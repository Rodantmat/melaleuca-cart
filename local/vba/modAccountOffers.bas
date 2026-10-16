Attribute VB_Name = "modAccountOffers"
Option Explicit
'=====================================================================
' Per-account offers
'   Scan_Account_Offers   : a black window logs in to each account of the Melaleuca store (credentials.env), reads that account's
'                           Special Offers / monthly deals / coupons (it never places an order), then the result is imported.
'   Import_Account_Offers : reads feed\account_offers.tsv into the sheet "AccountOffers" (one line per tab + product).
' Generate All Orders then uses, for every scanned tab, only the discounts that account really has.
'=====================================================================
Private Const BASE_DIR As String = "C:\AmazonFeed\"

Private Function ReadUtf8(ByVal path As String) As String
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.LoadFromFile path
    ReadUtf8 = Replace(st.ReadText, vbCr, "")
    st.Close
End Function

Public Sub Scan_Account_Offers()
    Dim sh As Object, cmd As String, rc As Long, q As String, d As String
    If Dir(BASE_DIR & "melaleuca_run.py") = "" Or Dir(BASE_DIR & "credentials.env") = "" Then
        MsgBox "The account scan is not set up yet (melaleuca_run.py / credentials.env missing in " & BASE_DIR & ")." & vbCrLf & "Update Melaleuca Data did the prices only.", vbInformation, "Account offers"
        Exit Sub
    End If
    On Error Resume Next
    Application.Run "Export_Order_Tabs"
    On Error GoTo 0
    q = Chr(34): d = Left$(BASE_DIR, Len(BASE_DIR) - 1)
    cmd = "cmd /c " & q & "cd /d " & q & d & q & " && python melaleuca_run.py || pause" & q
    Set sh = CreateObject("WScript.Shell")
    Application.StatusBar = "Reading the offers of each account... (about 2 minutes per account)"
    rc = sh.Run(cmd, 1, True)
    Application.StatusBar = False
    If rc <> 0 Then
        MsgBox "The account scan reported a problem (code " & rc & "). See " & BASE_DIR & "feed\scan_log.txt" & vbCrLf & "The accounts that WERE read are imported anyway; the others keep their older data.", vbExclamation, "Account offers"
    End If
    Import_Account_Offers
End Sub

Public Sub Import_Account_Offers()
    Dim wa As Worksheet, txt As String, ln() As String, p() As String, i As Long, r As Long, k As Long, nNew As Long, nTabs As Long
    Dim tabs As String, keep() As Variant, nKeep As Long, lastA As Long, old As Variant, t As String
    Dim c2 As String, q2 As String
    ' always re-match the LAST scan (feed\melaleuca_offers.json, no internet / no proxy) with the current product list, so the newest matching rules apply
    If Dir(BASE_DIR & "feed\melaleuca_offers.json") <> "" And Dir(BASE_DIR & "melaleuca_offers_map.py") <> "" Then
        On Error Resume Next
        Application.Run "Export_Order_Tabs"
        q2 = Chr(34)
        c2 = "cmd /c " & q2 & "cd /d " & q2 & Left$(BASE_DIR, Len(BASE_DIR) - 1) & q2 & " && set PYTHONIOENCODING=utf-8:replace&& python melaleuca_offers_map.py feed\melaleuca_offers.json feed\mel_rows.tsv feed\account_offers.tsv > feed\map_log.txt 2>&1" & q2
        CreateObject("WScript.Shell").Run c2, 0, True
        On Error GoTo 0
    End If
    If Dir(BASE_DIR & "feed\account_offers.tsv") = "" Then
        MsgBox "feed\account_offers.tsv was not found - run the scan first.", vbExclamation, "Account offers"
        Exit Sub
    End If
    txt = ReadUtf8(BASE_DIR & "feed\account_offers.tsv")
    ln = Split(txt, vbLf)
    On Error Resume Next
    Set wa = ThisWorkbook.Sheets("AccountOffers")
    On Error GoTo 0
    If wa Is Nothing Then
        On Error Resume Next
        Set wa = ThisWorkbook.Sheets.Add(Before:=ThisWorkbook.Sheets("Summary"))     ' before the Summary tab, so it is never taken for an order tab
        If wa Is Nothing Then Set wa = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets("Melaleuca"))
        On Error GoTo 0
        wa.Name = "AccountOffers"
    End If
    ' tabs in the new file
    For i = 1 To UBound(ln)
        p = Split(ln(i), vbTab)
        If UBound(p) >= 5 Then
            If InStr(tabs, "|" & p(0) & "|") = 0 Then tabs = tabs & "|" & p(0) & "|": nTabs = nTabs + 1
        End If
    Next i
    ' keep the older lines of tabs that were not scanned this time
    lastA = wa.Cells(wa.Rows.count, 1).End(xlUp).Row
    ReDim keep(1 To IIf(lastA < 2, 1, lastA), 1 To 10)
    If lastA >= 2 Then
        old = wa.Range(wa.Cells(1, 1), wa.Cells(lastA, 10)).Value
        For r = 2 To lastA
            t = CStr(old(r, 1))
            If Len(t) > 0 And InStr(tabs, "|" & t & "|") = 0 Then
                nKeep = nKeep + 1
                For k = 1 To 10
                    keep(nKeep, k) = old(r, k)
                Next k
            End If
        Next r
    End If
    wa.Cells.Clear
    wa.Range("A1:J1").Value = Array("Tab", "ASIN", "Type", "Units", "UnitPrice", "SetPoints", "OfferSku", "OfferTitle", "How", "Scanned")
    wa.Range("A1:J1").Font.Bold = True
    r = 2
    For i = 1 To nKeep
        For k = 1 To 10
            wa.Cells(r, k).Value = keep(i, k)
        Next k
        r = r + 1
    Next i
    For i = 1 To UBound(ln)
        p = Split(ln(i), vbTab)
        If UBound(p) >= 5 Then
            wa.Cells(r, 1).NumberFormat = "@"
            wa.Cells(r, 1).Value = p(0)
            wa.Cells(r, 2).Value = p(1)
            wa.Cells(r, 3).Value = p(2)
            wa.Cells(r, 4).Value = Val(p(3))
            wa.Cells(r, 5).Value = Val(p(4))
            wa.Cells(r, 6).Value = Val(p(5))
            If UBound(p) >= 6 Then wa.Cells(r, 7).Value = "'" & p(6)
            If UBound(p) >= 7 Then wa.Cells(r, 8).Value = p(7)
            If UBound(p) >= 8 Then wa.Cells(r, 9).Value = p(8)
            If UBound(p) >= 9 Then wa.Cells(r, 10).Value = p(9)
            If p(1) <> "*" Then nNew = nNew + 1
            r = r + 1
        End If
    Next i
    wa.Columns("A:J").AutoFit
    MsgBox nTabs & " account(s) read, " & nNew & " offer lines imported into the sheet AccountOffers." & vbCrLf & _
           "Now run Generate All Orders: each scanned tab uses only its own offers.", vbInformation, "Account offers"
End Sub
