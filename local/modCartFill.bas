Attribute VB_Name = "modCartFill"
Option Explicit
' ------------------------------------------------------------------------------------------------------------
' Auto-Fill Cart  (button on every order tab)
'   1. writes the order of the ACTIVE tab to C:\AmazonFeed\feed\cart_plan.tsv  (what to buy, which pack, which offer)
'   2. starts  python melaleuca_fill.py <tab number>  : opens the Melaleuca cart of that account with its own steady IP,
'      puts the whole order in the cart, goes through the Special Offers page and stops on the final checkout screen.
'      It NEVER pays and NEVER places the order: you check the cart and press the payment button yourself.
' ------------------------------------------------------------------------------------------------------------
Private Const BASE_DIR As String = "C:\AmazonFeed\"

Private Function Clean(ByVal v As Variant) As String
    Dim s As String
    If IsError(v) Then Clean = "": Exit Function
    s = CStr(v)
    s = Replace(s, vbTab, " "): s = Replace(s, vbCr, " "): s = Replace(s, vbLf, " ")
    Clean = Trim$(s)
End Function

Private Function Num(ByVal v As Variant) As String
    If IsError(v) Then Num = "0": Exit Function
    If IsNumeric(v) And Len(CStr(v)) > 0 Then
        Num = Replace(CStr(v), ",", ".")
    Else
        Num = "0"
    End If
End Function

Private Function HeaderCol(ws As Worksheet, ByVal title As String) As Long
    Dim c As Long
    For c = 1 To 200
        If Trim$(CStr(ws.Cells(1, c).Value)) = title Then HeaderCol = c: Exit Function
    Next c
    HeaderCol = 0
End Function

Private Sub WriteUtf8(ByVal path As String, ByVal text As String)
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.WriteText text
    st.SaveToFile path, 2
    st.Close
End Sub

Private Function ReadUtf8(ByVal path As String) As String
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.LoadFromFile path
    ReadUtf8 = Replace(st.ReadText, vbCr, "")
    st.Close
End Function

' number of the tab as the scan numbers it (the line of feed\mel_tabs.txt that holds the tab name); 0 = not found
Private Function TabNumber(ByVal tabName As String) As Long
    Dim ln() As String, p() As String, i As Long
    If Dir(BASE_DIR & "feed\mel_tabs.txt") = "" Then Exit Function
    ln = Split(ReadUtf8(BASE_DIR & "feed\mel_tabs.txt"), vbLf)
    For i = 0 To UBound(ln)
        p = Split(ln(i), vbTab)
        If UBound(p) >= 1 Then
            If p(1) = tabName Then TabNumber = Val(p(0)): Exit Function
        End If
    Next i
End Function

' builds the plan text of one order tab
Public Function Build_Cart_Plan(ws As Worksheet, ByVal tabNo As Long) As String
    Dim wm As Worksheet, wa As Worksheet, t As String, r As Long, mr As Long, k As Long
    Dim cAsin As Long, cMela As Long, cPack As Long, cPsz As Long
    Dim gKey As Long, gWhat As Long, gPack As Long, gUnits As Long, gSlots As Long, gLabel As Long
    Dim mKey As Long, mAsin As Long, mSlot As Long, mName As Long
    Dim cc As Long
    Dim asin As String, key As String, seen As String, offSku As String, offType As String, packSku As String, melId As String
    Dim lastA As Long, lastM As Long
    Set wm = ThisWorkbook.Sheets("Melaleuca")
    On Error Resume Next
    Set wa = ThisWorkbook.Sheets("AccountOffers")
    On Error GoTo 0
    cAsin = HeaderCol(wm, "ASIN"): cMela = HeaderCol(wm, "Mela ID"): cPack = HeaderCol(wm, "Pack row"): cPsz = HeaderCol(wm, "Pack size")
    gKey = HeaderCol(wm, "GROUP: key"): gWhat = HeaderCol(wm, "GROUP: what it is"): gPack = HeaderCol(wm, "GROUP: pack item no.")
    gUnits = HeaderCol(wm, "GROUP: units in set"): gSlots = HeaderCol(wm, "GROUP: slots (A2 = 2 of slot A, A1,B1 = one of A and one of B)"): gLabel = HeaderCol(wm, "GROUP: label (WITH / OF)")
    mKey = HeaderCol(wm, "MEMBER: group key"): mAsin = HeaderCol(wm, "MEMBER: ASIN"): mSlot = HeaderCol(wm, "MEMBER: slot"): mName = HeaderCol(wm, "MEMBER: name used in the note")
    cc = HeaderCol(wm, "CLEAN COMBO: units")
    If cAsin = 0 Or cMela = 0 Then Err.Raise vbObjectError + 1, , "The Melaleuca tab has no ASIN / Mela ID column."
    lastM = wm.Cells(wm.Rows.count, cAsin).End(xlUp).Row
    If lastM < 700 Then lastM = 700
    If Not wa Is Nothing Then lastA = wa.Cells(wa.Rows.count, 1).End(xlUp).Row
    t = "TAB" & vbTab & ws.Name & vbTab & tabNo & vbLf
    t = t & "CREDIT" & vbTab & Num(ws.Range("P9").Value) & vbLf
    ' ---- order lines
    r = 2
    Do While Len(Trim$(CStr(ws.Cells(r, 2).Value))) > 0 And UCase$(Trim$(CStr(ws.Cells(r, 1).Value))) <> "TOTAL"
        asin = Trim$(CStr(ws.Cells(r, 2).Value))
        If Val(ws.Cells(r, 9).Value) > 0 Then
            mr = 0: melId = "": packSku = ""
            For k = 2 To lastM
                If CStr(wm.Cells(k, cAsin).Value) = asin Then mr = k: Exit For
            Next k
            If mr > 0 Then
                melId = Clean(wm.Cells(mr, cMela).Value)
                If cPack > 0 Then
                    If IsNumeric(wm.Cells(mr, cPack).Value) And Val(wm.Cells(mr, cPack).Value) >= 2 Then
                        packSku = Clean(wm.Cells(Val(wm.Cells(mr, cPack).Value), cMela).Value)
                    End If
                End If
            End If
            offSku = "": offType = ""
            If Not wa Is Nothing Then
                For k = 2 To lastA
                    If CStr(wa.Cells(k, 1).Value) = ws.Name And CStr(wa.Cells(k, 2).Value) = asin Then
                        offType = Clean(wa.Cells(k, 3).Value): offSku = Clean(wa.Cells(k, 7).Value)
                        Exit For
                    End If
                Next k
            End If
            t = t & "L" & vbTab & r & vbTab & asin & vbTab & Clean(ws.Cells(r, 1).Value) & vbTab & Clean(ws.Cells(r, 8).Value) & vbTab & _
                Num(ws.Cells(r, 9).Value) & vbTab & Num(ws.Cells(r, 12).Value) & vbTab & Clean(ws.Cells(r, 14).Value) & vbTab & Clean(ws.Cells(r, 18).Value) & vbTab & _
                Num(ws.Cells(r, 19).Value) & vbTab & melId & vbTab & packSku & vbTab & offSku & vbTab & offType & vbTab & Num(ws.Cells(r, 10).Value) & vbLf
            key = Clean(ws.Cells(r, 18).Value)
            If Len(key) > 0 And Left$(key, 1) <> "#" And InStr(seen, "|" & key & "|") = 0 Then seen = seen & "|" & key & "|"
        End If
        r = r + 1
    Loop
    ' ---- totals of the tab
    Do While r <= 400 And UCase$(Trim$(CStr(ws.Cells(r, 1).Value))) <> "TOTAL"
        r = r + 1
    Loop
    If UCase$(Trim$(CStr(ws.Cells(r, 1).Value))) = "TOTAL" Then
        t = t & "TOTAL" & vbTab & Num(ws.Cells(r, 9).Value) & vbTab & Num(ws.Cells(r, 10).Value) & vbTab & Num(ws.Cells(r, 12).Value) & vbLf
    End If
    ' ---- groups used by this order (pack item number, slots) and their members
    If gKey > 0 Then
        For k = 2 To lastM
            key = Clean(wm.Cells(k, gKey).Value)
            If Len(key) > 0 Then
                If InStr(seen, "|" & key & "|") > 0 Then
                    t = t & "G" & vbTab & key & vbTab & Clean(wm.Cells(k, gWhat).Value) & vbTab & Clean(wm.Cells(k, gPack).Value) & vbTab & Clean(wm.Cells(k, gUnits).Value) & vbTab & _
                        Clean(wm.Cells(k, gSlots).Value) & vbTab & Clean(wm.Cells(k, gLabel).Value) & vbLf
                End If
            End If
        Next k
    End If
    If mKey > 0 Then
        For k = 2 To lastM
            key = Clean(wm.Cells(k, mKey).Value)
            If Len(key) > 0 Then
                If InStr(seen, "|" & key & "|") > 0 Then
                    t = t & "M" & vbTab & key & vbTab & Clean(wm.Cells(k, mAsin).Value) & vbTab & Clean(wm.Cells(k, mSlot).Value) & vbTab & Clean(wm.Cells(k, mName).Value) & vbLf
                End If
            End If
        Next k
    End If
    If cc > 0 Then       ' the customizable cleaner pack: units, pack price, pack points
        For k = 2 To 6
            If IsNumeric(wm.Cells(k, cc).Value) And Len(CStr(wm.Cells(k, cc).Value)) > 0 Then
                t = t & "CLEANPACK" & vbTab & Num(wm.Cells(k, cc).Value) & vbTab & Num(wm.Cells(k, cc + 1).Value) & vbTab & Num(wm.Cells(k, cc + 2).Value) & vbLf
            End If
        Next k
    End If
    Build_Cart_Plan = t
End Function

' the button: Auto-Fill Cart
Public Sub Auto_Fill_Cart()
    Dim ws As Worksheet, n As Long, d As String, q As String, sh As Object, plan As String, msg As String
    Set ws = ActiveSheet
    If Dir(BASE_DIR & "melaleuca_fill.py") = "" Or Dir(BASE_DIR & "credentials.env") = "" Then
        MsgBox "The cart filler is not set up yet (melaleuca_fill.py / credentials.env missing in " & BASE_DIR & ").", vbInformation, "Auto-Fill Cart"
        Exit Sub
    End If
    On Error Resume Next
    Application.Run "Export_Order_Tabs"
    On Error GoTo 0
    n = TabNumber(ws.Name)
    If n = 0 Then
        MsgBox "This tab is not one of the coloured order tabs, so there is no account for it.", vbExclamation, "Auto-Fill Cart"
        Exit Sub
    End If
    If Application.WorksheetFunction.CountA(ws.Range("B2:B3")) = 0 Then
        MsgBox "This tab has no order yet. Generate the orders first.", vbExclamation, "Auto-Fill Cart"
        Exit Sub
    End If
    msg = "Fill the Melaleuca cart of the account of tab '" & ws.Name & "' (tab " & n & ") with this order?" & vbCrLf & vbCrLf & _
          "A browser window opens, signs in and puts the products in the cart. It stops on the checkout screen - it does not pay and does not place the order." & vbCrLf & _
          "(Anything already in that cart stays; if the cart is not empty you will be told.)"
    If MsgBox(msg, vbQuestion + vbOKCancel, "Auto-Fill Cart") <> vbOK Then Exit Sub
    On Error GoTo failed
    plan = Build_Cart_Plan(ws, n)
    WriteUtf8 BASE_DIR & "feed\cart_plan_" & n & ".tsv", plan
    q = Chr(34): d = Left$(BASE_DIR, Len(BASE_DIR) - 1)
    Set sh = CreateObject("WScript.Shell")
    sh.Run "cmd /c " & q & "cd /d " & q & d & q & " && python melaleuca_fill.py " & n & " || pause" & q, 1, False
    Exit Sub
failed:
    MsgBox "The cart could not be prepared: " & Err.Description, vbExclamation, "Auto-Fill Cart"
End Sub
