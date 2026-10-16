Attribute VB_Name = "Module1"

'========================== SORT ACTIVE SHEET BY COLUMN A ===================================
'=================================== START HERE =============================================

Option Explicit

Private Const PTS_LO As Long = 143
Private Const PTS_HI As Long = 148
Private Const MAX_LINES As Long = 52
Private Const PTS_MAX As Long = 150      ' hard limit used by Add_New_Product
Private Const DEFAULT_CREDIT As Double = 10.42   ' monthly account credit of an account (typed on each order tab, cell P9)
Private Const CREDIT_CELL As String = "P9"
Private Const CREDIT_LABEL As String = "P8"

' state shared by the order builders (Create_All_Orders runs them silently)
Private gSilent As Boolean
Private gOvOn As Boolean          ' True while the offers of one account are laid over the Melaleuca tab
Private gOvSave As Variant        ' the Melaleuca V:Y values to put back
Private gOvLast As Long
Private gNote As String
Private gOk As Boolean
Private gPts As Double
Private gLines As Long
Private gOverlap As Double
Private gNoCredit As Boolean    ' True = no credit items on this build (member-savings packs)
Private gAppend As Boolean      ' True = BuildOrderTab keeps the products already on the tab and only adds to them
Private gPendOn As Boolean      ' True while Create_All_Orders runs: the units placed on its tabs are remembered here, the Summary is rebuilt once at the end
Private gPend() As Double       ' units placed during this run, by Melaleuca row

' set recipes: savings packs made of different products (Melaleuca columns CJ:CU = recipes, DE:DI = members)
Private gRecN As Long
Private gRecKey(1 To 120) As String
Private gRecUnits(1 To 120) As Long
Private gRecPrice(1 To 120) As Double
Private gRecPts(1 To 120) As Double
Private gRecSlots(1 To 120) As String
Private gRecLabel(1 To 120) As String
Private gRecName(1 To 120) As String
Private gMemN As Long
Private gMemKey(1 To 400) As String
Private gMemAsin(1 To 400) As String
Private gMemSlot(1 To 400) As String
Private gMemNote(1 To 400) As String

Sub SortActiveSheetByColumnA()
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim totalRow As Long
    Dim r As Long
    
    Set ws = ActiveSheet
    
    ' Find last used row in Column A
    lastRow = ws.Cells(ws.Rows.count, "A").End(xlUp).Row
    
    ' Exit if no data
    If lastRow <= 2 Then Exit Sub
    
    ' Find TOTAL row if exists
    totalRow = lastRow
    For r = lastRow To 2 Step -1
        If ws.Cells(r, 1).Value = "TOTAL" Then
            totalRow = r
            Exit For
        End If
    Next r
    
    ' Sort range from row 2 to row above TOTAL
    If totalRow > 2 Then
        ws.Sort.SortFields.Clear
        ws.Sort.SortFields.Add key:=ws.Range("A2:A" & totalRow - 1), _
            SortOn:=xlSortOnValues, Order:=xlAscending, DataOption:=xlSortNormal
        With ws.Sort
            .SetRange ws.Range("A2:O" & totalRow - 1)
            .Header = xlNo
            .MatchCase = False
            .Orientation = xlTopToBottom
            .Apply
        End With
    End If
End Sub
'========================== SORT ACTIVE SHEET BY COLUMN A ===================================
'===================================== END HERE =============================================














'========================== ADD 5 EXTRA FORMULA ROWS ===================================
'================================== START HERE =========================================

' === Add 5 extra formula rows + final totals ===
Sub AddFiveExtraFormulaRows()
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim startRow As Long
    Dim r As Long
    Dim totalRow As Long
    
    Set ws = ActiveSheet
    Dim ms As String: ms = MelFor(ws)      ' Canadian (orange / yellow) tabs read the sheet MelaleucaCA = same table with the Canadian store's points
    
    ' Find last used row in column A
    lastRow = ws.Cells(ws.Rows.count, "A").End(xlUp).Row
    
    ' Start immediately after last used row
    startRow = lastRow + 1
    
    ' Insert 5 rows with formulas
    For r = 0 To 4
        Dim curRow As Long
        curRow = startRow + r
        
        ' Column A
        ws.Cells(curRow, 1).Formula = "=IF(B" & curRow & "="""","""",IFERROR(INDEX(" & ms & "!A:A, MATCH(B" & curRow & ", " & ms & "!D:D, 0)),""""))"
        
        ' Column C
        ws.Cells(curRow, 3).Formula = "=IF(B" & curRow & "="""","""",IFERROR(IF(INDEX(" & ms & "!V:V, MATCH(B" & curRow & ", " & ms & "!D:D, 0))>0," & _
            "INDEX(" & ms & "!V:V, MATCH(B" & curRow & ", " & ms & "!D:D, 0))," & _
            "INDEX(" & ms & "!U:U, MATCH(B" & curRow & ", " & ms & "!D:D, 0))),""""))"
        
        ' Column D
        ws.Cells(curRow, 4).Formula = "=IF(B" & curRow & "="""","""",IFERROR(INDEX(" & ms & "!I:I, MATCH(B" & curRow & ", " & ms & "!D:D, 0)),""""))"
        
        ' Column E
        ws.Cells(curRow, 5).Formula = "=IF(B" & curRow & "="""","""",IFERROR(INDEX(" & ms & "!K:K, MATCH(B" & curRow & ", " & ms & "!D:D, 0)),""""))"
        
        ' Column F
        ws.Cells(curRow, 6).Formula = "=IF(B" & curRow & "="""","""",IFERROR(INDEX(" & ms & "!L:L, MATCH(B" & curRow & ", " & ms & "!D:D, 0)),""""))"
        
        ' Column G
        ws.Cells(curRow, 7).Formula = "=IF(B" & curRow & "="""","""",IFERROR(INDEX(" & ms & "!M:M, MATCH(B" & curRow & ", " & ms & "!D:D, 0)),""""))"
        
        ' Column I: blank if B is blank, else 1
        ws.Cells(curRow, 9).Formula = "=IF(B" & curRow & "="""","""",1)"
        
        ' Column J = I * C (blank if B blank)
        ws.Cells(curRow, 10).Formula = "=IF(B" & curRow & "="""","""",I" & curRow & "*C" & curRow & ")"
        
        ' Column K = C * D * I (blank if B blank)
        ws.Cells(curRow, 11).Formula = "=IF(B" & curRow & "="""","""",C" & curRow & "*D" & curRow & "*I" & curRow & ")"
        
        ' Column L = MELALEUCA T * I (blank if B blank)
        ws.Cells(curRow, 12).Formula = "=IF(B" & curRow & "="""","""",(INDEX(" & ms & "!T:T, MATCH(B" & curRow & ", " & ms & "!D:D, 0)))*I" & curRow & ")"
        
        ' Ensure new rows are NOT bold
        ws.Rows(curRow).Font.Bold = False
    Next r
    
    ' --- Format new rows ---
    With ws.Rows(startRow & ":" & startRow + 4)
        .Columns("A").HorizontalAlignment = xlLeft
        .Columns("B:L").HorizontalAlignment = xlCenter
        .Columns("C").NumberFormat = "$#,##0.00"
        .Columns("D").NumberFormat = "0.00%"
        .Columns("J:K").NumberFormat = "$#,##0.00"
    End With
    
    ws.Columns("A:L").AutoFit
    
    ' --- Add a blank row before totals ---
    totalRow = startRow + 5 + 1  ' 5 extra rows + 1 blank
    
    ' --- Add totals row ---
    ws.Cells(totalRow, 1).Value = "TOTAL"
    ws.Cells(totalRow, 9).Formula = "=SUM(I2:I" & totalRow - 2 & ")"
    ws.Cells(totalRow, 10).Formula = "=SUM(J2:J" & totalRow - 2 & ")"
    ws.Cells(totalRow, 11).Formula = "=SUM(K2:K" & totalRow - 2 & ")"
    ws.Cells(totalRow, 12).Formula = "=SUM(L2:L" & totalRow - 2 & ")"
    
    ' Format total row ONLY bold
    With ws.Rows(totalRow)
        .HorizontalAlignment = xlCenter
        .Columns("A").HorizontalAlignment = xlLeft
        .Font.Bold = True
        .Columns("C").NumberFormat = "$#,##0.00"
        .Columns("D").NumberFormat = "0.00%"
        .Columns("J:K").NumberFormat = "$#,##0.00"
    End With
End Sub
'========================== ADD 5 EXTRA FORMULA ROWS ===================================
'================================== END HERE ===========================================











'=============================== SUMMARIZE ALL SHEETS =======================================
'=================================== START HERE =============================================

' Helper: Convert many kinds of cell values to a numeric Double (returns 0 on invalid input)
Private Function ToDouble(v As Variant) As Double
    On Error Resume Next
    If IsError(v) Or IsEmpty(v) Then
        ToDouble = 0
        Exit Function
    End If
    If IsNumeric(v) Then
        ToDouble = CDbl(v)
        Exit Function
    End If
    
    Dim s As String
    s = CStr(v)
    s = Trim$(s)
    If s = "" Then
        ToDouble = 0
        Exit Function
    End If
    
    ' strip $ and commas
    s = Replace$(s, "$", "")
    s = Replace$(s, ",", "")
    
    ' percentage handling
    If InStr(s, "%") > 0 Then
        s = Replace$(s, "%", "")
        If IsNumeric(s) Then
            ToDouble = CDbl(s) / 100
        Else
            ToDouble = 0
        End If
        Exit Function
    End If
    
    If IsNumeric(s) Then
        ToDouble = CDbl(s)
    Else
        ToDouble = 0
    End If
End Function

' Helper: parse profit% robustly; returns Empty string if not available
Private Function ParseProfitPct(v As Variant) As Variant
    If IsError(v) Or IsEmpty(v) Then
        ParseProfitPct = ""
        Exit Function
    End If
    If IsNumeric(v) Then
        ParseProfitPct = CDbl(v)
        Exit Function
    End If
    
    Dim s As String
    s = CStr(v)
    s = Trim$(s)
    If s = "" Then
        ParseProfitPct = ""
        Exit Function
    End If
    
    If InStr(s, "%") > 0 Then
        s = Replace$(s, "%", "")
        If IsNumeric(s) Then
            ParseProfitPct = CDbl(s) / 100
        Else
            ParseProfitPct = ""
        End If
    Else
        If IsNumeric(s) Then
            ParseProfitPct = CDbl(s)
        Else
            ParseProfitPct = ""
        End If
    End If
End Function

' NEW HELPER: check if a string looks like a real ASIN (skip rows with "1", "2", etc.)
Private Function LooksLikeASIN(ByVal s As String) As Boolean
    Dim i As Long
    Dim ch As String
    Dim hasLetter As Boolean
    
    s = Trim$(s)
    If Len(s) < 8 Or Len(s) > 12 Then Exit Function   ' typical ASIN length
    
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        If ch >= "A" And ch <= "Z" Then
            hasLetter = True
        ElseIf ch >= "0" And ch <= "9" Then
            ' ok
        Else
            Exit Function            ' invalid character
        End If
    Next i
    
    LooksLikeASIN = hasLetter       ' must have at least one letter
End Function

' 1. SUMMARIZE ALL SHEETS IN CURRENT WORKBOOK
Sub SummarizeAllSheets()
    Dim wb As Workbook: Set wb = ThisWorkbook
    Dim wsSummary As Worksheet, ws As Worksheet
    Dim dict As Object: Set dict = CreateObject("Scripting.Dictionary")
    Dim firstDataSheetIndex As Long: firstDataSheetIndex = FirstOrderIdx()
    Dim sIdx As Long, lastRow As Long, r As Long
    Dim asin As String, key As String, nameVal As String
    Dim wsPriceVal As Double, profitPctVal As Variant
    Dim rankVal As Variant, stockVal As Variant, priorityVal As Variant
    Dim qtyVal As Double, totWsVal As Double, totProfVal As Double, pointsVal As Double

    ' Column mapping (same layout as your order tabs)
    Const COL_NAME As Long = 1
    Const COL_ASIN As Long = 2
    Const COL_WS_PRICE As Long = 3
    Const COL_PROFIT_PCT As Long = 4
    Const COL_RANK As Long = 5
    Const COL_STOCK As Long = 6
    Const COL_PRIORITY As Long = 7
    Const COL_QTY As Long = 9
    Const COL_TOTAL_WS As Long = 10
    Const COL_TOTAL_PROF As Long = 11
    Const COL_POINTS As Long = 12

    ' Create/Clear SUMMARY sheet
    On Error Resume Next
    Set wsSummary = wb.Sheets("SUMMARY")
    On Error GoTo 0
    If wsSummary Is Nothing Then
        Set wsSummary = wb.Sheets.Add(After:=wb.Sheets(wb.Sheets.count))
        wsSummary.Name = "SUMMARY"
    Else
        wsSummary.Cells.Clear
    End If

    ' Loop sheets and collect
    For sIdx = firstDataSheetIndex To wb.Sheets.count
        Set ws = wb.Sheets(sIdx)
        If UCase$(ws.Name) = "SUMMARY" Then GoTo NextSheet
        
        lastRow = ws.Cells(ws.Rows.count, COL_ASIN).End(xlUp).Row
        If lastRow < 2 Then GoTo NextSheet

        For r = 2 To lastRow
            If IsError(ws.Cells(r, COL_ASIN)) Then GoTo NextRow
            
            asin = Trim$(CStr(ws.Cells(r, COL_ASIN)))
            
            ' Skip empty / TOTAL / comment rows
            If asin = "" Then GoTo NextRow
            If UCase$(asin) = "TOTAL" Then GoTo NextRow
            If Left$(asin, 1) = "#" Then GoTo NextRow
            
            ' *** NEW FILTER: skip rows where "asin" is not a real ASIN (e.g., "1", "2") ***
            If Not LooksLikeASIN(asin) Then GoTo NextRow
            
            nameVal = Trim$(CStr(ws.Cells(r, COL_NAME)))
            wsPriceVal = ToDouble(ws.Cells(r, COL_WS_PRICE))
            profitPctVal = ParseProfitPct(ws.Cells(r, COL_PROFIT_PCT))
            rankVal = ws.Cells(r, COL_RANK)
            stockVal = ws.Cells(r, COL_STOCK)
            priorityVal = ws.Cells(r, COL_PRIORITY)
            qtyVal = ToDouble(ws.Cells(r, COL_QTY))
            totWsVal = ToDouble(ws.Cells(r, COL_TOTAL_WS))
            totProfVal = ToDouble(ws.Cells(r, COL_TOTAL_PROF))
            pointsVal = ToDouble(ws.Cells(r, COL_POINTS))

            key = asin
            If Not dict.Exists(key) Then
                Dim rec As Variant
                rec = Array(nameVal, key, wsPriceVal, profitPctVal, rankVal, stockVal, priorityVal, _
                            qtyVal, totWsVal, totProfVal, pointsVal)
                dict.Add key, rec
            Else
                Dim tmp As Variant
                tmp = dict(key)
                
                If tmp(0) = "" And nameVal <> "" Then tmp(0) = nameVal
                If tmp(2) = 0 And wsPriceVal <> 0 Then tmp(2) = wsPriceVal
                If (IsEmpty(tmp(3)) Or tmp(3) = "") And Not (IsEmpty(profitPctVal) Or profitPctVal = "") Then tmp(3) = profitPctVal
                If (IsEmpty(tmp(4)) Or tmp(4) = "") And Not (IsEmpty(rankVal) Or rankVal = "") Then tmp(4) = rankVal
                If (IsEmpty(tmp(5)) Or tmp(5) = "") And Not (IsEmpty(stockVal) Or stockVal = "") Then tmp(5) = stockVal
                If (IsEmpty(tmp(6)) Or tmp(6) = "") And Not (IsEmpty(priorityVal) Or priorityVal = "") Then tmp(6) = priorityVal
                
                tmp(7) = tmp(7) + qtyVal
                tmp(8) = tmp(8) + totWsVal
                tmp(9) = tmp(9) + totProfVal
                tmp(10) = tmp(10) + pointsVal
                
                dict(key) = tmp
            End If
NextRow:
        Next r
NextSheet:
    Next sIdx

    ' Output
    Dim headers As Variant
    headers = Array("Name", "ASIN", "WS Price", "Profit %", "Rank", "Stock", "Priority", _
                    "Quantity", "Total WS", "Total Profit", "Points")
    Dim i As Long, outRow As Long
    For i = 0 To UBound(headers)
        wsSummary.Cells(1, i + 1) = headers(i)
    Next i
    wsSummary.Rows(1).Font.Bold = True

    outRow = 2
    Dim k As Variant, recOut As Variant
    For Each k In dict.Keys
        recOut = dict(k)
        For i = 0 To UBound(recOut)
            wsSummary.Cells(outRow, i + 1).Value = recOut(i)
        Next i
        outRow = outRow + 1
    Next k

    Dim totalRow As Long
    totalRow = outRow + 1
    wsSummary.Cells(totalRow, 1) = "TOTAL"
    wsSummary.Cells(totalRow, 8).Formula = "=SUM(H2:H" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 9).Formula = "=SUM(I2:I" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 10).Formula = "=SUM(J2:J" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 11).Formula = "=SUM(K2:K" & outRow - 1 & ")"

    With wsSummary
        .Columns("A").HorizontalAlignment = xlLeft
        .Columns("B").HorizontalAlignment = xlCenter
        .Columns("C").NumberFormat = "$#,##0.00"
        .Columns("D").NumberFormat = "0.00%"
        .Columns("I:J").NumberFormat = "$#,##0.00"
        .Columns("H").NumberFormat = "0"
        .Columns("A:K").AutoFit
        .Rows(totalRow).Font.Bold = True
    End With

    ' Sort by Name
    wsSummary.Range("A2:K" & outRow - 1).Sort _
        Key1:=wsSummary.Range("A2"), Order1:=xlAscending, Header:=xlNo

    ' Insert an empty column before Quantity and update total formulas to match your old layout
    wsSummary.Columns("H").Insert Shift:=xlToRight
    wsSummary.Cells(totalRow, 9).Formula = "=SUM(I2:I" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 10).Formula = "=SUM(J2:J" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 11).Formula = "=SUM(K2:K" & outRow - 1 & ")"
    wsSummary.Cells(totalRow, 12).Formula = "=SUM(L2:L" & outRow - 1 & ")"

    'MsgBox "Summary complete. " & dict.Count & " unique ASIN(s) summarized.", vbInformation
End Sub

'=============================== SUMMARIZE ALL SHEETS =======================================
'===================================== END HERE =============================================









'=====================================================================================
' FILL PACKS  (button "Fill Packs" on every order tab)
' Fills the order tab with one of the member-savings packs (Melaleuca columns AC:AR):
'   - every item of the pack is written one by one, and the price of each item becomes its share of the
'     pack price (the pack price is split in proportion to the normal price, so the order total = the pack price)
'   - profit %, profit $, points and the totals are recalculated from that new price
'   - if the pack is below the points target, the order is topped up with the normal engine
'     (products that still need stock) and the monthly account credit items are added
'   - pack rows are marked "Pack" in column H
'=====================================================================================
Private Function PackName(ByVal p As Long) As String
    Select Case p
        Case 1: PackName = "EcoSense Home Pack"
        Case 2: PackName = "Value Pack"
        Case 3: PackName = "Home Conversion Pack"
        Case 4: PackName = "Customer Favorite Pack"
        Case Else: PackName = "Starter Pack"
    End Select
End Function

Private Function PackQtyCol(ByVal p As Long) As Long
    Select Case p
        Case 1: PackQtyCol = 29     ' AC
        Case 2: PackQtyCol = 32     ' AF
        Case 3: PackQtyCol = 35     ' AI
        Case 4: PackQtyCol = 38     ' AL
        Case Else: PackQtyCol = 42  ' AP
    End Select
End Function

' the pack price sits under the share column of the pack (row after the last product, e.g. AE170)
Private Function PackPrice(wsSrc As Worksheet, ByVal p As Long, ByVal lastR As Long) As Double
    Dim r As Long, c As Long
    c = PackQtyCol(p) + 2
    For r = lastR + 1 To lastR + 8
        If Len(CellText(wsSrc.Cells(r, 1).Value)) = 0 Then
            If IsNumeric(wsSrc.Cells(r, c).Value) And Not IsEmpty(wsSrc.Cells(r, c).Value) Then
                If SafeDbl(wsSrc.Cells(r, c).Value) > 0 And Not wsSrc.Cells(r, c).HasFormula Then
                    PackPrice = SafeDbl(wsSrc.Cells(r, c).Value)
                    Exit Function
                End If
            End If
        End If
    Next r
End Function

' asks a number (kept separate so it can be tested)
Private Function AskNumber(ByVal prompt As String, ByVal title As String) As Variant
    AskNumber = Application.InputBox(prompt:=prompt, Title:=title, Type:=1)
End Function

Private Sub WriteOrderHeaders(ws As Worksheet)
    With ws
        .Cells(1, 2).Value = "ASIN"
        .Cells(1, 3).Value = "WS Price"
        .Cells(1, 4).Value = "Profit %"
        .Cells(1, 5).Value = "Rank"
        .Cells(1, 6).Value = "Stock"
        .Cells(1, 7).Value = "Priority"
        .Cells(1, 8).Value = "Notes"
        .Cells(1, 9).Value = "Quantity"
        .Cells(1, 10).Value = "Total WS"
        .Cells(1, 11).Value = "Total Profit"
        .Cells(1, 12).Value = "Points"
        .Cells(1, 14).Value = "Discount / Credit"
        .Cells(1, 15).Value = "set key"
        .Rows(1).Font.Bold = True
    End With
End Sub

Public Sub Fill_Packs()
    Dim wb As Workbook, wsSrc As Worksheet, wsDest As Worksheet
    Dim lastR As Long, vals As Variant, p As Long, qc As Long, r As Long, j As Long, i As Long, k As Long
    Dim stU(1 To 5) As Double
    Dim stP(1 To 5) As Double
    Dim stPrice(1 To 5) As Double
    Dim stN(1 To 5) As Long
    Dim q As Double, o As Variant, a As String, listTxt As String
    Dim ans As Variant, packNo As Long, isLocal As Boolean, keepMode As Boolean, tabK As Long, fbaOnly As Boolean
    Dim iRow() As Long
    Dim iQty() As Double
    Dim iOrig() As Double
    Dim iShare() As Double
    Dim nI As Long
    Dim sumOrig As Double, price As Double, packPts As Double, unit As Double, nBad As Long, nLocalSkipped As Long, nNoAsin As Long
    Dim typ As String, fda As String, exN As Long, ptsAfter As Double, packLines As Long, noteTxt As String, msg As String
    Dim shr1 As Double

    Set wb = ThisWorkbook
    Set wsSrc = wb.Sheets("MELALEUCA")
    Set wsDest = ActiveSheet
    If Not IsOrderTab(wsDest) Then
        MsgBox "Click on an order tab first, then press Fill Packs.", vbExclamation, "Fill Packs"
        Exit Sub
    End If
    If CellText(wsSrc.Cells(1, 73).Value) <> "Priority (new)" Or CellText(wsSrc.Cells(1, 84).Value) <> "Set size (used)" Then
        MsgBox "Run Setup_NewPlan once first.", vbExclamation, "Fill Packs"
        Exit Sub
    End If
    lastR = SrcLastRow(wsSrc)
    vals = wsSrc.Range(wsSrc.Cells(1, 1), wsSrc.Cells(lastR, 86)).Value

    ' ---- what is in each pack
    For p = 1 To 5
        qc = PackQtyCol(p)
        stPrice(p) = PackPrice(wsSrc, p, lastR)
        For r = 2 To lastR
            q = SafeDbl(vals(r, qc))
            o = vals(r, qc + 1)
            If q > 0 And Not IsError(o) Then
                If IsNumeric(o) And Len(CStr(o)) > 0 Then
                    If CDbl(o) > 0 Then
                        stU(p) = stU(p) + q
                        stP(p) = stP(p) + q * SafeDbl(vals(r, 20))
                        stN(p) = stN(p) + 1
                    End If
                End If
            End If
        Next r
        listTxt = listTxt & p & " - " & PackName(p) & ":  $" & Format(stPrice(p), "0.00") & ",  " & stU(p) & " units,  " & stP(p) & " points" & vbCrLf
    Next p

    ' ---- existing order on the tab?
    exN = CountOrderRows(wsDest)
    If exN > 0 Then
        ans = MsgBox("This tab already has an order (" & exN & " products)." & vbCrLf & vbCrLf & _
                     "YES = replace it with the pack" & vbCrLf & _
                     "NO = keep it and add the pack (a product that is also in the pack takes the pack price)" & vbCrLf & _
                     "CANCEL = do nothing", vbYesNoCancel + vbQuestion, "Fill Packs")
        If ans = vbCancel Then Exit Sub
        keepMode = (ans = vbNo)
    End If

    ' ---- which pack
    ans = AskNumber("Which pack do you want to fill? Type the number:" & vbCrLf & vbCrLf & listTxt, "Fill Packs")
    If VarType(ans) = vbBoolean Then Exit Sub
    If Not IsNumeric(ans) Then Exit Sub
    packNo = CLng(ans)
    If packNo < 1 Or packNo > 5 Then
        MsgBox "Please type a number from 1 to 5.", vbExclamation, "Fill Packs"
        Exit Sub
    End If
    p = packNo
    qc = PackQtyCol(p)
    price = stPrice(p)
    If price <= 0 Then
        MsgBox "The price of the " & PackName(p) & " was not found under its share column (row after the last product).", vbExclamation, "Fill Packs"
        Exit Sub
    End If

    ' ---- isLocal order? (items that exist only in the isLocal store are skipped when it is not isLocal)
    ans = MsgBox("Is this a LOCAL order?" & vbCrLf & vbCrLf & _
                 "YES = local order (keep the items marked local-only)" & vbCrLf & _
                 "NO = shipped order (leave the local-only items out; the pack price is split between the other items)", _
                 vbYesNo + vbQuestion, "Fill Packs - local order?")
    isLocal = (ans = vbYes)

    ' ---- items of the chosen pack
    ReDim iRow(1 To lastR)
    ReDim iQty(1 To lastR)
    ReDim iOrig(1 To lastR)
    ReDim iShare(1 To lastR)
    tabK = TabKind(wsDest)
    fbaOnly = (tabK = 1)
    For r = 2 To lastR
        q = SafeDbl(vals(r, qc))
        o = vals(r, qc + 1)
        If q > 0 And Len(CellText(vals(r, 1))) > 0 And Not IsError(o) Then
            If IsNumeric(o) And Len(CStr(o)) > 0 Then
                If CDbl(o) > 0 Then
                    a = CellText(vals(r, 4))
                    If Len(a) = 0 Then
                        nNoAsin = nNoAsin + 1
                    ElseIf Not isLocal And CellText(vals(r, 41)) = "*" Then
                        nLocalSkipped = nLocalSkipped + 1
                    Else
                        nI = nI + 1
                        iRow(nI) = r
                        iQty(nI) = q
                        iOrig(nI) = CDbl(o)
                        sumOrig = sumOrig + CDbl(o)
                        packPts = packPts + q * SafeDbl(vals(r, 20))
                        typ = UCase$(CellText(vals(r, 3)))
                        fda = CellText(vals(r, 56))
                        If typ = "M" Or (Len(fda) > 0 And fda <> "0") Then nBad = nBad + 1
                    End If
                End If
            End If
        End If
    Next r
    If nI = 0 Or sumOrig <= 0 Then
        MsgBox "No items were found for the " & PackName(p) & ".", vbExclamation, "Fill Packs"
        Exit Sub
    End If

    ' ---- warnings
    If fbaOnly And nBad > 0 Then
        ans = MsgBox("This tab is an FBA-only (orange/yellow) tab, but " & nBad & " item(s) of the " & PackName(p) & " cannot go to FBA (Melaleuca-only or food items)." & vbCrLf & _
                     "Fill the pack anyway?", vbYesNo + vbQuestion, "Fill Packs")
        If ans <> vbYes Then Exit Sub
    End If
    If keepMode And packPts <= PTS_MAX Then
        If CountedPoints(wsDest, exN + 1) + packPts > PTS_MAX Then
            ans = MsgBox("The products already on this tab have " & CountedPoints(wsDest, exN + 1) & " points; adding the pack (" & packPts & " points) goes above the " & PTS_MAX & "-point limit." & vbCrLf & _
                         "Add it anyway?", vbYesNo + vbExclamation, "Fill Packs")
            If ans <> vbYes Then Exit Sub
        End If
    End If
    If packPts > PTS_MAX Then
        ans = MsgBox("The " & PackName(p) & " has " & packPts & " points, more than the " & PTS_MAX & "-point limit of one order." & vbCrLf & _
                     "Fill it anyway?", vbYesNo + vbExclamation, "Fill Packs")
        If ans <> vbYes Then Exit Sub
    End If

    ' ---- price of every item = its share of the pack price
    For j = 1 To nI
        iShare(j) = iOrig(j) * price / sumOrig
    Next j

    Application.ScreenUpdating = False
    If keepMode Then
        ' products that are also in the pack are replaced by the pack rows
        For r = exN + 1 To 2 Step -1
            a = CellText(wsDest.Cells(r, 2).Value)
            For j = 1 To nI
                If CellText(vals(iRow(j), 4)) = a Then
                    wsDest.Rows(r).Delete
                    Exit For
                End If
            Next j
        Next r
        exN = CountOrderRows(wsDest)
        ClearOrderRows wsDest, exN + 2, exN + 8
    Else
        ClearOrderRows wsDest, 2, 164
        exN = 0
    End If
    WriteOrderHeaders wsDest

    i = exN + 2
    For j = 1 To nI
        r = iRow(j)
        unit = iShare(j) / iQty(j)
        wsDest.Cells(i, 1).Value = vals(r, 1)
        wsDest.Cells(i, 2).Value = vals(r, 4)
        wsDest.Cells(i, 3).Value = unit
        If unit > 0 Then
            wsDest.Cells(i, 4).Value = (MoneyVal(vals(r, 5)) - unit - MoneyVal(vals(r, 7))) / unit
        Else
            wsDest.Cells(i, 4).Value = 0
        End If
        wsDest.Cells(i, 5).Value = vals(r, 11)
        wsDest.Cells(i, 6).Value = vals(r, 12)
        wsDest.Cells(i, 7).Value = vals(r, 13)
        wsDest.Cells(i, 9).Value = iQty(j)
        TagRow wsDest, i, "Pack"
        SetRowFormulas wsDest, i, r
        Usage_Inc_AllInv CellText(vals(r, 4)), 1
        i = i + 1
    Next j
    packLines = nI

    With wsDest.Columns("B:L")
        .HorizontalAlignment = xlCenter
    End With
    wsDest.Columns("C").NumberFormat = "$#,##0.00"
    wsDest.Columns("D").NumberFormat = "0.00%"
    wsDest.Columns("J").NumberFormat = "$#,##0.00"
    wsDest.Columns("K").NumberFormat = "$#,##0.00"
    WriteTotals wsDest, exN + nI + 1
    SortActiveSheetByColumnA
    RewriteFormulas wsDest
    wsDest.Columns("A:L").AutoFit
    SummarizeAllSheets
    Application.Calculate

    ' ---- top up with the normal engine (and the account credit items)
    gAppend = True
    gNoCredit = True
    gSilent = True
    gNote = ""
    BuildOrderTab fbaOnly
    gSilent = False
    noteTxt = gNote
    gNote = ""
    Application.ScreenUpdating = True

    ptsAfter = CountedPoints(wsDest, CountOrderRows(wsDest) + 1)
    msg = PackName(p) & " filled: " & packLines & " pack items for $" & Format(price, "0.00") & " (" & packPts & " points)."
    If nLocalSkipped > 0 Then msg = msg & vbCrLf & nLocalSkipped & " local-only item(s) left out; the pack price was split between the others."
    If nNoAsin > 0 Then msg = msg & vbCrLf & nNoAsin & " pack item(s) have no ASIN and were skipped."
    msg = msg & vbCrLf & "The order now has " & CountOrderRows(wsDest) & " products and " & ptsAfter & " counted points."
    If Len(noteTxt) > 0 Then msg = msg & vbCrLf & noteTxt
    MsgBox msg, vbInformation, "Fill Packs"
End Sub

' old macro name, kept so nothing that calls it breaks
Public Sub Fill_Pack_Products()
    Fill_Packs
End Sub











'=====================================================================================
' MENU BUTTONS (tab "Menu", tab "Summary" and every order tab)
'=====================================================================================
Public Sub Update_Amazon_Data()
    On Error GoTo failed
    Application.Run "RefreshFromAmazon"
    Exit Sub
failed:
    MsgBox "The Amazon data update could not run: " & Err.Description, vbExclamation, "Update Amazon Data"
End Sub

' orange / yellow / blue (blue = anything else): the scan picks the proxy city from it (orange = Vancouver, yellow = Toronto, blue = southern California)
Private Function TabColourName(ws As Worksheet) As String
    Dim c As Long, g As Long
    TabColourName = "blue"
    On Error GoTo done
    If ws.Tab.ColorIndex = xlColorIndexNone Then GoTo done
    c = ws.Tab.Color
    g = (c \ 256) Mod 256
    If TabKind(ws) = 1 Then
        If g >= 225 Then TabColourName = "yellow" Else TabColourName = "orange"
    End If
done:
End Function

' the sheet with the product table an order tab reads: Canadian tabs (orange / yellow) use MelaleucaCA (the same table with the points of the Canadian store
' - made by Sync_Canada_Points), every other tab uses Melaleuca
Public Function MelFor(ws As Worksheet) As String
    Dim s As Worksheet
    MelFor = "Melaleuca"
    On Error GoTo done
    If TabColourName(ws) <> "blue" Then
        Set s = ThisWorkbook.Worksheets("MelaleucaCA")
        MelFor = "MelaleucaCA"
    End If
done:
End Function

' writes feed\mel_tabs.txt : number, tab name, kind (1 = FBA only, 2 = all inventory), colour of every coloured order tab, in tab order (tab 1 = first coloured tab)
Public Sub Export_Order_Tabs()
    Dim wb As Workbook, ws As Worksheet, s As Long, n As Long, t As String, st As Object
    Set wb = ThisWorkbook
    For s = FirstOrderIdx() To wb.Sheets.count
        Set ws = wb.Sheets(s)
        If IsOrderTab(ws) Then
            If TabKind(ws) > 0 Then
                n = n + 1
                t = t & n & vbTab & ws.Name & vbTab & TabKind(ws) & vbTab & TabColourName(ws) & vbLf
            End If
        End If
    Next s
    If Dir("C:\AmazonFeed\feed", vbDirectory) = "" Then MkDir "C:\AmazonFeed\feed"
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.WriteText t
    st.SaveToFile "C:\AmazonFeed\feed\mel_tabs.txt", 2
    st.Close
End Sub

Public Sub Update_Melaleuca_Data()
    On Error GoTo failed
    Application.Run "Update_Melaleuca_Prices"
    Application.Run "Scan_Account_Offers"
    Exit Sub
failed:
    MsgBox "The Melaleuca data update could not run: " & Err.Description, vbExclamation, "Update Melaleuca Data"
End Sub

' erases the Summary tab and every order tab after it (replaces "clear sheets from 5 onward": the tabs moved, so it starts at the Summary tab)
Public Sub Clear_Summary_And_Orders()
    Dim i As Long, first As Long, ans As Long
    Dim cr(1 To 200) As Variant
    first = FirstOrderIdx() - 1
    If first < 1 Or UCase$(ThisWorkbook.Sheets(first).Name) <> "SUMMARY" Then first = FirstOrderIdx()
    ans = MsgBox("This erases the Summary tab and every order tab (products, quantities and totals)." & vbCrLf & _
                 "The Menu, Melaleuca, FBA and Inventory tabs are not touched." & vbCrLf & vbCrLf & "Continue?", _
                 vbYesNo + vbExclamation, "Clear Sheets From Summary and Orders")
    If ans <> vbYes Then Exit Sub

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    ' every order tab keeps its own account credit amount
    For i = first To ThisWorkbook.Sheets.count
        If IsOrderTab(ThisWorkbook.Sheets(i)) Then cr(i) = ThisWorkbook.Sheets(i).Range(CREDIT_CELL).Value
    Next i
    For i = first To ThisWorkbook.Sheets.count
        With ThisWorkbook.Sheets(i)
            .Cells.Clear
        End With
    Next i
    For i = first To ThisWorkbook.Sheets.count
        If IsOrderTab(ThisWorkbook.Sheets(i)) Then
            If IsNumeric(cr(i)) And Not IsEmpty(cr(i)) Then
                WriteCreditCell ThisWorkbook.Sheets(i), CDbl(cr(i))
            Else
                WriteCreditCell ThisWorkbook.Sheets(i), DefaultCreditFor(ThisWorkbook.Sheets(i))
            End If
        End If
    Next i
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    MsgBox "The Summary tab and all order tabs have been cleared.", vbInformation, "Clear Sheets From Summary and Orders"
End Sub

Public Sub Generate_All_Orders()
    Create_All_Orders
End Sub

Public Sub Summarize_All_Tabs()
    Application.ScreenUpdating = False
    SummarizeAllSheets
    Application.Calculate
    Application.ScreenUpdating = True
    MsgBox "The Summary tab was updated from all the order tabs.", vbInformation, "Summarize All Tabs"
End Sub

' asks before replacing an order that already exists on the tab (used by the per-tab Create buttons)
Private Function ConfirmReplace(ByVal what As String) As Boolean
    Dim ws As Worksheet, n As Long, ans As Long
    Set ws = ActiveSheet
    If Not IsOrderTab(ws) Then
        MsgBox "Click on an order tab first, then press the button.", vbExclamation, what
        Exit Function
    End If
    n = CountOrderRows(ws)
    If n > 0 Then
        ans = MsgBox("This tab already has an order (" & n & " products). Replace it with a new one?", vbYesNo + vbQuestion, what)
        If ans <> vbYes Then Exit Function
    End If
    ConfirmReplace = True
End Function

Public Sub Create_All_Inventory_Order()
    If ConfirmReplace("Create a All Inventory Order") Then BuildOrderTab False
End Sub

Public Sub Create_FBA_Only_Order()
    If ConfirmReplace("Create a FBA Only Order") Then BuildOrderTab True
End Sub












'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================
'================================= ALL GOOD UP FROM HERE!!!!! =======================================











'Option Explicit

'=====================================================================================
' NEW ORDER ENGINE  (replaces the random bucket picking)
' - picks products by profit per point x sales speed x how much stock is still needed
' - keeps each order between 143 and 148 points
' - every order tab is built to differ from every other tab (max overlap about 50%)
' - same rules as before: one product per family (BB), FBA-only skips C="M" and food (BD),
'   quantity = set size (W) or 1, points = set points (X) or T x quantity
'=====================================================================================

Private Sub Notify(ByVal msg As String, Optional ByVal icon As Long = 64, Optional ByVal title As String = "Order generator")
    If gSilent Then
        If Len(gNote) > 0 Then gNote = gNote & " "
        gNote = gNote & msg
    Else
        MsgBox msg, icon, title
    End If
End Sub

' index of the first order tab = the tab right after "Summary" (the Menu tab moved everything, so it is looked up by name)
Private Function FirstOrderIdx() As Long
    Dim i As Long
    FirstOrderIdx = 5
    For i = 1 To ThisWorkbook.Sheets.count
        If UCase$(ThisWorkbook.Sheets(i).Name) = "SUMMARY" Then
            FirstOrderIdx = i + 1
            Exit Function
        End If
    Next i
End Function

' 1 = FBA-only tab (orange or yellow), 2 = all-inventory tab (blue), 0 = not coloured
Private Function TabKind(ws As Worksheet) As Long
    Dim c As Long, r As Long, g As Long, b As Long
    On Error GoTo noColour
    If ws.Tab.ColorIndex = xlColorIndexNone Then GoTo noColour
    c = ws.Tab.Color
    r = c Mod 256
    g = (c \ 256) Mod 256
    b = (c \ 65536) Mod 256
    If r >= 200 And g >= 100 And b <= 100 Then
        TabKind = 1
        Exit Function
    End If
    If b >= 180 And r <= 120 Then
        TabKind = 2
        Exit Function
    End If
noColour:
    TabKind = 0
End Function

Private Function IsOrderTab(ws As Worksheet) As Boolean
    IsOrderTab = (ws.Index >= FirstOrderIdx() And ws.Visible = xlSheetVisible And UCase$(ws.Name) <> "PICK_USAGE" And UCase$(ws.Name) <> "SUMMARY")
End Function

' formulas of one order row (i) for the Melaleuca row rr: set-aware Total WS / Profit / Points / flag
Private Sub SetRowFormulas(wsDest As Worksheet, ByVal i As Long, ByVal rr As Long)
    Dim a As String, p As String, qh As String
    Dim ms As String: ms = MelFor(wsDest)      ' Canadian (orange / yellow) tabs read the sheet MelaleucaCA = same table with the Canadian store's points
    a = CStr(i)
    p = CStr(i - 1)
    qh = "OR($Q" & a & "=0,$H" & a & "=""Pack"")"
    ' helper columns Q:X (hidden): everything is looked up by ASIN (column B), so sorting the rows never breaks the formulas
    ' O = set key chosen when the order was built ("" = the product's own key from Melaleuca!CE, a recipe key such as PAIN, or COUPON = coupon deal of the product)
    wsDest.Cells(i, 17).Formula = "=IFERROR(MATCH($B" & a & "," & ms & "!$D$2:$D$700,0),0)"
    wsDest.Cells(i, 25).Formula = "=IFERROR(MATCH($B" & a & ",$AE$2:$AE$250,0),0)"   ' > 0: this row uses the frozen account offer stored in AE:AI
    wsDest.Cells(i, 18).Formula = "=IF(" & qh & ","""",IF($Y" & a & ">0,INDEX($AF$2:$AF$250,$Y" & a & ")&"""",IF($O" & a & "=""COUPON"",""#""&$B" & a & ",IF($O" & a & "<>"""",$O" & a & ",INDEX(" & ms & "!$CE$2:$CE$700,$Q" & a & ")&""""))))"
    ' the cleaners combo (group CLEAN) is a set of 3, 4 or 5 cleaners: its size, price and points follow the units on the tab (table Melaleuca!CQ:CS)
    wsDest.Cells(i, 19).Formula = "=IF(" & qh & ",0,IF(AND($Y" & a & ">0,$R" & a & "<>""CLEAN""),N(INDEX($AG$2:$AG$250,$Y" & a & ")),IF($O" & a & "=""COUPON"",N(INDEX(" & ms & "!$CA$2:$CA$700,$Q" & a & ")),IF($O" & a & "<>"""",N(IFERROR(INDEX(" & ms & "!$CM$2:$CM$201,MATCH($O" & a & "," & ms & "!$CJ$2:$CJ$201,0)),0)),IF($R" & a & "=""CLEAN"",IF(AND(SUMIF($R$2:$R$250,$R" & a & ",$I$2:$I$250)>=3,SUMIF($R$2:$R$250,$R" & a & ",$I$2:$I$250)<=5),SUMIF($R$2:$R$250,$R" & a & ",$I$2:$I$250),0),N(INDEX(" & ms & "!$CF$2:$CF$700,$Q" & a & ")))))))"
    wsDest.Cells(i, 20).Formula = "=IF($Q" & a & "=0,0,IF(AND($Y" & a & ">0,$R" & a & "<>""CLEAN""),N(INDEX($AH$2:$AH$250,$Y" & a & ")),IF($O" & a & "=""COUPON"",N(INDEX(" & ms & "!$CB$2:$CB$700,$Q" & a & ")),IF($O" & a & "<>"""",IFERROR(INDEX(" & ms & "!$CN$2:$CN$201,MATCH($O" & a & "," & ms & "!$CJ$2:$CJ$201,0))/MAX(1,$S" & a & "),0),IF($R" & a & "=""CLEAN"",IFERROR(INDEX(" & ms & "!$CR$2:$CR$4,MATCH($S" & a & "," & ms & "!$CQ$2:$CQ$4,0))/$S" & a & "+MAX(0,N(INDEX(" & ms & "!$U$2:$U$700,$Q" & a & "))-" & ms & "!$CR$6),0),N(INDEX(" & ms & "!$CG$2:$CG$700,$Q" & a & ")))))))"
    wsDest.Cells(i, 21).Formula = "=IF($Q" & a & "=0,0,IF(AND($Y" & a & ">0,$R" & a & "<>""CLEAN""),N(INDEX($AI$2:$AI$250,$Y" & a & ")),IF($O" & a & "=""COUPON"",N(INDEX(" & ms & "!$CC$2:$CC$700,$Q" & a & ")),IF($O" & a & "<>"""",IFERROR(INDEX(" & ms & "!$CO$2:$CO$201,MATCH($O" & a & "," & ms & "!$CJ$2:$CJ$201,0)),0),IF($R" & a & "=""CLEAN"",IFERROR(INDEX(" & ms & "!$CS$2:$CS$4,MATCH($S" & a & "," & ms & "!$CQ$2:$CQ$4,0)),0),N(INDEX(" & ms & "!$CH$2:$CH$700,$Q" & a & ")))))))"
    wsDest.Cells(i, 22).Formula = "=IF($Q" & a & "=0,0,N(INDEX(" & ms & "!$U$2:$U$700,$Q" & a & ")))"
    wsDest.Cells(i, 23).Formula = "=IF($Q" & a & "=0,0,N(INDEX(" & ms & "!$T$2:$T$700,$Q" & a & ")))"
    ' X = units of this row that are covered by a full set (units of the same group are counted together, in row order)
    wsDest.Cells(i, 24).Formula = "=IF(OR($R" & a & "="""",$S" & a & "<=0),0,MAX(0,MIN(SUMIF($R$1:$R" & p & ",$R" & a & ",$I$1:$I" & p & ")+$I" & a & _
        ",INT(SUMIF($R$2:$R$250,$R" & a & ",$I$2:$I$250)/$S" & a & ")*$S" & a & ")-MIN(SUMIF($R$1:$R" & p & ",$R" & a & ",$I$1:$I" & p & _
        "),INT(SUMIF($R$2:$R$250,$R" & a & ",$I$2:$I$250)/$S" & a & ")*$S" & a & ")))"
    wsDest.Cells(i, 10).Formula = "=IF($S" & a & ">0,$X" & a & "*$T" & a & "+($I" & a & "-$X" & a & ")*$V" & a & ",$I" & a & "*$C" & a & ")"
    wsDest.Cells(i, 11).Formula = "=$C" & a & "*$D" & a & "*$I" & a & "+$I" & a & "*$C" & a & "-$J" & a
    ' points are whole numbers: the points of a set are shared out unit by unit (e.g. 4 points for 3 units = 2 + 1 + 1)
    wsDest.Cells(i, 12).Formula = "=IF($S" & a & ">0,INT((SUMIF($R$1:$R" & p & ",$R" & a & ",$X$1:$X" & p & ")+$X" & a & ")*$U" & a & "/$S" & a & ")-INT(SUMIF($R$1:$R" & p & ",$R" & a & ",$X$1:$X" & p & ")*$U" & a & "/$S" & a & ")+($I" & a & "-$X" & a & ")*$W" & a & ",$W" & a & "*$I" & a & ")"
    wsDest.Cells(i, 13).Formula = "=IF($X" & a & ">0,""Discounted"","""")"
End Sub

' rewrites the formulas of every product row of an order tab (after sorting / editing) and hides the helper columns
Private Sub RewriteFormulas(ws As Worksheet)
    Dim r As Long
    r = 2
    Do While Len(CellText(ws.Cells(r, 2).Value)) > 0 And r < 250
        SetRowFormulas ws, r, 0
        r = r + 1
    Loop
    ws.Range("Q1:X1").Value = Array("src", "group", "set n", "set unit", "set pts", "single $", "single pts", "in sets")
    ws.Range("Q1:X250").Font.Color = RGB(150, 150, 150)
    ws.Columns("Q:X").Hidden = True
    ws.Range("Y1").Value = "frozen"
    ws.Range("AE1:AI1").Value = Array("asin", "key", "n", "unit", "pts")
    ws.Range("Y1:AI250").Font.Color = RGB(150, 150, 150)
    ws.Columns("Y").Hidden = True
    ws.Columns("AE:AI").Hidden = True
    ws.Cells(1, 15).Value = "set key"
    ws.Columns("O").Hidden = True
End Sub

' blank row after the last product, then the TOTAL row
Private Sub WriteTotals(ws As Worksheet, ByVal lastProd As Long)
    Dim t As Long
    t = lastProd + 2
    ws.Rows(lastProd + 1).ClearContents
    ws.Cells(t, 1).Value = "TOTAL"
    RefreshTotals ws, t
    With ws.Rows(t)
        .Font.Bold = True
        .HorizontalAlignment = xlCenter
        .Columns("C").NumberFormat = "$#,##0.00"
        .Columns("D").NumberFormat = "0.00%"
        .Columns("J:K").NumberFormat = "$#,##0.00"
    End With
    ws.Cells(t, 1).HorizontalAlignment = xlLeft
End Sub

' sum formulas of the TOTAL row (row t). Points leave out the items marked "Credit" (paid with the account credit).
Private Sub RefreshTotals(ws As Worksheet, ByVal t As Long)
    ws.Cells(t, 9).Formula = "=SUM(I2:I" & t - 1 & ")"
    ws.Cells(t, 10).Formula = "=SUM(J2:J" & t - 1 & ")"
    ws.Cells(t, 11).Formula = "=SUM(K2:K" & t - 1 & ")"
    ws.Cells(t, 12).Formula = "=SUM(L2:L" & t - 1 & ")-SUMIF(N2:N" & t - 1 & ",""Credit*"",L2:L" & t - 1 & ")"
    ws.Cells(t + 1, 1).ClearContents
End Sub

Private Function CellText(ByVal v As Variant) As String
    If IsError(v) Then
        CellText = ""
    ElseIf IsNull(v) Then
        CellText = ""
    Else
        CellText = Trim$(CStr(v))
    End If
End Function

' number of product rows on an order tab (contiguous from row 2, until the first blank ASIN)
Private Function CountOrderRows(ws As Worksheet) As Long
    Dim r As Long
    r = 2
    Do While Len(CellText(ws.Cells(r, 2).Value)) > 0 And r < 400
        r = r + 1
    Loop
    CountOrderRows = r - 2
End Function

' points of the order that count towards the 143-148 target (items marked Credit are left out)
Private Function CountedPoints(ws As Worksheet, ByVal lastProd As Long) As Double
    Dim r As Long
    For r = 2 To lastProd
        If Len(CellText(ws.Cells(r, 2).Value)) > 0 Then
            If Not IsCreditRow(ws, r) Then CountedPoints = CountedPoints + SafeDbl(ws.Cells(r, 12).Value)
        End If
    Next r
End Function

Private Function PackRowCount(ws As Worksheet, ByVal lastProd As Long) As Long
    Dim r As Long
    For r = 2 To lastProd
        If CellText(ws.Cells(r, 8).Value) = "Pack" Then PackRowCount = PackRowCount + 1
    Next r
End Function

Private Function CreditRowCount(ws As Worksheet, ByVal lastProd As Long) As Long
    Dim r As Long
    For r = 2 To lastProd
        If IsCreditRow(ws, r) Then CreditRowCount = CreditRowCount + 1
    Next r
End Function

' account credit (in dollars) used per order; the number is typed on the Menu tab. 0 = do not use credit.
' usual account credit: US = 10.42. Canada = 13.12 Canadian dollars, but the sheet counts US dollars (prices are about 1.26-1.30 times higher in Canada) and the store refuses
' the second credit line when the first one leaves less than about a dollar of credit over, so Canadian tabs plan with 9.30 (= about 12.10 Canadian dollars)
Private Function DefaultCreditFor(ws As Worksheet) As Double
    DefaultCreditFor = DEFAULT_CREDIT
    If TabColourName(ws) <> "blue" Then DefaultCreditFor = 9.3
End Function

Public Function CreditAmount(ws As Worksheet) As Double
    Dim v As Variant
    v = ws.Range(CREDIT_CELL).Value
    If IsError(v) Then v = Empty
    If IsEmpty(v) Or Len(CStr(v)) = 0 Then
        CreditAmount = DefaultCreditFor(ws)
        WriteCreditCell ws, CreditAmount         ' empty = not set yet: use the usual credit
    ElseIf IsNumeric(v) Then
        CreditAmount = CDbl(v)
        If Abs(CreditAmount - DEFAULT_CREDIT) < 0.001 And TabColourName(ws) <> "blue" Then      ' a Canadian tab still holding the US default: use the Canadian one
            CreditAmount = DefaultCreditFor(ws)
            WriteCreditCell ws, CreditAmount
        End If
        If CreditAmount < 0 Then CreditAmount = 0
    Else
        CreditAmount = 0
    End If
End Function

' label (P8) and amount (P9) of the account credit on an order tab; 0 = new account without credit
Private Sub WriteCreditCell(ws As Worksheet, ByVal amount As Double)
    ws.Range(CREDIT_LABEL).Value = "Account credit ($)"
    ws.Range(CREDIT_LABEL).Font.Bold = True
    ws.Range(CREDIT_LABEL).Font.Size = 9
    ws.Range(CREDIT_LABEL).Font.Color = RGB(31, 56, 100)
    ws.Range(CREDIT_CELL).Value = amount
    ws.Range(CREDIT_CELL).NumberFormat = "$#,##0.00"
    ws.Range(CREDIT_CELL).Interior.Color = RGB(255, 242, 204)
    ws.Range(CREDIT_CELL).Font.Bold = True
    ws.Range(CREDIT_CELL).HorizontalAlignment = xlCenter
End Sub

' clears the order rows of a tab (products, totals, helper columns) without touching the buttons area / credit cell
Private Sub ClearOrderRows(ws As Worksheet, ByVal r1 As Long, ByVal r2 As Long)
    ws.Range(ws.Cells(r1, 1), ws.Cells(r2, 15)).ClearContents
    ws.Range(ws.Cells(r1, 17), ws.Cells(r2, 25)).ClearContents
    If r1 <= 2 Then ws.Range(ws.Cells(2, 31), ws.Cells(260, 35)).ClearContents
End Sub

' marks an order row: "Pack" in column H, "Credit 1" / "Credit 2" in column N
Private Sub TagRow(ws As Worksheet, ByVal i As Long, ByVal tag As String)
    If Left$(tag, 6) = "Credit" Then
        ws.Cells(i, 14).Value = tag
        With ws.Cells(i, 14)
            .HorizontalAlignment = xlCenter
            .Font.Bold = True
            .Font.Color = RGB(0, 128, 64)
        End With
    Else
        ws.Cells(i, 8).Value = tag
        With ws.Cells(i, 8)
            .HorizontalAlignment = xlCenter
            .Font.Bold = True
            If tag = "Pack" Then .Font.Color = RGB(0, 102, 204)
        End With
    End If
End Sub

'=====================================================================================
' CREDIT ITEMS: the monthly account credit is applied to two products of the order:
'   1) the product whose price is closest to the credit amount but not above it (the credit pays it completely), and
'   2) the product (or set of the same product) with the most points.
' Their points are not counted in the 143-148 target, so more products fit in the order.
' vals = Melaleuca A:CH values. Returns the Melaleuca rows (0 = none found).
'=====================================================================================
Private Sub PickCreditRows(wb As Workbook, wsDest As Worksheet, vals As Variant, ByVal lastR As Long, ByVal fbaOnly As Boolean, _
                           exA() As String, ByVal nEx As Long, exF() As String, ByVal nExF As Long, _
                           ByRef rCheap As Long, ByRef rExp As Long, ByRef qExp As Long)
    Dim k As Long, j As Long, ok As Boolean, nm As String, a As String, typ As String, fda As String
    Dim pr As Double, sc As Double, pt As Double, u As Double, vv As Double, n As Long, key As String, fam As String
    Dim grpFree As Boolean, v As Double, bestV As Double, uses As Long, credit As Double, famCheap As String
    rCheap = 0
    rExp = 0
    qExp = 1
    credit = CreditAmount(wsDest)
    If credit <= 0 Then Exit Sub
    ' ---- cheap product
    For k = 2 To lastR
        nm = CellText(vals(k, 1))
        a = CellText(vals(k, 4))
        If Len(nm) > 0 And Len(a) > 0 Then
            ok = True
            typ = UCase$(CellText(vals(k, 3)))
            fda = CellText(vals(k, 56))
            If fbaOnly Then
                If typ = "M" Then ok = False
                If Len(fda) > 0 And fda <> "0" Then ok = False
            End If
            pr = SafeDbl(vals(k, 13))
            If pr < 1 Or pr > 100 Then ok = False
            sc = SafeDbl(vals(k, 72))
            pt = SafeDbl(vals(k, 69))
            If sc <= 0 Or pt <= 0 Or pt > PTS_HI Then ok = False
            u = SafeDbl(vals(k, 21))
            If u <= 0 Or u > credit Then ok = False
            If SafeDbl(vals(k, 22)) > 0 Then ok = False      ' no credit on discounted (Special Offers) products
            If gPendOn Then
                If SafeDbl(vals(k, 67)) - gPend(k) <= 0 Then ok = False
            End If
            n = CLng(SafeDbl(vals(k, 84)))
            key = CellText(vals(k, 83))
            grpFree = (n <= 1)
            If Not grpFree Then ok = False
            If ok Then
                For j = 1 To nEx
                    If exA(j) = a Then
                        ok = False
                        Exit For
                    End If
                Next j
            End If
            fam = CellText(vals(k, 54))
            If ok And Len(fam) > 0 Then
                For j = 1 To nExF
                    If exF(j) = fam Then
                        ok = False
                        Exit For
                    End If
                Next j
            End If
            If ok Then
                uses = TabUseCount(wb, wsDest, a)
                v = u * (0.95 + 0.1 * Rnd()) / (1 + 0.4 * uses)
                If v > bestV Then
                    bestV = v
                    rCheap = k
                End If
            End If
        End If
    Next k
    If rCheap > 0 Then famCheap = CellText(vals(rCheap, 54))
    ' ---- not discounted product with the most points
    bestV = 0
    For k = 2 To lastR
        If k <> rCheap Then
            nm = CellText(vals(k, 1))
            a = CellText(vals(k, 4))
            If Len(nm) > 0 And Len(a) > 0 Then
                ok = True
                typ = UCase$(CellText(vals(k, 3)))
                fda = CellText(vals(k, 56))
                If fbaOnly Then
                    If typ = "M" Then ok = False
                    If Len(fda) > 0 And fda <> "0" Then ok = False
                End If
                pr = SafeDbl(vals(k, 13))
                If pr < 1 Or pr > 100 Then ok = False
                sc = SafeDbl(vals(k, 72))
                pt = SafeDbl(vals(k, 69))
                If sc <= 0 Or pt <= 0 Or pt > PTS_HI Then ok = False
                If gPendOn Then
                    If SafeDbl(vals(k, 67)) - gPend(k) <= 0 Then ok = False
                End If
                If SafeDbl(vals(k, 22)) > 0 Then ok = False      ' no credit on discounted products
                n = CLng(SafeDbl(vals(k, 84)))
                key = CellText(vals(k, 83))
                grpFree = (n <= 1) Or (Left$(key, 1) = "#" And n <= 2)      ' a product or a set of the same product ("big sets" count)
                If Not grpFree Then ok = False
                fam = CellText(vals(k, 54))
                If ok And Len(fam) > 0 And fam = famCheap Then ok = False
                If ok Then
                    For j = 1 To nEx
                        If exA(j) = a Then
                            ok = False
                            Exit For
                        End If
                    Next j
                End If
                If ok And Len(fam) > 0 Then
                    For j = 1 To nExF
                        If exF(j) = fam Then
                            ok = False
                            Exit For
                        End If
                    Next j
                End If
                If ok Then
                    uses = TabUseCount(wb, wsDest, a)
                    v = (pt + 0.01 * sc) * (0.95 + 0.1 * Rnd()) / (1 + 0.2 * uses)
                    If v > bestV Then
                        bestV = v
                        rExp = k
                        qExp = 1
                        If Left$(key, 1) = "#" And n >= 2 Then qExp = n
                    End If
                End If
            End If
        End If
    Next k
End Sub

'=====================================================================================
' SET RECIPES (savings packs that mix products)
'   Melaleuca group table CJ:CO (key, name, pack item, units, price, points) + CT = slots ("A2" = 2 units from slot A, "A1,B1" = one from A and one from B)
'   + CU = label type (WITH = "Set with <the other product>", OF = "Set of 2")
'   Members table DE:DI = group key, ASIN, slot, short name used in the notes, product name.
'   A product may be a member of several recipes. On an order tab the recipe used by a row is written in column O (hidden).
'=====================================================================================
Private Sub LoadRecipes(wsSrc As Worksheet)
    Dim v As Variant, r As Long, k As String
    gRecN = 0
    gMemN = 0
    v = wsSrc.Range(wsSrc.Cells(2, 88), wsSrc.Cells(201, 113)).Value
    For r = 1 To 200
        k = UCase$(CellText(v(r, 1)))
        If Len(k) > 0 And Len(CellText(v(r, 11))) > 0 And gRecN < 120 Then
            gRecN = gRecN + 1
            gRecKey(gRecN) = k
            gRecName(gRecN) = CellText(v(r, 2))
            gRecUnits(gRecN) = CLng(SafeDbl(v(r, 4)))
            gRecPrice(gRecN) = SafeDbl(v(r, 5))
            gRecPts(gRecN) = SafeDbl(v(r, 6))
            gRecSlots(gRecN) = UCase$(CellText(v(r, 11)))
            gRecLabel(gRecN) = UCase$(CellText(v(r, 12)))
        End If
        k = UCase$(CellText(v(r, 22)))
        If Len(k) > 0 And Len(CellText(v(r, 23))) > 0 And gMemN < 400 Then
            gMemN = gMemN + 1
            gMemKey(gMemN) = k
            gMemAsin(gMemN) = CellText(v(r, 23))
            gMemSlot(gMemN) = UCase$(CellText(v(r, 24)))
            gMemNote(gMemN) = CellText(v(r, 25))
        End If
    Next r
End Sub

Private Function RecIdx(ByVal key As String) As Long
    Dim i As Long
    RecIdx = 0
    If Len(key) = 0 Then Exit Function
    For i = 1 To gRecN
        If gRecKey(i) = UCase$(key) Then
            RecIdx = i
            Exit Function
        End If
    Next i
End Function

' slot letter -> 1..5 (0 = none)
Private Function SlotNo(ByVal s As String) As Long
    SlotNo = 0
    If Len(s) = 0 Then Exit Function
    If s = "COUPON" Then Exit Function
    SlotNo = Asc(UCase$(Left$(s, 1))) - 64
    If SlotNo < 1 Or SlotNo > 5 Then SlotNo = 0
End Function

' units a recipe needs from slot number sl (1..5)
Private Function RecSlotNeed(ByVal ri As Long, ByVal sl As Long) As Long
    Dim p As Long, ch As String, n As Long, tok As String, parts() As String, i As Long
    RecSlotNeed = 0
    If ri < 1 Then Exit Function
    parts = Split(gRecSlots(ri), ",")
    For i = LBound(parts) To UBound(parts)
        tok = Trim$(parts(i))
        If Len(tok) >= 1 Then
            If SlotNo(Left$(tok, 1)) = sl Then
                n = 1
                If Len(tok) > 1 Then n = CLng(Val(Mid$(tok, 2)))
                RecSlotNeed = RecSlotNeed + n
            End If
        End If
    Next i
End Function

' short name of a product inside a recipe (for the "Set with ..." notes)
Private Function MemberNote(ByVal key As String, ByVal asin As String, ByVal prodName As String) As String
    Dim i As Long, p As Long, s As String
    For i = 1 To gMemN
        If gMemKey(i) = UCase$(key) And gMemAsin(i) = asin Then
            If Len(gMemNote(i)) > 0 Then
                MemberNote = gMemNote(i)
                Exit Function
            End If
        End If
    Next i
    s = Trim$(prodName)
    p = InStrRev(s, " - ")
    If p > 0 Then s = Trim$(Mid$(s, p + 3))
    MemberNote = s
End Function

' score of a product when it is bought inside a recipe / coupon (units and total price/points of the whole deal)
Private Function AltScore(vals As Variant, ByVal r As Long, ByVal baseScore As Double, ByVal price As Double, ByVal units As Double, ByVal pts As Double, ByVal remNeed As Double) As Double
    Dim bs0 As Double, bp0 As Double, e As Double, g As Double, br As Double, bs1 As Double, f0 As Double, f1 As Double
    AltScore = 0
    If baseScore <= 0 Or pts <= 0 Or units < 1 Then Exit Function
    bs0 = SafeDbl(vals(r, 71))
    bp0 = SafeDbl(vals(r, 68))
    If bp0 < 1 Then bp0 = 1
    e = MoneyVal(vals(r, 5))
    g = MoneyVal(vals(r, 7))
    br = (e - g) * units - price
    If bs0 <= 0 Or br <= 0 Then Exit Function
    bs1 = br / pts
    f0 = remNeed / bp0
    If f0 > 1 Then f0 = 1
    f1 = remNeed / units
    If f1 > 1 Then f1 = 1
    If f0 <= 0 Then f0 = 1
    AltScore = baseScore * (bs1 / bs0) * (f1 / f0)
End Function

' Finds the other products of a recipe for Add_New_Product. Returns True when the set can be completed.
' outRow/outQty: Melaleuca rows and quantities of the whole set (index 1 = the lead product).
Private Function FindRecipePartners(wb As Workbook, wsDest As Worksheet, vals As Variant, ByVal lastR As Long, ByVal fbaOnly As Boolean, ByVal ri As Long, _
                                    ByVal leadRow As Long, ByVal leadSlotNo As Long, onAsin() As String, ByVal nOn As Long, onFam() As String, ByVal nFam As Long, _
                                    outRow() As Long, outQty() As Long, ByRef nOut As Long) As Boolean
    Dim slotRem(1 To 5) As Long
    Dim outSlot(1 To 8) As Long
    Dim sl As Long, remTot As Long, nKinds As Long, lastSl As Long, mi As Long, k As Long, j As Long, bestMi As Long, bestRow As Long
    Dim bestV As Double, v As Double, ok As Boolean, a As String, typ As String, fda As String, fam As String, pr As Double, sc As Double
    Dim capRoom As Long
    FindRecipePartners = False
    nOut = 1
    outRow(1) = leadRow
    outQty(1) = 1
    outSlot(1) = leadSlotNo
    For sl = 1 To 5
        slotRem(sl) = RecSlotNeed(ri, sl)
        remTot = remTot + slotRem(sl)
    Next sl
    If leadSlotNo < 1 Then Exit Function
    If slotRem(leadSlotNo) <= 0 Then Exit Function
    slotRem(leadSlotNo) = slotRem(leadSlotNo) - 1
    remTot = remTot - 1
    Do While remTot > 0
        bestV = 0
        bestRow = 0
        bestMi = 0
        For mi = 1 To gMemN
            If gMemKey(mi) = gRecKey(ri) Then
                sl = SlotNo(gMemSlot(mi))
                If sl > 0 Then
                    If slotRem(sl) > 0 Then
                        k = 0
                        For j = 2 To lastR
                            If CellText(vals(j, 4)) = gMemAsin(mi) Then
                                k = j
                                Exit For
                            End If
                        Next j
                        If k > 0 Then
                            ok = True
                            a = gMemAsin(mi)
                            For j = 1 To nOut
                                If CellText(vals(outRow(j), 4)) = a Then ok = False
                            Next j
                            typ = UCase$(CellText(vals(k, 3)))
                            fda = CellText(vals(k, 56))
                            If fbaOnly Then
                                If typ = "M" Then ok = False
                                If Len(fda) > 0 And fda <> "0" Then ok = False
                            End If
                            pr = SafeDbl(vals(k, 13))
                            If pr < 1 Or pr > 100 Then ok = False
                            If SafeDbl(vals(k, 22)) > 0 Then ok = False         ' a product with its own discount is never part of a regular set
                            sc = SafeDbl(vals(k, 72))
                            If sc <= 0 Then ok = False
                            If ok Then
                                For j = 1 To nOn
                                    If onAsin(j) = a Then ok = False
                                Next j
                            End If
                            If ok Then
                                fam = CellText(vals(k, 54))
                                If Len(fam) > 0 Then
                                    For j = 1 To nFam
                                        If onFam(j) = fam Then ok = False
                                    Next j
                                End If
                            End If
                            If ok Then
                                v = sc / (1 + 0.12 * TabUseCount(wb, wsDest, a))
                                If v > bestV Then
                                    bestV = v
                                    bestRow = k
                                    bestMi = mi
                                End If
                            End If
                        End If
                    End If
                End If
            End If
        Next mi
        If bestRow = 0 Then Exit Do
        nOut = nOut + 1
        outRow(nOut) = bestRow
        outQty(nOut) = 1
        outSlot(nOut) = SlotNo(gMemSlot(bestMi))
        slotRem(outSlot(nOut)) = slotRem(outSlot(nOut)) - 1
        remTot = remTot - 1
    Loop
    If remTot > 0 Then
        ' the missing units can only be a 2nd unit of a product of the one slot that is left (never more than 2 of a product)
        nKinds = 0
        For sl = 1 To 5
            If slotRem(sl) > 0 Then
                nKinds = nKinds + 1
                lastSl = sl
            End If
        Next sl
        If nKinds <> 1 Then Exit Function
        capRoom = 0
        For j = 1 To nOut
            If outSlot(j) = lastSl Then capRoom = capRoom + 1
        Next j
        If capRoom < remTot Then Exit Function
        For j = 1 To nOut
            If remTot > 0 And outSlot(j) = lastSl Then
                outQty(j) = 2
                remTot = remTot - 1
            End If
        Next j
    End If
    FindRecipePartners = True
End Function


' discount type text from the sheet (column Y); numbers typed there by mistake are ignored
Private Function CleanDT(ByVal s As String) As String
    s = Trim$(s)
    CleanDT = ""
    If Len(s) = 0 Then Exit Function
    If IsNumeric(s) Then Exit Function
    CleanDT = s
End Function

' coupon group of a Melaleuca row ("" = the row is not a coupon deal): similar products of one deal share the group, only one of them is bought per tab
Private Function CouponGroupOf(vals As Variant, ByVal k As Long) As String
    Dim s As String
    CouponGroupOf = ""
    If LCase$(CellText(vals(k, 25))) <> "coupon" Then Exit Function
    If SafeDbl(vals(k, 22)) <= 0 Then Exit Function
    s = CellText(vals(k, 82))
    If Len(s) = 0 Then s = CellText(vals(k, 54))
    If Len(s) = 0 Then s = CellText(vals(k, 4))
    CouponGroupOf = "CPN:" & s
End Function


'=====================================================================================
' PER-ACCOUNT OFFERS (sheet "AccountOffers", filled by Import_Account_Offers from the store scan)
'   While one account's order is built, the Melaleuca tab (V:Y) temporarily shows ONLY the discounts that account really has.
'   Afterwards the prices of the order's rows are frozen on the tab itself (columns Y and AE:AI, hidden), and the Melaleuca tab is put back.
'   A tab that was never scanned keeps working on the Melaleuca tab as before.
'=====================================================================================
Private Function OverlayPush(wsTab As Worksheet) As Boolean
    Dim wa As Worksheet, wsSrc As Worksheet, lastA As Long, r As Long, i As Long, last As Long, found As Boolean
    Dim v As Variant, fv As Variant, o As Variant, asinA As Variant, a As String
    Dim couponsKnown As Boolean, coupSet As String
    If gOvOn Then Exit Function
    On Error Resume Next
    Set wa = ThisWorkbook.Sheets("AccountOffers")
    On Error GoTo 0
    If wa Is Nothing Then Exit Function
    lastA = wa.Cells(wa.Rows.count, 1).End(xlUp).Row
    If lastA < 2 Then Exit Function
    o = wa.Range(wa.Cells(1, 1), wa.Cells(lastA, 6)).Value
    For r = 2 To lastA
        If CellText(o(r, 1)) = wsTab.Name Then
            found = True
            ' the scan also read the coupons of this account: only those may be used (COUPONSCAN = they were read; Coupon lines = the products they belong to)
            If CellText(o(r, 3)) = "COUPONSCAN" Then couponsKnown = True
            If LCase$(CellText(o(r, 3))) = "coupon" Then coupSet = coupSet & "|" & CellText(o(r, 2)) & "|"
        End If
    Next r
    If Not found Then Exit Function
    Set wsSrc = ThisWorkbook.Sheets("MELALEUCA")
    last = SrcLastRow(wsSrc)
    If last < 2 Then Exit Function
    gOvLast = last
    gOvSave = wsSrc.Range(wsSrc.Cells(2, 22), wsSrc.Cells(last, 25)).Formula     ' formulas such as =9.23/2 are put back exactly
    v = wsSrc.Range(wsSrc.Cells(2, 22), wsSrc.Cells(last, 25)).Value
    fv = wsSrc.Range(wsSrc.Cells(2, 22), wsSrc.Cells(last, 25)).Formula
    asinA = wsSrc.Range(wsSrc.Cells(2, 4), wsSrc.Cells(last, 4)).Value
    For i = 1 To last - 1
        If SafeDbl(v(i, 1)) > 0 Then
            If LCase$(CellText(v(i, 4))) <> "coupon" Then
                fv(i, 1) = ""
                fv(i, 2) = ""
                fv(i, 3) = ""
                fv(i, 4) = ""
            ElseIf couponsKnown Then
                ' a coupon deal of the sheet: kept only when this account really has that coupon
                If InStr(coupSet, "|" & CellText(asinA(i, 1)) & "|") = 0 Then
                    fv(i, 1) = ""
                    fv(i, 2) = ""
                    fv(i, 3) = ""
                    fv(i, 4) = ""
                End If
            End If
        End If
    Next i
    For r = 2 To lastA
        If CellText(o(r, 1)) = wsTab.Name And CellText(o(r, 2)) <> "*" And LCase$(CellText(o(r, 3))) <> "coupon" Then
            a = CellText(o(r, 2))
            For i = 1 To last - 1
                If CellText(asinA(i, 1)) = a Then
                    fv(i, 1) = SafeDbl(o(r, 5))
                    fv(i, 2) = SafeDbl(o(r, 4))
                    fv(i, 3) = SafeDbl(o(r, 6))
                    fv(i, 4) = CellText(o(r, 3))
                End If
            Next i
        End If
    Next r
    wsSrc.Range(wsSrc.Cells(2, 22), wsSrc.Cells(last, 25)).Formula = fv
    gOvOn = True
    Application.Calculate
    OverlayPush = True
End Function

Private Sub OverlayPop()
    Dim wsSrc As Worksheet
    If Not gOvOn Then Exit Sub
    Set wsSrc = ThisWorkbook.Sheets("MELALEUCA")
    wsSrc.Range(wsSrc.Cells(2, 22), wsSrc.Cells(gOvLast, 25)).Formula = gOvSave
    gOvOn = False
    Application.Calculate
End Sub

' freezes, on the order tab, the set / price / points that each row has under the account's offers
Private Sub FreezeOffers(ws As Worksheet)
    Dim r As Long, n As Long, ov As String, rk As String
    Application.Calculate
    n = ws.Cells(ws.Rows.count, 31).End(xlUp).Row
    If n < 1 Then n = 1
    r = 2
    Do While Len(CellText(ws.Cells(r, 2).Value)) > 0 And r < 250
        If SafeDbl(ws.Cells(r, 17).Value) > 0 And SafeDbl(ws.Cells(r, 25).Value) = 0 And CellText(ws.Cells(r, 8).Value) <> "Pack" Then
            ov = CellText(ws.Cells(r, 15).Value)
            If Len(ov) = 0 Or ov = "COUPON" Then
                n = n + 1
                ws.Cells(n, 31).Value = CellText(ws.Cells(r, 2).Value)
                ws.Cells(n, 32).Value = CellText(ws.Cells(r, 18).Value)
                ws.Cells(n, 33).Value = SafeDbl(ws.Cells(r, 19).Value)
                ws.Cells(n, 34).Value = SafeDbl(ws.Cells(r, 20).Value)
                ws.Cells(n, 35).Value = SafeDbl(ws.Cells(r, 21).Value)
            End If
        End If
        r = r + 1
    Loop
    RewriteFormulas ws
    Application.Calculate
End Sub

Private Sub BuildOrderTab(ByVal fbaOnly As Boolean)
    Dim ws As Worksheet, mine As Boolean
    Set ws = ActiveSheet
    On Error GoTo bad
    mine = OverlayPush(ws)
    BuildOrderTabCore fbaOnly
    If mine Then
        If IsOrderTab(ws) And Len(CellText(ws.Cells(2, 2).Value)) > 0 Then FreezeOffers ws
        OverlayPop
    End If
    Exit Sub
bad:
    If mine Then OverlayPop
    gOk = False
    gNote = "stopped: " & Err.Description
End Sub

Public Sub Add_New_Product()
    Dim ws As Worksheet, mine As Boolean
    Set ws = ActiveSheet
    On Error GoTo bad
    mine = OverlayPush(ws)
    Add_New_ProductCore
    If mine Then
        If IsOrderTab(ws) And Len(CellText(ws.Cells(2, 2).Value)) > 0 Then FreezeOffers ws
        OverlayPop
    End If
    Exit Sub
bad:
    If mine Then OverlayPop
    MsgBox "Add product stopped: " & Err.Description, vbExclamation, "Add product"
End Sub

Private Sub BuildOrderTabCore(ByVal fbaOnly As Boolean)
    Dim wb As Workbook, wsSrc As Worksheet, wsDest As Worksheet, ws As Worksheet
    Dim colsToCopy As Variant
    Dim usableLastRow As Long, r As Long, k As Long, ti As Long, s As Long, j As Long
    Dim vals As Variant
    Dim nc As Long
    Dim cRow() As Long, cAsin() As String, cFam() As String
    Dim cScore() As Double, cPts() As Double, cKey() As String, cN() As Long
    Dim qtyOf() As Long, tagOf() As String, partnersLeft As Long, restrictKey As String, leadIdx As Long, nPartners As Long
    Dim needPts As Double, grpFam() As String, ngf As Long, q As Long
    Dim nm As String, asin As String, typ As String, fda As String, pr As Double, sc As Double, pt As Double
    Dim nt As Long, ntDim As Long, n As Long, rr As Long
    Dim tabA() As String, tabCnt() As Long
    Dim inTab() As Boolean, shr() As Long
    Dim isPicked() As Boolean, picked() As Long, np As Long
    Dim famList() As String, nf As Long
    Dim pts As Double, nest As Long, lim As Double, stage As Long
    Dim bestK As Long, bestV As Double, v As Double, ok As Boolean
    Dim i As Long, maxJ As Double, jac As Double, sumCnt As Long
    Dim appendMode As Boolean, exN As Long, exA() As String, exF() As String, nExF As Long
    Dim rCheap As Long, rExp As Long, qExp As Long, kc As Long, nCredit As Long, nCrNew As Long, noCredit As Boolean
    Dim usedKey() As String, nUsed As Long, kk As Long
    Dim leadPts As Double, tgtN As Long, szNow As Long, needQ As Long
    Dim cleanP(3 To 5) As Double
    Dim needU As Double, bpU As Double, remN As Double, f0 As Double, f1 As Double, keyX As String
    Dim cSlot() As String
    Dim cAlt() As Boolean
    Dim cRec() As Long
    Dim cCg() As String
    Dim ovrOf() As String
    Dim slotOf() As String
    Dim slotRem(1 To 5) As Long
    Dim deadKey(1 To 60) As String
    Dim nDead As Long
    Dim cpnUsed(1 To 40) As String
    Dim nCpn As Long
    Dim restrictRec As Long, remTot As Long, nKinds As Long, lastSl As Long, capRoom As Long, sl As Long
    Dim nCpnSet As Long
    Dim nBase As Long, c As Long, c0 As Long, mi As Long, ri As Long, uV As Double, wV As Double, xV As Double, ov As String, cgx As String

    appendMode = gAppend
    gAppend = False
    noCredit = gNoCredit
    gNoCredit = False
    Set wb = ThisWorkbook
    Set wsSrc = wb.Sheets("MELALEUCA")
    Set wsDest = ActiveSheet
    colsToCopy = Array(1, 4, 6, 9, 11, 12, 13) ' A, D, F, I, K, L, M
    gOk = False
    gPts = 0
    gLines = 0
    gOverlap = 0

    If wsDest.Index < FirstOrderIdx() Or UCase$(wsDest.Name) = "PICK_USAGE" Or UCase$(wsDest.Name) = "SUMMARY" Then
        Notify "Click on the order tab (the person's tab) first, then run this again.", vbExclamation
        Exit Sub
    End If

    Application.ScreenUpdating = False

    ' ---- Headers
    With wsDest
        .Cells(1, 2).Value = "ASIN"
        .Cells(1, 3).Value = "WS Price"
        .Cells(1, 4).Value = "Profit %"
        .Cells(1, 5).Value = "Rank"
        .Cells(1, 6).Value = "Stock"
        .Cells(1, 7).Value = "Priority"
        .Cells(1, 8).Value = "Notes"
        .Cells(1, 9).Value = "Quantity"
        .Cells(1, 10).Value = "Total WS"
        .Cells(1, 11).Value = "Total Profit"
        .Cells(1, 12).Value = "Points"
        .Cells(1, 14).Value = "Discount / Credit"
        .Cells(1, 15).Value = "set key"
        .Rows(1).Font.Bold = True
    End With

    ' ---- Usable last row (same rule as before)
    usableLastRow = SrcLastRow(wsSrc)

    ' ---- Clear this tab (or, when adding to an existing order, only the TOTAL rows under it).
    '      One tab at a time the Summary is refreshed so this tab's old order does not count;
    '      inside Create_All_Orders the Summary is rebuilt only once at the end (the units placed meanwhile are remembered in gPend).
    If appendMode Then
        exN = CountOrderRows(wsDest)
        ClearOrderRows wsDest, exN + 2, exN + 8
    Else
        ClearOrderRows wsDest, 2, 164
    End If
    If Not gPendOn Then
        SummarizeAllSheets
        Application.Calculate
    End If

    ' ---- Read candidates (needs Setup_NewPlan to have been run once)
    If CellText(wsSrc.Cells(1, 73).Value) <> "Priority (new)" Or CellText(wsSrc.Cells(1, 84).Value) <> "Set size (used)" Then
        Notify "Run Setup_NewPlan once first (it adds the new Max Stock / Priority / Set columns).", vbExclamation
        Application.ScreenUpdating = True
        Exit Sub
    End If
    vals = wsSrc.Range(wsSrc.Cells(1, 1), wsSrc.Cells(usableLastRow, 86)).Value
    cleanP(3) = 7
    cleanP(4) = 9
    cleanP(5) = 10
    For r = 2 To 4
        n = CLng(SafeDbl(wsSrc.Cells(r, 95).Value))
        If n >= 3 And n <= 5 Then
            If SafeDbl(wsSrc.Cells(r, 97).Value) > 0 Then cleanP(n) = SafeDbl(wsSrc.Cells(r, 97).Value)
        End If
    Next r

    ' ---- products already on the tab (add mode): they are not picked again, their families are blocked, their points count
    ReDim exA(1 To exN + 2)
    ReDim exF(1 To exN + 2)
    ReDim usedKey(1 To 40)
    If exN > 0 Then
        RewriteFormulas wsDest
        Application.Calculate
        For j = 1 To exN
            exA(j) = CellText(wsDest.Cells(j + 1, 2).Value)
            ov = CellText(wsDest.Cells(j + 1, 15).Value)
            For k = 2 To usableLastRow
                If CellText(vals(k, 4)) = exA(j) Then
                    cgx = CouponGroupOf(vals, k)
                    If Len(cgx) > 0 And nCpn < 40 Then
                        nCpn = nCpn + 1
                        cpnUsed(nCpn) = cgx
                    End If
                    keyX = CellText(vals(k, 83))
                    If ov = "COUPON" Then
                        keyX = ""
                    ElseIf Len(ov) > 0 Then
                        keyX = ov
                    End If
                    If Len(keyX) > 0 And Left$(keyX, 1) <> "#" And (SafeDbl(vals(k, 84)) > 1 Or Len(ov) > 0) Then
                        ok = True
                        For kk = 1 To nUsed
                            If usedKey(kk) = keyX Then ok = False
                        Next kk
                        If ok And nUsed < 40 Then
                            nUsed = nUsed + 1
                            usedKey(nUsed) = keyX
                        End If
                    End If
                    Exit For
                End If
            Next k
        Next j
        pts = CountedPoints(wsDest, exN + 1)
        nCredit = CreditRowCount(wsDest, exN + 1)
    End If

    ReDim cRow(1 To usableLastRow + 160)
    ReDim cAsin(1 To usableLastRow + 160)
    ReDim cFam(1 To usableLastRow + 160)
    ReDim cKey(1 To usableLastRow + 160)
    ReDim cN(1 To usableLastRow + 160)
    ReDim cScore(1 To usableLastRow + 160)
    ReDim cPts(1 To usableLastRow + 160)
    ReDim cSlot(1 To usableLastRow + 160)
    ReDim cAlt(1 To usableLastRow + 160)
    ReDim cRec(1 To usableLastRow + 160)
    ReDim cCg(1 To usableLastRow + 160)
    For r = 2 To usableLastRow
        nm = CellText(vals(r, 1))
        asin = CellText(vals(r, 4))
        If Len(nm) > 0 And Len(asin) > 0 Then
            typ = UCase$(CellText(vals(r, 3)))
            fda = CellText(vals(r, 56))
            ok = True
            If fbaOnly Then
                If typ = "M" Then ok = False
                If Len(fda) > 0 And fda <> "0" Then ok = False
            End If
            ' Priority 101 / price: a product at its Max Stock (priority 101) or without profit is never picked
            pr = SafeDbl(vals(r, 13))
            If pr < 1 Or pr > 100 Then ok = False
            sc = SafeDbl(vals(r, 72))
            pt = SafeDbl(vals(r, 69))
            If sc <= 0 Or pt <= 0 Or pt > PTS_HI Then ok = False
            ' units already placed on the other tabs of this run: a product that reached its Max Stock is out (same as priority 101)
            needU = SafeDbl(vals(r, 67))
            bpU = SafeDbl(vals(r, 68))
            If bpU < 1 Then bpU = 1
            remN = needU
            If gPendOn Then
                remN = needU - gPend(r)
                If remN <= 0 Then ok = False
            End If
            If ok And exN > 0 Then
                For j = 1 To exN
                    If exA(j) = asin Then
                        ok = False
                        Exit For
                    End If
                Next j
            End If
            If ok Then
                nc = nc + 1
                cRow(nc) = r
                cAsin(nc) = asin
                cFam(nc) = CellText(vals(r, 54))
                cKey(nc) = CellText(vals(r, 83))
                cN(nc) = CLng(SafeDbl(vals(r, 84)))
                cScore(nc) = sc
                If gPendOn Then
                    If gPend(r) > 0 Then
                        f0 = needU / bpU
                        If f0 > 1 Then f0 = 1
                        f1 = remN / bpU
                        If f1 > 1 Then f1 = 1
                        If f0 > 0 Then cScore(nc) = sc * f1 / f0
                    End If
                End If
                cPts(nc) = pt
            End If
        End If
    Next r


    ' ---- Alternatives of a candidate: the same product bought inside a recipe (savings pack that mixes products or a 2-pack) or as a coupon deal.
    '      Each alternative is its own candidate (own set key, units, points and score); once one of them is picked the product is out for all the others.
    LoadRecipes wsSrc
    nBase = nc
    For c0 = 1 To nBase
        r = cRow(c0)
        needU = SafeDbl(vals(r, 67))
        remN = needU
        If gPendOn Then remN = needU - gPend(r)
        cCg(c0) = CouponGroupOf(vals, r)
        For mi = 1 To gMemN
            If gMemAsin(mi) = cAsin(c0) And SafeDbl(vals(r, 22)) <= 0 Then
                ri = RecIdx(gMemKey(mi))
                If ri > 0 And nc < UBound(cRow) Then
                    sc = AltScore(vals, r, cScore(c0), gRecPrice(ri), CDbl(gRecUnits(ri)), gRecPts(ri), remN)
                    If sc > 0 And gRecPts(ri) <= PTS_HI Then
                        nc = nc + 1
                        cRow(nc) = r
                        cAsin(nc) = cAsin(c0)
                        cFam(nc) = cFam(c0)
                        cKey(nc) = gRecKey(ri)
                        cN(nc) = gRecUnits(ri)
                        cScore(nc) = sc
                        cPts(nc) = gRecPts(ri)
                        cSlot(nc) = gMemSlot(mi)
                        cAlt(nc) = True
                        cRec(nc) = ri
                        cCg(nc) = ""
                    End If
                End If
            End If
        Next mi
        ' coupon deal of a product that is in a set group (a row cannot be both: the coupon is its own candidate, 2 units at the coupon price)
        If Left$(cKey(c0), 1) <> "#" And nc < UBound(cRow) Then
            If LCase$(CellText(vals(r, 25))) = "coupon" Then
                uV = SafeDbl(vals(r, 22))
                wV = SafeDbl(vals(r, 79))
                xV = SafeDbl(vals(r, 81))
                If uV > 0 And wV >= 2 And xV > 0 And xV <= PTS_HI And SafeDbl(vals(r, 23)) >= 2 Then
                    sc = AltScore(vals, r, cScore(c0), uV * wV, wV, xV, remN)
                    If sc > 0 Then
                        nc = nc + 1
                        cRow(nc) = r
                        cAsin(nc) = cAsin(c0)
                        cFam(nc) = cFam(c0)
                        cKey(nc) = "#" & cAsin(c0)
                        cN(nc) = CLng(wV)
                        cScore(nc) = sc
                        cPts(nc) = xV
                        cSlot(nc) = "COUPON"
                        cAlt(nc) = True
                        cRec(nc) = 0
                        cCg(nc) = CouponGroupOf(vals, r)
                    End If
                End If
            End If
        End If
    Next c0

    If nc = 0 Then
        Notify "No product needs ordering right now (every product is at or above its Max Stock, or has no profit).", vbInformation
        If appendMode And exN > 0 Then
            WriteTotals wsDest, exN + 1
            RewriteFormulas wsDest
            LabelOrderTab wsDest
        End If
        Application.ScreenUpdating = True
        Exit Sub
    End If

    ' ---- ASINs of the other order tabs (order tabs only, visible, not this one)
    ReDim tabA(1 To wb.Sheets.count, 1 To 300)
    ReDim tabCnt(1 To wb.Sheets.count)
    For s = FirstOrderIdx() To wb.Sheets.count
        Set ws = wb.Sheets(s)
        If ws.Name <> wsDest.Name And ws.Visible = xlSheetVisible Then
            n = 0
            rr = 2
            Do While Len(Trim$(CStr(ws.Cells(rr, 2).Value))) > 0
                n = n + 1
                rr = rr + 1
            Loop
            If n > 300 Then n = 300
            If n > 0 Then
                nt = nt + 1
                For j = 1 To n
                    tabA(nt, j) = Trim$(CStr(ws.Cells(j + 1, 2).Value))
                Next j
                tabCnt(nt) = n
                sumCnt = sumCnt + n
            End If
        End If
    Next s
    ntDim = nt
    If ntDim < 1 Then ntDim = 1
    ReDim inTab(1 To nc, 1 To ntDim)
    ReDim shr(1 To ntDim)
    nest = 30
    If nt > 0 Then
        For ti = 1 To nt
            For k = 1 To nc
                For j = 1 To tabCnt(ti)
                    If tabA(ti, j) = cAsin(k) Then
                        inTab(k, ti) = True
                        Exit For
                    End If
                Next j
            Next k
        Next ti
        nest = CLng(sumCnt / nt)
    End If
    If nest < 20 Then nest = 20

    ReDim isPicked(1 To nc)
    ReDim picked(1 To MAX_LINES + 8)
    ReDim qtyOf(1 To MAX_LINES + 8)
    ReDim tagOf(1 To MAX_LINES + 8)
    ReDim ovrOf(1 To MAX_LINES + 8)
    ReDim slotOf(1 To MAX_LINES + 8)
    ReDim famList(1 To MAX_LINES + 70)
    ReDim grpFam(1 To 12)
    For j = 1 To nExF
        nf = nf + 1
        famList(nf) = exF(j)
    Next j
    Randomize

    ' ---- Credit items first (their points are not counted, they only take a place in the order)
    If nCredit = 0 And Not noCredit Then
        PickCreditRows wb, wsDest, vals, usableLastRow, fbaOnly, exA, exN, exF, nExF, rCheap, rExp, qExp
        For q = 1 To 2
            kc = 0
            If q = 1 And rCheap > 0 Then
                For k = 1 To nc
                    If cRow(k) = rCheap And Not cAlt(k) Then kc = k
                Next k
            End If
            If q = 2 And rExp > 0 Then
                For k = 1 To nc
                    If cRow(k) = rExp And Not cAlt(k) Then kc = k
                Next k
            End If
            If kc > 0 Then
                For c = 1 To nc
                    If cAsin(c) = cAsin(kc) Then isPicked(c) = True
                Next c
                If Len(cCg(kc)) > 0 And nCpn < 40 Then
                    nCpn = nCpn + 1
                    cpnUsed(nCpn) = cCg(kc)
                End If
                np = np + 1
                picked(np) = kc
                qtyOf(np) = 1
                tagOf(np) = "Credit " & q
                If q = 2 And qExp > 1 Then qtyOf(np) = qExp
                nCrNew = nCrNew + 1
                If Len(cFam(kc)) > 0 Then
                    nf = nf + 1
                    famList(nf) = cFam(kc)
                End If
                If nt > 0 Then
                    For ti = 1 To nt
                        If inTab(kc, ti) Then shr(ti) = shr(ti) + 1
                    Next ti
                End If
            End If
        Next q
    End If

    ' ---- Pick products
    '      A product that belongs to a mix-and-match set (group) is picked together with partners of the same group,
    '      so the whole set is priced as a set. One set per group on a tab, never more than 2 units of one discounted product.
    '      The cleaners combo (group CLEAN) is a set of 3, 4 or 5 different cleaners.
    '      Recipes (savings packs of different products, see LoadRecipes) work the same way, but each partner must fill a free slot of the recipe.
    '      A product is on the tab only once: when one of its candidates is picked, all its other candidates (single, set, recipe, coupon) are taken out.
    For stage = 1 To 2
        If stage = 1 Then lim = 0.5 Else lim = 0.65
        Do While (pts < PTS_LO And exN + np - nCredit - nCrNew < MAX_LINES) Or partnersLeft > 0
            bestK = 0
            bestV = 0
            For k = 1 To nc
                If Not isPicked(k) Then
                    ok = True
                    If Len(cKey(k)) > 0 And Left$(cKey(k), 1) <> "#" Then
                        For j = 1 To nDead
                            If deadKey(j) = cKey(k) Then ok = False
                        Next j
                    End If
                    If ok And Len(cCg(k)) > 0 Then
                        ' coupon products of one deal: 2 units for the whole group on a tab. Inside a set that is being completed only the groups used before the set count.
                        q = nCpn
                        If partnersLeft > 0 Then q = nCpnSet
                        For j = 1 To q
                            If cpnUsed(j) = cCg(k) Then ok = False
                        Next j
                    End If
                    If ok Then
                        If partnersLeft > 0 Then
                            If cKey(k) <> restrictKey Then ok = False
                            If ok And restrictRec > 0 Then
                                sl = SlotNo(cSlot(k))
                                If sl = 0 Then
                                    ok = False
                                ElseIf slotRem(sl) <= 0 Then
                                    ok = False
                                End If
                            End If
                            needPts = 0
                        Else
                            needPts = cPts(k)
                            If pts + needPts > PTS_HI Then ok = False
                            If ok And cN(k) > 1 And Len(cKey(k)) > 0 And Left$(cKey(k), 1) <> "#" Then
                                For j = 1 To nUsed
                                    If usedKey(j) = cKey(k) Then ok = False
                                Next j
                            End If
                        End If
                    End If
                    If ok Then
                        If Len(cFam(k)) > 0 Then
                            For j = 1 To nf
                                If famList(j) = cFam(k) Then
                                    ok = False
                                    Exit For
                                End If
                            Next j
                        End If
                    End If
                    If ok And partnersLeft > 0 And restrictKey = "CLEAN" And Len(cFam(k)) > 0 Then
                        For j = 1 To ngf
                            If grpFam(j) = cFam(k) Then ok = False
                        Next j
                    End If
                    If ok And nt > 0 Then
                        For ti = 1 To nt
                            If inTab(k, ti) Then
                                If shr(ti) + 1 > Int(lim * (nest + tabCnt(ti)) / (1 + lim)) Then
                                    ok = False
                                    Exit For
                                End If
                            End If
                        Next ti
                    End If
                    If ok Then
                        v = cScore(k) * (0.75 + 0.5 * Rnd())
                        If partnersLeft > 0 And Len(cFam(k)) > 0 Then
                            For j = 1 To ngf
                                If grpFam(j) = cFam(k) Then v = v * 0.15
                            Next j
                        End If
                        If v > bestV Then
                            bestV = v
                            bestK = k
                        End If
                    End If
                End If
            Next k
            If bestK = 0 Then
                If partnersLeft > 0 Then
                    ' not enough partners for the full set
                    szNow = nPartners + 1
                    ok = False
                    If restrictKey = "CLEAN" Then
                        If szNow >= 3 Then
                            pts = pts - leadPts + cleanP(szNow)
                            ok = True
                        End If
                    ElseIf restrictRec > 0 Then
                        ' recipe: the missing units can only be a 2nd unit of a product of the one slot that is left
                        remTot = 0
                        nKinds = 0
                        lastSl = 0
                        For sl = 1 To 5
                            If slotRem(sl) > 0 Then
                                remTot = remTot + slotRem(sl)
                                nKinds = nKinds + 1
                                lastSl = sl
                            End If
                        Next sl
                        If nKinds = 1 Then
                            capRoom = 0
                            For j = leadIdx To np
                                If SlotNo(slotOf(j)) = lastSl And qtyOf(j) < 2 Then capRoom = capRoom + 1
                            Next j
                            If capRoom >= remTot Then
                                For j = leadIdx To np
                                    If remTot > 0 And SlotNo(slotOf(j)) = lastSl And qtyOf(j) < 2 Then
                                        qtyOf(j) = qtyOf(j) + 1
                                        remTot = remTot - 1
                                    End If
                                Next j
                                ok = True
                            End If
                        End If
                    Else
                        needQ = cN(picked(leadIdx)) - nPartners
                        If needQ <= 2 Then
                            qtyOf(leadIdx) = needQ
                            ok = True
                        End If
                    End If
                    If ok Then
                        If nUsed < 40 Then
                            nUsed = nUsed + 1
                            usedKey(nUsed) = restrictKey
                        End If
                        For q = 1 To ngf
                            nf = nf + 1
                            famList(nf) = grpFam(q)
                        Next q
                    Else
                        ' the set cannot be completed: take the lead product (and the partners already picked) out again and do not try this group again on this tab
                        pts = pts - leadPts
                        nCpn = nCpnSet
                        If nDead < 60 Then
                            nDead = nDead + 1
                            deadKey(nDead) = restrictKey
                        End If
                        For j = leadIdx To np
                            If nt > 0 Then
                                For ti = 1 To nt
                                    If inTab(picked(j), ti) Then shr(ti) = shr(ti) - 1
                                Next ti
                            End If
                            For c = 1 To nc
                                If cAsin(c) = cAsin(picked(j)) Then isPicked(c) = False
                            Next c
                        Next j
                        np = leadIdx - 1
                    End If
                    partnersLeft = 0
                    nPartners = 0
                    restrictKey = ""
                    restrictRec = 0
                    ngf = 0
                    If pts >= PTS_LO Or exN + np - nCredit - nCrNew >= MAX_LINES Then Exit Do
                Else
                    Exit Do
                End If
            Else
                For c = 1 To nc
                    If cAsin(c) = cAsin(bestK) Then isPicked(c) = True
                Next c
                np = np + 1
                picked(np) = bestK
                qtyOf(np) = 1
                tagOf(np) = ""
                ovrOf(np) = ""
                If cAlt(bestK) Then
                    If cSlot(bestK) = "COUPON" Then ovrOf(np) = "COUPON" Else ovrOf(np) = cKey(bestK)
                End If
                slotOf(np) = cSlot(bestK)
                If partnersLeft > 0 Then
                    nPartners = nPartners + 1
                    partnersLeft = partnersLeft - 1
                    If Len(cCg(bestK)) > 0 And nCpn < 40 Then
                        nCpn = nCpn + 1
                        cpnUsed(nCpn) = cCg(bestK)
                    End If
                    If restrictRec > 0 Then
                        sl = SlotNo(cSlot(bestK))
                        If sl > 0 Then slotRem(sl) = slotRem(sl) - 1
                    End If
                    If Len(cFam(bestK)) > 0 And ngf < 12 Then
                        ngf = ngf + 1
                        grpFam(ngf) = cFam(bestK)
                    End If
                    If partnersLeft = 0 Then
                        If nUsed < 40 Then
                            nUsed = nUsed + 1
                            usedKey(nUsed) = restrictKey
                        End If
                        restrictKey = ""
                        restrictRec = 0
                        For q = 1 To ngf
                            nf = nf + 1
                            famList(nf) = grpFam(q)
                        Next q
                        ngf = 0
                        nPartners = 0
                    End If
                Else
                    pts = pts + cPts(bestK)
                    If cN(bestK) > 1 And Len(cKey(bestK)) > 0 And Left$(cKey(bestK), 1) <> "#" Then
                        restrictKey = cKey(bestK)
                        leadIdx = np
                        nCpnSet = nCpn
                        If Len(cCg(bestK)) > 0 And nCpn < 40 Then
                            nCpn = nCpn + 1
                            cpnUsed(nCpn) = cCg(bestK)
                        End If
                        leadPts = cPts(bestK)
                        nPartners = 0
                        tgtN = cN(bestK)
                        restrictRec = 0
                        If cAlt(bestK) And cRec(bestK) > 0 Then
                            restrictRec = cRec(bestK)
                            For sl = 1 To 5
                                slotRem(sl) = RecSlotNeed(restrictRec, sl)
                            Next sl
                            sl = SlotNo(cSlot(bestK))
                            If sl > 0 Then slotRem(sl) = slotRem(sl) - 1
                        End If
                        If restrictKey = "CLEAN" Then
                            tgtN = 3 + Int(Rnd() * 3)
                            If tgtN > 5 Then tgtN = 5
                            Do While tgtN > 3 And pts - leadPts + cleanP(tgtN) > PTS_HI
                                tgtN = tgtN - 1
                            Loop
                            pts = pts - leadPts + cleanP(tgtN)
                            leadPts = cleanP(tgtN)
                        End If
                        partnersLeft = tgtN - 1
                        ngf = 0
                        If Len(cFam(bestK)) > 0 Then
                            ngf = 1
                            grpFam(1) = cFam(bestK)
                        End If
                    Else
                        If cN(bestK) > 0 Then qtyOf(np) = cN(bestK)
                        If Len(cCg(bestK)) > 0 And nCpn < 40 Then
                            nCpn = nCpn + 1
                            cpnUsed(nCpn) = cCg(bestK)
                        End If
                        If Len(cFam(bestK)) > 0 Then
                            nf = nf + 1
                            famList(nf) = cFam(bestK)
                        End If
                    End If
                End If
                If nt > 0 Then
                    For ti = 1 To nt
                        If inTab(bestK, ti) Then shr(ti) = shr(ti) + 1
                    Next ti
                End If
            End If
        Loop
        If pts >= PTS_LO Then Exit For
    Next stage


    ' ---- Write the order (same row layout as before)
    i = exN + 2
    For j = 1 To np
        CopyOneRow_AllInv wsSrc, wsDest, colsToCopy, cRow(picked(j)), i
        wsDest.Cells(i, 9).Value = qtyOf(j)
        wsDest.Cells(i, 15).Value = ovrOf(j)
        If Len(tagOf(j)) > 0 Then TagRow wsDest, i, tagOf(j)
        Usage_Inc_AllInv cAsin(picked(j)), 1
        If gPendOn Then gPend(cRow(picked(j))) = gPend(cRow(picked(j))) + qtyOf(j)
        i = i + 1
    Next j

    ' ---- How similar is this tab to the closest other tab?
    maxJ = 0
    For ti = 1 To nt
        jac = shr(ti) / (np + tabCnt(ti) - shr(ti))
        If jac > maxJ Then maxJ = jac
    Next ti

    ' ---- Format & finish
    WriteTotals wsDest, exN + np + 1
    SortActiveSheetByColumnA
    RewriteFormulas wsDest
    CalcTab wsDest
    LabelOrderTab wsDest
    With wsDest.Columns("B:L")
        .AutoFit
        .HorizontalAlignment = xlCenter
    End With
    wsDest.Columns("A").AutoFit
    wsDest.Columns("C").NumberFormat = "$#,##0.00"
    wsDest.Columns("D").NumberFormat = "0.00%"
    wsDest.Columns("J").NumberFormat = "$#,##0.00"
    wsDest.Columns("K").NumberFormat = "$#,##0.00"
    wsDest.Columns("N").AutoFit
    wsDest.Columns("M").Hidden = True
    wsDest.Columns("O").Hidden = True
    wsDest.Columns("P").ColumnWidth = 25
    pts = SafeDbl(wsDest.Cells(exN + np + 3, 12).Value)
    Application.ScreenUpdating = True

    gOk = True
    gPts = pts
    gLines = exN + np
    gOverlap = maxJ
    Application.StatusBar = "Order built: " & (exN + np) & " products, " & pts & " points, closest other tab overlap " & Format(maxJ, "0%")
    If pts < PTS_LO Then
        Notify "This order only reaches " & pts & " points: there are no more products that still need stock" & _
               IIf(fbaOnly, " (FBA-only list)", "") & ". Nothing was added just to fill points."
    ElseIf maxJ > 0.7 Then
        Notify "Order built, but it is " & Format(maxJ, "0%") & " similar to another tab (few products left to choose from)."
    End If
End Sub



'=====================================================================================
' ONE-TIME SETUP: adds the new Max Stock / Priority columns (BE:BU) on Melaleuca and
' points Priority (M), Max Stock (AU) and the "U" flags (B, AW) at them.
' Your old Max Stock numbers are saved in column BJ. Run Restore_OldPlan to go back.
' New products added later: copy the formulas in BE:BU (and M, AU, B, AW) down one row.
'=====================================================================================
Public Sub Setup_NewPlan()
    Dim ws As Worksheet, lastRow As Long, calcPrev As Long, alreadyDone As Boolean
    Set ws = ThisWorkbook.Sheets("Melaleuca")
    lastRow = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    If lastRow < 3 Then Exit Sub
    alreadyDone = (CellText(ws.Cells(1, 73).Value) = "Priority (new)")
    calcPrev = Application.Calculation
    Application.Calculation = xlCalculationManual
    Application.ScreenUpdating = False
    ws.Range("BE1").Value = "Plan row"
    ws.Range("BF1").Value = "Sold 30d"
    ws.Range("BG1").Value = "Sold 90d"
    ws.Range("BH1").Value = "Units/day"
    ws.Range("BI1").Value = "Cover days"
    ws.Range("BJ1").Value = "Old Max (backup)"
    ws.Range("BK1").Value = "Auto Max"
    ws.Range("BL1").Value = "Manual Max (type here)"
    ws.Range("BM1").Value = "Max Stock used"
    ws.Range("BN1").Value = "Order limit"
    ws.Range("BO1").Value = "Need (units)"
    ws.Range("BP1").Value = "Units per row"
    ws.Range("BQ1").Value = "Points per row"
    ws.Range("BR1").Value = "Profit per row"
    ws.Range("BS1").Value = "Profit per point"
    ws.Range("BT1").Value = "Score"
    ws.Range("BU1").Value = "Priority (new)"
    ws.Range("BV1").Value = "Mela ID"
    ws.Range("BW1").Value = "Pack row"
    ws.Range("BX1").Value = "Pack size"
    ws.Range("BY1").Value = "Pack unit price"
    ws.Range("BZ1").Value = "Pack points"
    ws.Range("CA1").Value = "Set size"
    ws.Range("CB1").Value = "Set unit price"
    ws.Range("CC1").Value = "Set points"
    ws.Range("CD1").Value = "Set group"
    ws.Range("CE1").Value = "Group key"
    ws.Range("CF1").Value = "Set size (used)"
    ws.Range("CG1").Value = "Set unit price (used)"
    ws.Range("CH1").Value = "Set points (used)"
    ws.Range("CJ1").Value = "GROUP: key"
    ws.Range("CK1").Value = "GROUP: what it is"
    ws.Range("CL1").Value = "GROUP: pack item no."
    ws.Range("CM1").Value = "GROUP: units in set"
    ws.Range("CN1").Value = "GROUP: set price (all units)"
    ws.Range("CO1").Value = "GROUP: set points (all units)"
    If Not alreadyDone Then
        ws.Range("BJ2:BJ" & lastRow).Value = ws.Range("AU2:AU" & lastRow).Value
    End If
    ws.Range("BE2").Formula = "=IFERROR(MATCH($D2,FBA!$Z:$Z,0),0)"
    ws.Range("BE2:BE" & lastRow).FillDown
    ws.Range("BF2").Formula = "=IF($BE2=0,0,N(INDEX(FBA!$Z:$CZ,$BE2,MATCH(""ord_units_30"",FBA!$Z$1:$CZ$1,0))))"
    ws.Range("BF2:BF" & lastRow).FillDown
    ws.Range("BG2").Formula = "=IF($BE2=0,0,N(INDEX(FBA!$Z:$CZ,$BE2,MATCH(""ord_units_90"",FBA!$Z$1:$CZ$1,0))))"
    ws.Range("BG2:BG" & lastRow).FillDown
    ws.Range("BH2").Formula = "=IF($BG2<=0,0,IF(AND($BF2>6,$BF2>0.5*$BG2),($BF2/30+$BG2/90)/2,$BG2/90))"
    ws.Range("BH2:BH" & lastRow).FillDown
    ws.Range("BI2").Formula = "=IF($AV2=""N"",30,IFERROR(IF($I2>=1,85,IF($I2>=0.6,70,55)),55))"
    ws.Range("BI2:BI" & lastRow).FillDown
    ws.Range("BK2").Formula = "=IF($BH2<=0,MIN(2,N($BJ2)),MIN(60,MAX(IF($AV2=""N"",1,2),ROUNDUP($BH2*$BI2,0))))"
    ws.Range("BK2:BK" & lastRow).FillDown
    ws.Range("BM2").Formula = "=IF(ISNUMBER($BL2),$BL2,$BK2)"
    ws.Range("BM2:BM" & lastRow).FillDown
    ws.Range("BN2").Formula = "=IF(AND(OR($N2=""*"",$CF2>0),$BH2*30>=3),ROUNDUP($BM2*1.3,0),$BM2)"
    ws.Range("BN2:BN" & lastRow).FillDown
    ws.Range("BO2").Formula = "=MAX(0,$BM2-N($AT2))"
    ws.Range("BO2:BO" & lastRow).FillDown
    ws.Range("BP2").Formula = "=IF($CF2>0,$CF2,1)"
    ws.Range("BP2:BP" & lastRow).FillDown
    ws.Range("BQ2").Formula = "=IF($CF2>0,$CH2,N($T2))"
    ws.Range("BQ2:BQ" & lastRow).FillDown
    ws.Range("BR2").Formula = "=IFERROR(($E2-$G2-IF($CF2>0,$CG2,$F2))*$BP2,0)"
    ws.Range("BR2:BR" & lastRow).FillDown
    ws.Range("BS2").Formula = "=IF($BQ2>0,$BR2/$BQ2,0)"
    ws.Range("BS2:BS" & lastRow).FillDown
    ws.Range("BT2").Formula = "=IFERROR(IF(OR($BO2<=0,$BR2<=0,$I2<0.6,$B2=""U""),0,$BS2*SQRT($BH2*30+1)*MIN(1,IF($CF2>0,SUMIF($CE:$CE,$CE2,$BO:$BO),$BO2)/$BP2)),0)"
    ws.Range("BT2:BT" & lastRow).FillDown
    ws.Range("BU2").Formula = "=IF($BT2<=0,101,MIN(100,MAX(1,ROUNDUP(100*(COUNTIF($BT:$BT,"">""&$BT2)+1)/COUNTIF($BT:$BT,"">0""),0))))"
    ws.Range("BU2:BU" & lastRow).FillDown
    ws.Range("BY2").Formula = "=IF(N($BW2)>0,IFERROR(INDEX($U:$U,$BW2)/$BX2,0),0)"
    ws.Range("BY2:BY" & lastRow).FillDown
    ws.Range("BZ2").Formula = "=IF(N($BW2)>0,N(INDEX($T:$T,$BW2)),0)"
    ws.Range("BZ2:BZ" & lastRow).FillDown
    ws.Range("CA2").Formula = "=IF(N($W2)>0,$W2,IF(AND(N($BX2)>1,$BZ2>0,$BZ2<$BX2*N($T2),$BY2>0,$BY2<=N($U2)+0.005),$BX2,0))"
    ws.Range("CA2:CA" & lastRow).FillDown
    ws.Range("CB2").Formula = "=IF(N($W2)>0,IF(N($V2)>0,$V2,N($U2)),IF($CA2>0,$BY2,0))"
    ws.Range("CB2:CB" & lastRow).FillDown
    ws.Range("CC2").Formula = "=IF(N($W2)>0,IF(N($X2)>0,$X2,N($T2)*$W2),IF($CA2>0,$BZ2,0))"
    ws.Range("CC2:CC" & lastRow).FillDown
    ws.Range("CE2").Formula = "=IF(AND($CD2<>"""",N(IFERROR(INDEX($CM$2:$CM$201,MATCH($CD2,$CJ$2:$CJ$201,0)),0))>1,N(IFERROR(INDEX($CN$2:$CN$201,MATCH($CD2,$CJ$2:$CJ$201,0)),0))>0),$CD2,IF($CA2>0,""#""&$D2,""""))"
    ws.Range("CE2:CE" & lastRow).FillDown
    ws.Range("CF2").Formula = "=IF($CE2="""",0,IF(LEFT($CE2,1)=""#"",$CA2,INDEX($CM$2:$CM$201,MATCH($CE2,$CJ$2:$CJ$201,0))))"
    ws.Range("CF2:CF" & lastRow).FillDown
    ws.Range("CG2").Formula = "=IF($CF2<=0,0,IF(LEFT($CE2,1)=""#"",$CB2,INDEX($CN$2:$CN$201,MATCH($CE2,$CJ$2:$CJ$201,0))/$CF2))"
    ws.Range("CG2:CG" & lastRow).FillDown
    ws.Range("CH2").Formula = "=IF($CF2<=0,0,IF(LEFT($CE2,1)=""#"",$CC2,INDEX($CO$2:$CO$201,MATCH($CE2,$CJ$2:$CJ$201,0))))"
    ws.Range("CH2:CH" & lastRow).FillDown
    RelinkPacks
    ws.Range("M2").Formula = "=$BU2"
    ws.Range("M2:M" & lastRow).FillDown
    ws.Range("AU2").Formula = "=$BM2"
    ws.Range("AU2:AU" & lastRow).FillDown
    ws.Range("B2").Formula = "=IF(AT2>=BN2,""U"",AV2)"
    ws.Range("B2:B" & lastRow).FillDown
    ws.Range("AW2").Formula = "=IF(AT2>=BN2,""U"",AV2)"
    ws.Range("AW2:AW" & lastRow).FillDown
    ws.Range("BE1:CO1").Font.Bold = True
    ws.Range("CD1:CD" & lastRow).Interior.Color = RGB(255, 242, 204)
    ws.Range("CJ1:CO1").Interior.Color = RGB(221, 235, 247)
    ws.Range("CJ2:CM60").Interior.Color = RGB(255, 242, 204)
    ws.Range("BV1:BV" & lastRow).Interior.Color = RGB(255, 242, 204)
    ws.Range("BL1:BL" & lastRow).Interior.Color = RGB(255, 242, 204)
    ws.Range("BH2:BH" & lastRow).NumberFormat = "0.00"
    ws.Range("BS2:BT" & lastRow).NumberFormat = "0.0"
    Application.Calculation = calcPrev
    Application.Calculate
    Application.ScreenUpdating = True
    MsgBox "New plan columns are ready (Melaleuca BE:CC)." & vbCrLf & _
           "Packs (2-Pack / 3-Pack rows) were linked to their single product: columns BW:CC." & vbCrLf & _
           "Mix-and-match sets: put the same word in column CD (yellow) for products that can be mixed in one set, and fill that word's line in the table CJ:CO (Update_Melaleuca_Prices does this for you)." & vbCrLf & _
           "Type a number in BL (yellow) to force a Max Stock for a product; leave it empty to use the automatic one." & vbCrLf & _
           "Your old Max Stock numbers are saved in BJ.", vbInformation, "Setup_NewPlan"
End Sub

Public Sub Restore_OldPlan()
    Dim ws As Worksheet, lastRow As Long
    Set ws = ThisWorkbook.Sheets("Melaleuca")
    If CellText(ws.Cells(1, 73).Value) <> "Priority (new)" Then
        MsgBox "The new plan is not installed.", vbInformation, "Restore_OldPlan"
        Exit Sub
    End If
    lastRow = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    Application.ScreenUpdating = False
    ws.Range("AU2:AU" & lastRow).Value = ws.Range("BJ2:BJ" & lastRow).Value
    ws.Range("B2").Formula = "=IF(AT2>=AU2,""U"",AV2)"
    ws.Range("B2:B" & lastRow).FillDown
    ws.Range("AW2").Formula = "=IF(AT2>=AU2,""U"",AV2)"
    ws.Range("AW2:AW" & lastRow).FillDown
    ws.Range("M2").Formula = "=IF(I2<0.6,101, IF(B2=""U"",101, MAX(1, ROUND( 101 - ( (MIN(10,I2/3*10)*4) + (IF(K2>800000,0,10*(1-(K2/1000000)))*6) + (MAX(0, (1-(L2/IF(K2<100000,75,IF(K2<=250000,30,IF(K2<=800000,10,5))))^0.5))*10*2) ) * IF(OR(B2=""C"",B2=""N""),0.2,1),0)) ) )"
    ws.Range("M2:M" & lastRow).FillDown
    ws.Range("BE1:BU" & lastRow).ClearContents
    ws.Range("BW1:CC" & lastRow).ClearContents
    ws.Range("CE1:CH" & lastRow).ClearContents
    Application.Calculate
    Application.ScreenUpdating = True
    MsgBox "Old Priority and Max Stock restored.", vbInformation, "Restore_OldPlan"
End Sub


'=====================================================================================
' PACKS: finds "2-Pack / 3-Pack" rows and links them to their single product (Melaleuca BW:BX).
' When the pack needs fewer points than the same number of singles (and is not more
' expensive), the single is bought as a set automatically: Set size / unit price / points
' (CA:CC) feed the quantity, points and total of every order tab.
'=====================================================================================
Private Function PackSizeOf(ByVal nm As String, ByRef baseName As String) As Long
    Dim s As String, p As Long, q As Long, d As String, ch As String, ok As Boolean
    s = LCase$(nm)
    baseName = s
    p = InStr(1, s, "pack")
    Do While p > 0
        q = p - 1
        Do While q >= 1
            ch = Mid$(s, q, 1)
            If ch = "-" Or ch = " " Or ch = ChrW(8211) Then
                q = q - 1
            Else
                Exit Do
            End If
        Loop
        d = ""
        Do While q >= 1
            ch = Mid$(s, q, 1)
            If ch >= "0" And ch <= "9" Then
                d = ch & d
                q = q - 1
            Else
                Exit Do
            End If
        Loop
        If Len(d) > 0 And Len(d) <= 2 Then
            ok = True
            If q >= 1 Then
                ch = Mid$(s, q, 1)
                ok = (ch = " " Or ch = "-" Or ch = ChrW(8211))
            End If
            If ok And CLng(d) >= 2 Then
                PackSizeOf = CLng(d)
                baseName = Left$(s, q) & Mid$(s, p + 4)
                Exit Function
            End If
        End If
        p = InStr(p + 1, s, "pack")
    Loop
End Function

Private Function NormName(ByVal s As String) As String
    Dim i As Long, ch As String, o As String
    s = LCase$(s)
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        If (ch >= "a" And ch <= "z") Or (ch >= "0" And ch <= "9") Then o = o & ch
    Next i
    NormName = o
End Function

Private Function RelinkPacks() As Long
    Dim ws As Worksheet, lastRow As Long, r As Long, p As Long, found As Long
    Dim vals As Variant, packN() As Long, baseN() As String, b As String
    Dim outv() As Variant, ppuNew As Double, ppuOld As Double, cur As Long
    Set ws = ThisWorkbook.Sheets("Melaleuca")
    lastRow = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    If lastRow < 3 Then Exit Function
    vals = ws.Range(ws.Cells(1, 1), ws.Cells(lastRow, 54)).Value
    ReDim packN(1 To lastRow)
    ReDim baseN(1 To lastRow)
    ReDim outv(1 To lastRow - 1, 1 To 2)
    For r = 2 To lastRow
        packN(r) = PackSizeOf(CellText(vals(r, 1)), b)
        baseN(r) = NormName(b)
    Next r
    For p = 2 To lastRow
        If packN(p) >= 2 And Len(baseN(p)) > 0 Then
            found = 0
            For r = 2 To lastRow
                If r <> p And packN(r) = 0 And baseN(r) = baseN(p) Then
                    If Len(CellText(vals(r, 54))) > 0 And Len(CellText(vals(p, 54))) > 0 And CellText(vals(r, 54)) <> CellText(vals(p, 54)) Then
                        ' different family: not the same product
                    Else
                        found = r
                        Exit For
                    End If
                End If
            Next r
            If found > 0 Then
                ppuNew = SafeDbl(vals(p, 20)) / packN(p)
                cur = 0
                If Not IsEmpty(outv(found - 1, 1)) Then cur = CLng(outv(found - 1, 1))
                If cur = 0 Then
                    outv(found - 1, 1) = p
                    outv(found - 1, 2) = packN(p)
                Else
                    ppuOld = SafeDbl(vals(cur, 20)) / packN(cur)
                    If ppuNew < ppuOld Or (ppuNew = ppuOld And packN(p) < packN(cur)) Then
                        outv(found - 1, 1) = p
                        outv(found - 1, 2) = packN(p)
                    End If
                End If
            End If
        End If
    Next p
    ws.Range(ws.Cells(2, 75), ws.Cells(lastRow, 76)).Value = outv
    For r = 1 To lastRow - 1
        If Not IsEmpty(outv(r, 1)) Then RelinkPacks = RelinkPacks + 1
    Next r
End Function

Public Sub Relink_Packs_Quiet()
    If CellText(ThisWorkbook.Sheets("Melaleuca").Cells(1, 79).Value) = "Set size" Then RelinkPacks
End Sub

Public Sub Relink_Packs()
    Dim ws As Worksheet, n As Long, lastRow As Long, r As Long, k As Long, lst As String
    Set ws = ThisWorkbook.Sheets("Melaleuca")
    If CellText(ws.Cells(1, 79).Value) <> "Set size" Then
        MsgBox "Run Setup_NewPlan first.", vbExclamation, "Relink_Packs"
        Exit Sub
    End If
    n = RelinkPacks()
    Application.Calculate
    lastRow = ws.Cells(ws.Rows.count, 1).End(xlUp).Row
    For r = 2 To lastRow
        If SafeDbl(ws.Cells(r, 79).Value) > 0 And SafeDbl(ws.Cells(r, 23).Value) = 0 Then
            k = k + 1
            If k <= 15 Then lst = lst & vbCrLf & "  " & ws.Cells(r, 1).Value & "  (set of " & ws.Cells(r, 79).Value & ": " & ws.Cells(r, 81).Value & " pts instead of " & ws.Cells(r, 79).Value * SafeDbl(ws.Cells(r, 20).Value) & ")"
        End If
    Next r
    MsgBox n & " pack(s) linked to their single product." & vbCrLf & _
           k & " single product(s) now use the pack automatically (it needs fewer points):" & lst & vbCrLf & vbCrLf & _
           "A pack is used only when its points (column T of the pack row) are lower than the same number of singles.", vbInformation, "Relink_Packs"
End Sub



'=====================================================================================
' CREATE ALL ORDERS: builds every coloured order tab in one go.
'   orange or yellow tab = FBA-only order, blue tab = all-inventory order.
'   (same engine and same rules as Create_FBA_Only_Order / Create_All_Inventory_Order)
'=====================================================================================
Public Sub Create_All_Orders()
    Dim wb As Workbook, ws As Worksheet, wsStart As Worksheet
    Dim s As Long, i As Long, n As Long, nFba As Long, nAll As Long, nFull As Long, pass As Long
    Dim names() As String, kinds() As Long, full() As Boolean
    Dim ans As Long, rebuild As Boolean, built As Long, skipped As Long, failed As Long
    Dim repTxt() As String, repOk() As Boolean, repLines() As Long, repPts() As Double, repNote() As String
    Dim report As String, calcPrev As Long

    Set wb = ThisWorkbook
    On Error Resume Next: Application.Run "Sync_Canada_Points", True: On Error GoTo 0      ' Canadian points table + sheet MelaleucaCA (see modCanadaPoints)
    Set wsStart = ActiveSheet
    ReDim names(1 To wb.Sheets.count)
    ReDim kinds(1 To wb.Sheets.count)
    ReDim full(1 To wb.Sheets.count)
    ReDim repTxt(1 To wb.Sheets.count)
    ReDim repOk(1 To wb.Sheets.count)
    ReDim repLines(1 To wb.Sheets.count)
    ReDim repPts(1 To wb.Sheets.count)
    ReDim repNote(1 To wb.Sheets.count)
    For s = FirstOrderIdx() To wb.Sheets.count
        Set ws = wb.Sheets(s)
        If IsOrderTab(ws) Then
            If TabKind(ws) > 0 Then
                n = n + 1
                names(n) = ws.Name
                kinds(n) = TabKind(ws)
                full(n) = (Len(CellText(ws.Cells(2, 2).Value)) > 0)
                If kinds(n) = 1 Then nFba = nFba + 1 Else nAll = nAll + 1
                If full(n) Then nFull = nFull + 1
            End If
        End If
    Next s
    If n = 0 Then
        MsgBox "No coloured order tabs found." & vbCrLf & "Colour a tab orange or yellow (FBA-only order) or blue (all-inventory order), then run this again.", vbInformation, "Create_All_Orders"
        Exit Sub
    End If

    If nFull > 0 Then
        ans = MsgBox(n & " coloured tabs (" & nFba & " FBA-only, " & nAll & " all-inventory); " & nFull & " already have an order." & vbCrLf & vbCrLf & _
                     "YES = rebuild ALL of them (their current orders are erased)" & vbCrLf & _
                     "NO = fill only the empty tabs and keep the existing orders" & vbCrLf & _
                     "CANCEL = do nothing", vbYesNoCancel + vbQuestion, "Create_All_Orders")
        If ans = vbCancel Then Exit Sub
        rebuild = (ans = vbYes)
    Else
        ans = MsgBox("Build orders for " & n & " coloured tabs (" & nFba & " FBA-only, " & nAll & " all-inventory)?", vbYesNo + vbQuestion, "Create_All_Orders")
        If ans <> vbYes Then Exit Sub
    End If

    On Error GoTo failed
    Application.ScreenUpdating = False
    If rebuild Then
        For i = 1 To n
            ClearOrderRows wb.Sheets(names(i)), 2, 164
        Next i
    End If
    ' the Summary is rebuilt now (tabs that are kept count) and once more at the very end; in between only the units
    ' placed by this run are remembered (gPend), so a product that reached its Max Stock is not ordered again on the next tab
    SummarizeAllSheets
    Application.Calculate
    ReDim gPend(1 To 1500)
    gPendOn = True
    calcPrev = Application.Calculation
    Application.Calculation = xlCalculationManual

    gSilent = True
    For pass = 1 To 2                         ' FBA-only tabs first (their product list is the smaller one)
        For i = 1 To n
            If kinds(i) = pass Then
                If full(i) And Not rebuild Then
                    skipped = skipped + 1
                    repTxt(i) = names(i) & ": kept (already has an order)"
                Else
                    Application.StatusBar = "Building order " & (built + failed + skipped + 1) & " of " & n & ": " & names(i)
                    wb.Sheets(names(i)).Activate
                    gNote = ""
                    BuildOrderTab (kinds(i) = 1)
                    If gOk Then
                        built = built + 1
                        repOk(i) = True
                        repLines(i) = gLines
                        repPts(i) = gPts
                        repNote(i) = gNote
                    Else
                        failed = failed + 1
                        repTxt(i) = names(i) & ": NOT built - " & gNote
                    End If
                End If
            End If
        Next i
    Next pass
    gSilent = False
    gNote = ""
    gPendOn = False
    Application.Calculation = calcPrev
    ' ---- the Summary, once, at the end
    SummarizeAllSheets
    Application.Calculate
    For i = 1 To n
        If repOk(i) Then
            repTxt(i) = names(i) & IIf(kinds(i) = 1, " (FBA only)", "") & ": " & repLines(i) & " products, " & repPts(i) & " points, " & _
                        Format(ClosestOverlap(wb.Sheets(names(i))), "0%") & " like the closest tab" & IIf(Len(repNote(i)) > 0, "  - " & repNote(i), "")
        End If
        If Len(repTxt(i)) > 0 Then report = report & vbCrLf & repTxt(i)
    Next i

    wsStart.Activate
    Application.StatusBar = False
    Application.ScreenUpdating = True
    MsgBox "Create_All_Orders finished: " & built & " built, " & skipped & " kept, " & failed & " not built." & vbCrLf & report, vbInformation, "Create_All_Orders"
    Exit Sub
failed:
    gSilent = False
    gPendOn = False
    gAppend = False
    gNoCredit = False
    Application.Calculation = xlCalculationAutomatic
    Application.ScreenUpdating = True
    Application.StatusBar = False
    MsgBox "Create_All_Orders stopped: " & Err.Description, vbExclamation, "Create_All_Orders"
End Sub

'=====================================================================================
' ADD EXTRA PRODUCT: adds the next most-needed product to the current order tab
'   (best score among products that still need stock, not already in this order, not from
'    the same family, allowed for this tab type, and that fits in the remaining points up to 150)
'=====================================================================================
Private Function SrcLastRow(wsSrc As Worksheet) As Long
    Dim r As Long, last As Long, firstBlankA As Long
    last = wsSrc.Cells(wsSrc.Rows.count, 13).End(xlUp).Row
    For r = 2 To last
        If Len(Trim$(CStr(wsSrc.Cells(r, 1).Value))) = 0 Then
            firstBlankA = r - 1
            Exit For
        End If
    Next r
    If firstBlankA > 0 Then last = Application.Min(last, firstBlankA)
    SrcLastRow = last
End Function

Private Function TabUseCount(wb As Workbook, wsDest As Worksheet, ByVal a As String) As Long
    Dim s As Long, ws As Worksheet, r As Long, cnt As Long
    For s = FirstOrderIdx() To wb.Sheets.count
        Set ws = wb.Sheets(s)
        If IsOrderTab(ws) And ws.Name <> wsDest.Name Then
            r = 2
            Do While Len(CellText(ws.Cells(r, 2).Value)) > 0 And r < 300
                If CellText(ws.Cells(r, 2).Value) = a Then
                    cnt = cnt + 1
                    Exit Do
                End If
                r = r + 1
            Loop
        End If
    Next s
    TabUseCount = cnt
End Function

' writes one product row into the first free row above TOTAL (inserting one if needed) and keeps one blank row above TOTAL
Private Function AddOrderRow(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, ByVal srcRow As Long, ByVal qty As Long, ByRef t As Long) As Long
    Dim target As Long, r As Long
    For r = 2 To t - 1
        If Len(CellText(wsDest.Cells(r, 2).Value)) = 0 Then
            target = r
            Exit For
        End If
    Next r
    If target = 0 Then
        wsDest.Rows(t).Insert
        target = t
        t = t + 1
    End If
    CopyOneRow_AllInv wsSrc, wsDest, colsToCopy, srcRow, target
    If qty > 0 Then wsDest.Cells(target, 9).Value = qty
    If target = t - 1 Then
        wsDest.Rows(t).Insert                 ' keep one blank row above TOTAL
        t = t + 1
        wsDest.Rows(t - 1).ClearContents
    End If
    With wsDest.Range(wsDest.Cells(target, 2), wsDest.Cells(target, 13))
        .HorizontalAlignment = xlCenter
        .Font.Bold = False
    End With
    wsDest.Cells(target, 3).NumberFormat = "$#,##0.00"
    wsDest.Cells(target, 4).NumberFormat = "0.00%"
    wsDest.Cells(target, 10).NumberFormat = "$#,##0.00"
    wsDest.Cells(target, 11).NumberFormat = "$#,##0.00"
    AddOrderRow = target
End Function

Private Sub Add_New_ProductCore()
    Dim wb As Workbook, wsSrc As Worksheet, wsDest As Worksheet
    Dim kind As Long, fbaOnly As Boolean, ans As Long
    Dim vals As Variant, lastR As Long, colsToCopy As Variant
    Dim t As Long, r As Long, k As Long, j As Long, m As Long
    Dim ptsNow As Double, room As Double, ptsAfter As Double
    Dim onAsin() As String, nOn As Long, onFam() As String, nFam As Long
    Dim gKey() As String, gQty() As Double, nG As Long, qd As Double
    Dim a As String, typ As String, fda As String, fam As String, key As String
    Dim sc As Double, pt As Double, pr As Double, v As Double, bestV As Double, bestR As Long
    Dim ok As Boolean, nm As String, n As Long, isGrp As Boolean, rem0 As Double, cost As Double
    Dim bestMode As Long, mode As Long, bestCost As Double
    Dim partR() As Long, partV() As Double, nPart As Long, taken() As Boolean
    Dim leadQty As Long, addedTxt As String, onThis As Boolean
    Dim pFam(1 To 8) As String, nPFam As Long
    Dim recSel As Long, ri As Long, mi As Long, recSlot As Long, altBest As Double, nOut As Long
    Dim outRow(1 To 8) As Long
    Dim outQty(1 To 8) As Long

    Set wb = ThisWorkbook
    Set wsSrc = wb.Sheets("MELALEUCA")
    Set wsDest = ActiveSheet
    colsToCopy = Array(1, 4, 6, 9, 11, 12, 13)
    If Not IsOrderTab(wsDest) Then
        MsgBox "Click on an order tab first, then press the button.", vbExclamation, "Add New Product"
        Exit Sub
    End If
    If CellText(wsSrc.Cells(1, 73).Value) <> "Priority (new)" Or CellText(wsSrc.Cells(1, 84).Value) <> "Set size (used)" Then
        MsgBox "Run Setup_NewPlan once first.", vbExclamation, "Add New Product"
        Exit Sub
    End If
    kind = TabKind(wsDest)
    If kind = 0 Then
        ans = MsgBox("This tab has no colour (orange/yellow = FBA only, blue = all inventory)." & vbCrLf & "Treat it as an ALL-INVENTORY order?", vbYesNo + vbQuestion, "Add New Product")
        If ans <> vbYes Then Exit Sub
    End If
    fbaOnly = (kind = 1)

    Application.ScreenUpdating = False
    RewriteFormulas wsDest
    SummarizeAllSheets
    Application.Calculate

    ' --- where is the TOTAL row, and how many points does the order have now?
    t = 0
    For r = 2 To 300
        If UCase$(CellText(wsDest.Cells(r, 1).Value)) = "TOTAL" Then
            t = r
            Exit For
        End If
    Next r
    If t = 0 Then
        r = 2
        Do While Len(CellText(wsDest.Cells(r, 2).Value)) > 0
            r = r + 1
        Loop
        WriteTotals wsDest, r - 1
        t = r + 1
    End If
    ptsNow = CountedPoints(wsDest, t - 1)
    If ptsNow >= PTS_MAX Then
        Application.ScreenUpdating = True
        MsgBox "This order already has " & ptsNow & " points (the limit is " & PTS_MAX & ").", vbInformation, "Add New Product"
        Exit Sub
    End If
    If ptsNow >= PTS_HI Then
        Application.ScreenUpdating = True
        ans = MsgBox("This order already has " & ptsNow & " points (target 143-" & PTS_HI & ")." & vbCrLf & "Add one more product anyway (up to " & PTS_MAX & " points)?", vbYesNo + vbQuestion, "Add New Product")
        If ans <> vbYes Then Exit Sub
        Application.ScreenUpdating = False
    End If
    room = PTS_MAX - ptsNow

    ' --- products already in this order, their families, and the units of every mix-and-match group
    lastR = SrcLastRow(wsSrc)
    vals = wsSrc.Range(wsSrc.Cells(1, 1), wsSrc.Cells(lastR, 86)).Value
    ReDim onAsin(1 To 400)
    ReDim onFam(1 To 400)
    ReDim gKey(1 To 60)
    ReDim gQty(1 To 60)
    For r = 2 To t - 1
        a = CellText(wsDest.Cells(r, 2).Value)
        If Len(a) > 0 And nOn < 400 Then
            nOn = nOn + 1
            onAsin(nOn) = a
            For k = 2 To lastR
                If CellText(vals(k, 4)) = a Then
                    fam = CellText(vals(k, 54))
                    If Len(fam) > 0 Then
                        nFam = nFam + 1
                        onFam(nFam) = fam
                    End If
                    key = CellText(vals(k, 83))
                    If Len(CellText(wsDest.Cells(r, 15).Value)) > 0 Then key = CellText(wsDest.Cells(r, 15).Value)
                    If key = "COUPON" Then key = ""
                    If Len(key) > 0 And Left$(key, 1) <> "#" And (SafeDbl(vals(k, 84)) > 1 Or Len(CellText(wsDest.Cells(r, 15).Value)) > 0) Then
                        qd = SafeDbl(wsDest.Cells(r, 9).Value)
                        m = 0
                        For j = 1 To nG
                            If gKey(j) = key Then
                                m = j
                                Exit For
                            End If
                        Next j
                        If m = 0 And nG < 60 Then
                            nG = nG + 1
                            gKey(nG) = key
                            m = nG
                        End If
                        If m > 0 Then gQty(m) = gQty(m) + qd
                    End If
                    Exit For
                End If
            Next k
        End If
    Next r

    ' --- choose the best product that fits
    '     mode 1 = normal product / row-level set, mode 2 = completes an unfinished group on this tab, mode 3 = starts a new group
    For k = 2 To lastR
        nm = CellText(vals(k, 1))
        a = CellText(vals(k, 4))
        If Len(nm) > 0 And Len(a) > 0 Then
            ok = True
            typ = UCase$(CellText(vals(k, 3)))
            fda = CellText(vals(k, 56))
            If fbaOnly Then
                If typ = "M" Then ok = False
                If Len(fda) > 0 And fda <> "0" Then ok = False
            End If
            pr = SafeDbl(vals(k, 13))
            If pr < 1 Or pr > 100 Then ok = False
            sc = SafeDbl(vals(k, 72))
            If sc <= 0 Then ok = False
            For j = 1 To nOn
                If onAsin(j) = a Then
                    ok = False
                    Exit For
                End If
            Next j
            If ok Then
                key = CellText(vals(k, 83))
                n = CLng(SafeDbl(vals(k, 84)))
                isGrp = (n > 1 And Len(key) > 0 And Left$(key, 1) <> "#")
                mode = 1
                cost = SafeDbl(vals(k, 69))
                onThis = False
                rem0 = 0
                If isGrp Then
                    For j = 1 To nG
                        If gKey(j) = key Then
                            onThis = True
                            rem0 = gQty(j) - n * Int(gQty(j) / n)
                            If key = "CLEAN" Then
                                rem0 = 0
                                If gQty(j) < 3 Then rem0 = 3 - gQty(j)
                            End If
                            Exit For
                        End If
                    Next j
                    If rem0 > 0 Then
                        mode = 2
                        cost = SafeDbl(vals(k, 20))
                    ElseIf onThis Then
                        ok = False                  ' a second set of the same group is not added to a tab
                    Else
                        mode = 3
                        If CountPartners(vals, lastR, key, k, fbaOnly, onAsin, nOn, onFam, nFam) < IIf(key = "CLEAN", 2, n - 2) Then ok = False
                    End If
                End If
                If cost <= 0 Or cost > room Then ok = False
            End If
            If ok Then
                fam = CellText(vals(k, 54))
                If Len(fam) > 0 And Not onThis Then
                    For j = 1 To nFam
                        If onFam(j) = fam Then
                            ok = False
                            Exit For
                        End If
                    Next j
                End If
            End If
            If ok Then
                ' prefer products that are in fewer of the other tabs (keeps the tabs different)
                v = sc / (1 + 0.12 * TabUseCount(wb, wsDest, a))
                If mode = 2 Then v = v * 1.5          ' finishing a set that is already on the tab comes first
                If v > bestV Then
                    bestV = v
                    bestR = k
                    bestMode = mode
                    bestCost = cost
                End If
            End If
        End If
    Next k

    If bestR = 0 Then
        ' nothing fits in the points that are left: use the account credit items (their points are not counted)
        If CreditRowCount(wsDest, t - 1) = 0 And CreditAmount(wsDest) > 0 And PackRowCount(wsDest, t - 1) = 0 Then
            Dim rC1 As Long, rC2 As Long
            Dim qC2 As Long
            PickCreditRows wb, wsDest, vals, lastR, fbaOnly, onAsin, nOn, onFam, nFam, rC1, rC2, qC2
            If rC1 > 0 Or rC2 > 0 Then
                addedTxt = "Credit items (paid with your account credit, not counted in the points):"
                If rC1 > 0 Then
                    k = AddOrderRow(wsSrc, wsDest, colsToCopy, rC1, 1, t)
                    TagRow wsDest, k, "Credit 1"
                    Usage_Inc_AllInv CellText(vals(rC1, 4)), 1
                    addedTxt = addedTxt & vbCrLf & "      " & nm_of(vals, rC1)
                End If
                If rC2 > 0 Then
                    k = AddOrderRow(wsSrc, wsDest, colsToCopy, rC2, qC2, t)
                    TagRow wsDest, k, "Credit 2"
                    Usage_Inc_AllInv CellText(vals(rC2, 4)), 1
                    addedTxt = addedTxt & vbCrLf & "      " & nm_of(vals, rC2)
                End If
                RefreshTotals wsDest, t
                SortActiveSheetByColumnA
                RewriteFormulas wsDest
                SummarizeAllSheets
                Application.Calculate
                LabelOrderTab wsDest
                Application.ScreenUpdating = True
                MsgBox addedTxt & vbCrLf & "Order still has " & CountedPoints(wsDest, t - 1) & " counted points.", vbInformation, "Add New Product"
                Exit Sub
            End If
        End If
        Application.ScreenUpdating = True
        MsgBox "No other product needs stock that fits in the remaining " & room & " points" & IIf(fbaOnly, " (FBA-only list)", "") & ".", vbInformation, "Add New Product"
        Exit Sub
    End If

    ' --- a recipe (savings pack that mixes products, see LoadRecipes) when buying the product inside it pays better than buying it alone
    recSel = 0
    If bestMode = 1 And SafeDbl(vals(bestR, 22)) <= 0 Then
        LoadRecipes wsSrc
        a = CellText(vals(bestR, 4))
        altBest = SafeDbl(vals(bestR, 72))
        For mi = 1 To gMemN
            If gMemAsin(mi) = a Then
                ri = RecIdx(gMemKey(mi))
                If ri > 0 Then
                    If gRecPts(ri) <= room Then
                        v = AltScore(vals, bestR, SafeDbl(vals(bestR, 72)), gRecPrice(ri), CDbl(gRecUnits(ri)), gRecPts(ri), SafeDbl(vals(bestR, 67)))
                        If v > altBest Then
                            altBest = v
                            recSel = ri
                            recSlot = SlotNo(gMemSlot(mi))
                        End If
                    End If
                End If
            End If
        Next mi
        If recSel > 0 Then
            ' only if the order has no set of this recipe yet
            For j = 1 To nG
                If gKey(j) = gRecKey(recSel) Then recSel = 0
            Next j
        End If
        If recSel > 0 Then
            If Not FindRecipePartners(wb, wsDest, vals, lastR, fbaOnly, recSel, bestR, recSlot, onAsin, nOn, onFam, nFam, outRow, outQty, nOut) Then recSel = 0
        End If
    End If

    ' --- a new mix-and-match set: pick the partners from the same group
    leadQty = 0
    nPart = 0
    If bestMode = 3 Then
        key = CellText(vals(bestR, 83))
        n = CLng(SafeDbl(vals(bestR, 84)))
        ReDim partR(1 To n)
        ReDim partV(1 To n)
        nPFam = 1
        pFam(1) = CellText(vals(bestR, 54))
        ReDim taken(1 To lastR)
        taken(bestR) = True
        For m = 1 To n - 1
            bestV = 0
            j = 0
            For k = 2 To lastR
                If Not taken(k) Then
                    If CellText(vals(k, 83)) = key Then
                        a = CellText(vals(k, 4))
                        ok = (Len(a) > 0)
                        typ = UCase$(CellText(vals(k, 3)))
                        fda = CellText(vals(k, 56))
                        If fbaOnly Then
                            If typ = "M" Then ok = False
                            If Len(fda) > 0 And fda <> "0" Then ok = False
                        End If
                        pr = SafeDbl(vals(k, 13))
                        If pr < 1 Or pr > 100 Then ok = False
                        sc = SafeDbl(vals(k, 72))
                        If sc <= 0 Then ok = False
                        If ok Then
                            For r = 1 To nOn
                                If onAsin(r) = a Then
                                    ok = False
                                    Exit For
                                End If
                            Next r
                        End If
                        If ok Then
                            fam = CellText(vals(k, 54))
                            If Len(fam) > 0 Then
                                For r = 1 To nFam
                                    If onFam(r) = fam Then
                                        ok = False
                                        Exit For
                                    End If
                                Next r
                                If key = "CLEAN" Then
                                    For r = 1 To nPFam
                                        If pFam(r) = fam Then ok = False
                                    Next r
                                End If
                            End If
                        End If
                        If ok Then
                            v = sc / (1 + 0.12 * TabUseCount(wb, wsDest, a))
                            If v > bestV Then
                                bestV = v
                                j = k
                            End If
                        End If
                    End If
                End If
            Next k
            If j = 0 Then Exit For
            taken(j) = True
            nPart = nPart + 1
            partR(nPart) = j
            nPFam = nPFam + 1
            pFam(nPFam) = CellText(vals(j, 54))
        Next m
        leadQty = n - nPart
        If leadQty < 1 Then leadQty = 1
    End If

    ' --- write it into the order
    addedTxt = nm_of(vals, bestR)
    If recSel > 0 Then
        addedTxt = ""
        For m = 1 To nOut
            k = AddOrderRow(wsSrc, wsDest, colsToCopy, outRow(m), outQty(m), t)
            wsDest.Cells(k, 15).Value = gRecKey(recSel)
            Usage_Inc_AllInv CellText(vals(outRow(m), 4)), 1
            If m > 1 Then addedTxt = addedTxt & vbCrLf & "      + "
            addedTxt = addedTxt & nm_of(vals, outRow(m))
        Next m
        addedTxt = addedTxt & vbCrLf & "(set of " & gRecUnits(recSel) & ": " & gRecName(recSel) & ")"
    ElseIf bestMode = 3 Then
        AddOrderRow wsSrc, wsDest, colsToCopy, bestR, leadQty, t
        Usage_Inc_AllInv CellText(vals(bestR, 4)), 1
        For m = 1 To nPart
            AddOrderRow wsSrc, wsDest, colsToCopy, partR(m), 1, t
            Usage_Inc_AllInv CellText(vals(partR(m), 4)), 1
            addedTxt = addedTxt & vbCrLf & "      + " & nm_of(vals, partR(m))
        Next m
        addedTxt = addedTxt & vbCrLf & "(mix-and-match set of " & CellText(vals(bestR, 84)) & IIf(nPart < CLng(SafeDbl(vals(bestR, 84))) - 1, ", completed with extra units of the first product", "") & ")"
    Else
        AddOrderRow wsSrc, wsDest, colsToCopy, bestR, IIf(bestMode = 2, 1, 0), t
        Usage_Inc_AllInv CellText(vals(bestR, 4)), 1
        If bestMode = 2 Then addedTxt = addedTxt & vbCrLf & "(completes a set already in this order)"
    End If
    RefreshTotals wsDest, t
    SortActiveSheetByColumnA
    RewriteFormulas wsDest
    SummarizeAllSheets
    Application.Calculate
    LabelOrderTab wsDest
    ptsAfter = CountedPoints(wsDest, t - 1)
    Application.ScreenUpdating = True
    MsgBox "Added: " & addedTxt & vbCrLf & "Order now has " & ptsAfter & " points (was " & ptsNow & ").", vbInformation, "Add New Product"
End Sub

Public Sub Add_Extra_Product()
    Add_New_Product
End Sub


' a row whose column N starts with "Credit" is paid with the account credit ("Credit 1" = closest to the credit, "Credit 2" = most points)
Private Function IsCreditRow(ws As Worksheet, ByVal r As Long) As Boolean
    IsCreditRow = (Left$(CellText(ws.Cells(r, 14).Value), 6) = "Credit")
End Function

' recalculates one order tab. Inside Create_All_Orders only that tab is calculated (the Summary is rebuilt once at the end).
Private Sub CalcTab(ws As Worksheet)
    If gPendOn Then
        On Error Resume Next
        ws.Calculate
        If Err.Number <> 0 Then
            Err.Clear
            Application.Calculate
        End If
        On Error GoTo 0
    Else
        SummarizeAllSheets
        Application.Calculate
    End If
End Sub

' short name of a set group for the labels ("Toothpaste Set 1"): column CP of the group table, else made from the group's description
Private Function GroupShortName(wsSrc As Worksheet, ByVal key As String) As String
    Dim r As Long, nm As String, p As Long
    GroupShortName = key
    For r = 2 To 201
        If UCase$(CellText(wsSrc.Cells(r, 88).Value)) = UCase$(key) Then
            nm = CellText(wsSrc.Cells(r, 94).Value)
            If Len(nm) = 0 Then
                nm = CellText(wsSrc.Cells(r, 89).Value)
                p = InStr(nm, "-Pack")
                If p > 3 Then nm = Trim$(Left$(nm, p - 3))
            End If
            If Len(nm) > 0 Then GroupShortName = nm
            Exit Function
        End If
    Next r
End Function

'=====================================================================================
' LABELS of an order tab (so anybody can place the order on Melaleuca):
'   column H = comments:
'       "<Short name> Set of N"   a set of N different products of one group (every row of the set has it, N = size of the set)
'       "Set of N"                a set of N units of the same product
'       "Set with A, B"           a set that mixes products (Rinse Aid + Diamond Brite, Pain-A-Trate Original + Extra Strength...): the other products of the set
'       "Coupon of N"             a coupon deal: N units of the same product at the coupon price
'       "Add Bottle", "Add Pump"
'   column N = "Credit 1" / "Credit 2" (order to place the credit items) and the discount type:
'       "Combo" for every set, "Coupon" for a coupon deal, the sheet's Discount Type (column Y) for a plain discounted product
'   column M (formula) = "Discounted"
' Rows marked "Pack" in column H are left alone. The hidden column O holds the set key when the row was chosen as part of a recipe / coupon.
'=====================================================================================
Private Sub LabelOrderTab(ws As Worksheet)
    Dim wsSrc As Worksheet, vals As Variant, lastR As Long, last As Long
    Dim r As Long, r2 As Long, k As Long, m As Long, ri As Long
    Dim a As String, key As String, ov As String, nm As String, low As String, cn As Long, q As Double
    Dim gk(1 To 60) As String, gTot(1 To 60) As Double, gDone(1 To 60) As Double, gSize(1 To 60) As Long, gRows(1 To 60) As Long, nG As Long
    Dim mRow() As Long, eKey() As String
    Dim txt As String, note As String, cr As String, dt As String, disc As Boolean, shortN As String, others As String, nt As String, nt2 As String
    Dim s1 As Long, un0 As Double, full As Double, sz As Long, wU As Long, isCpn As Boolean

    Set wsSrc = ThisWorkbook.Sheets("MELALEUCA")
    lastR = SrcLastRow(wsSrc)
    vals = wsSrc.Range(wsSrc.Cells(1, 1), wsSrc.Cells(lastR, 94)).Value
    LoadRecipes wsSrc
    last = CountOrderRows(ws) + 1
    If last < 2 Then Exit Sub
    ReDim mRow(2 To last)
    ReDim eKey(2 To last)
    ' pass 1: Melaleuca row of every order row, its set key, and the units of every set
    For r = 2 To last
        a = CellText(ws.Cells(r, 2).Value)
        For k = 2 To lastR
            If CellText(vals(k, 4)) = a Then
                mRow(r) = k
                Exit For
            End If
        Next k
        If mRow(r) > 0 And CellText(ws.Cells(r, 8).Value) <> "Pack" Then
            ov = CellText(ws.Cells(r, 15).Value)
            If ov = "COUPON" Then
                key = ""
            ElseIf Len(ov) > 0 Then
                key = ov
            Else
                key = CellText(vals(mRow(r), 83))
            End If
            eKey(r) = key
            If Len(key) > 0 And Left$(key, 1) <> "#" Then
                m = 0
                For k = 1 To nG
                    If gk(k) = key Then m = k
                Next k
                If m = 0 And nG < 60 Then
                    nG = nG + 1
                    gk(nG) = key
                    ri = RecIdx(key)
                    If ri > 0 Then
                        gSize(nG) = gRecUnits(ri)
                    Else
                        gSize(nG) = CLng(SafeDbl(vals(mRow(r), 84)))
                    End If
                    m = nG
                End If
                If m > 0 Then
                    gTot(m) = gTot(m) + SafeDbl(ws.Cells(r, 9).Value)
                    gRows(m) = gRows(m) + 1
                End If
            End If
        End If
    Next r
    For k = 1 To nG
        If gk(k) = "CLEAN" Then
            If gTot(k) >= 3 And gTot(k) <= 5 Then gSize(k) = CLng(gTot(k)) Else gSize(k) = 0
        End If
    Next k

    ' pass 2: write the labels
    For r = 2 To last
        If CellText(ws.Cells(r, 8).Value) <> "Pack" And mRow(r) > 0 Then
            k = mRow(r)
            key = eKey(r)
            ov = CellText(ws.Cells(r, 15).Value)
            cn = CLng(SafeDbl(vals(k, 84)))
            q = SafeDbl(ws.Cells(r, 9).Value)
            nm = CellText(vals(k, 1))
            low = LCase$(nm)
            txt = ""
            note = ""
            dt = ""
            disc = False
            isCpn = (ov = "COUPON")
            If Not isCpn And Left$(key, 1) = "#" Then
                If LCase$(CellText(vals(k, 25))) = "coupon" And SafeDbl(vals(k, 23)) >= 2 And SafeDbl(vals(k, 22)) > 0 Then isCpn = True
            End If
            If isCpn Then
                If ov = "COUPON" Then wU = CLng(SafeDbl(vals(k, 79))) Else wU = cn
                If wU >= 2 And q >= wU Then
                    txt = "Coupon of " & wU
                    dt = "Coupon"
                    disc = True
                End If
            ElseIf Len(key) > 0 And Left$(key, 1) <> "#" Then
                m = 0
                For s1 = 1 To nG
                    If gk(s1) = key Then m = s1
                Next s1
                sz = gSize(m)
                un0 = gDone(m)
                ri = RecIdx(key)
                shortN = GroupShortName(wsSrc, key)
                If sz > 0 Then
                    full = Int(gTot(m) / sz) * sz
                Else
                    full = 0
                End If
                If sz > 0 And un0 < full Then
                    If gRows(m) = 1 Then
                        txt = "Set of " & sz
                    ElseIf ri > 0 Then
                        ' the other products of this set, short and by name
                        others = ""
                        nt = MemberNote(key, CellText(vals(k, 4)), nm)
                        For r2 = 2 To last
                            If r2 <> r And eKey(r2) = key And mRow(r2) > 0 Then
                                nt2 = MemberNote(key, CellText(vals(mRow(r2), 4)), CellText(vals(mRow(r2), 1)))
                                If nt2 <> nt And InStr(", " & others & ",", ", " & nt2 & ",") = 0 Then
                                    If Len(others) > 0 Then others = others & ", "
                                    others = others & nt2
                                End If
                            End If
                        Next r2
                        If Len(others) = 0 Or gRecLabel(ri) <> "WITH" Then
                            txt = "Set of " & sz
                        Else
                            txt = "Set with " & others
                        End If
                    Else
                        txt = shortN & " Set of " & sz
                    End If
                    dt = "Combo"
                    disc = True
                Else
                    txt = shortN & " (no set)"
                End If
                gDone(m) = un0 + q
            ElseIf Left$(key, 1) = "#" Then
                If cn >= 2 And q >= cn Then
                    txt = "Set of " & cn
                    disc = True
                    If SafeDbl(vals(k, 23)) > 0 And SafeDbl(vals(k, 22)) > 0 Then
                        ' the product's own discounted set (Special Offers, Outlet, ...)
                        dt = CleanDT(CellText(vals(k, 25)))
                        If Len(dt) = 0 Then dt = "Special Offers"
                    Else
                        dt = "Combo"
                    End If
                ElseIf cn = 1 And SafeDbl(vals(k, 22)) > 0 Then
                    disc = True
                    dt = CleanDT(CellText(vals(k, 25)))
                    If Len(dt) = 0 Then dt = "Special Offers"
                End If
            ElseIf SafeDbl(vals(k, 22)) > 0 And SafeDbl(vals(k, 23)) = 1 Then
                disc = True
                dt = CleanDT(CellText(vals(k, 25)))
                If Len(dt) = 0 Then dt = "Special Offers"
            End If
            If Len(txt) = 0 Then txt = "Single"
            If InStr(low, "with bottle") > 0 Or InStr(low, "w/ bottle") > 0 Or InStr(low, "sprayer") > 0 Then
                If InStr(low, "revive") = 0 Then note = "Add Bottle"
            End If
            If InStr(low, "with pump") > 0 Or (InStr(low, "hand wash") > 0 And InStr(low, "refill") = 0 And (InStr(low, "renew") > 0 Or InStr(low, "sun valley") > 0)) _
               Or (InStr(low, "herbal shampoo") > 0 And InStr(low, "32oz") > 0) Then
                If Len(note) > 0 Then note = note & ", "
                note = note & "Add Pump"
            End If
            If Len(note) > 0 Then
                If Len(txt) > 0 Then txt = txt & ", "
                txt = txt & note
            End If
            ' column N: credit order + discount type
            cr = ""
            If IsCreditRow(ws, r) Then cr = Left$(CellText(ws.Cells(r, 14).Value), 8)
            If Len(cr) > 0 Then cr = Trim$(Replace(Left$(cr, 8), "|", ""))
            If Not disc Then dt = ""
            If Len(cr) > 0 And Len(dt) > 0 Then
                cr = cr & " | " & dt
            ElseIf Len(dt) > 0 Then
                cr = dt
            ElseIf Len(cr) = 0 Then
                cr = "Regular"
            End If
            If Len(txt) > 0 Then
                ws.Cells(r, 8).Value = txt
            Else
                ws.Cells(r, 8).ClearContents
            End If
            If Len(cr) > 0 Then
                ws.Cells(r, 14).Value = cr
            Else
                ws.Cells(r, 14).ClearContents
            End If
            ws.Cells(r, 8).HorizontalAlignment = xlCenter
            ws.Cells(r, 8).Font.Bold = False
            ws.Cells(r, 8).Font.Color = RGB(64, 64, 64)
            ws.Cells(r, 14).HorizontalAlignment = xlCenter
            ws.Cells(r, 14).Font.Bold = (Left$(cr, 6) = "Credit")
            If Left$(cr, 6) = "Credit" Then ws.Cells(r, 14).Font.Color = RGB(0, 128, 64) Else ws.Cells(r, 14).Font.Color = RGB(64, 64, 64)
        End If
    Next r
End Sub

' how many of the other tabs' products this tab shares with its closest tab (share of all products of both tabs)
Private Function ClosestOverlap(ws As Worksheet) As Double
    Dim wb As Workbook, s As Long, o As Worksheet, r As Long, r2 As Long
    Dim n1 As Long, n2 As Long, sh As Long, best As Double, jac As Double, a As String
    Set wb = ThisWorkbook
    n1 = CountOrderRows(ws)
    For s = FirstOrderIdx() To wb.Sheets.count
        Set o = wb.Sheets(s)
        If IsOrderTab(o) And o.Name <> ws.Name Then
            n2 = CountOrderRows(o)
            If n2 > 0 And n1 > 0 Then
                sh = 0
                For r = 2 To n1 + 1
                    a = CellText(ws.Cells(r, 2).Value)
                    For r2 = 2 To n2 + 1
                        If CellText(o.Cells(r2, 2).Value) = a Then
                            sh = sh + 1
                            Exit For
                        End If
                    Next r2
                Next r
                jac = sh / (n1 + n2 - sh)
                If jac > best Then best = jac
            End If
        End If
    Next s
    ClosestOverlap = best
End Function

' number of other products of a set group that could still be added to this tab (used before a new set is started)
Private Function CountPartners(vals As Variant, ByVal lastR As Long, ByVal key As String, ByVal selfRow As Long, ByVal fbaOnly As Boolean, _
                               onAsin() As String, ByVal nOn As Long, onFam() As String, ByVal nFam As Long) As Long
    Dim k As Long, j As Long, ok As Boolean, a As String, typ As String, fda As String, fam As String, pr As Double
    For k = 2 To lastR
        If k <> selfRow Then
            If CellText(vals(k, 83)) = key Then
                a = CellText(vals(k, 4))
                ok = (Len(a) > 0)
                typ = UCase$(CellText(vals(k, 3)))
                fda = CellText(vals(k, 56))
                If fbaOnly Then
                    If typ = "M" Then ok = False
                    If Len(fda) > 0 And fda <> "0" Then ok = False
                End If
                pr = SafeDbl(vals(k, 13))
                If pr < 1 Or pr > 100 Then ok = False
                If SafeDbl(vals(k, 72)) <= 0 Then ok = False
                For j = 1 To nOn
                    If onAsin(j) = a Then ok = False
                Next j
                fam = CellText(vals(k, 54))
                If Len(fam) > 0 Then
                    For j = 1 To nFam
                        If onFam(j) = fam Then ok = False
                    Next j
                End If
                If ok Then CountPartners = CountPartners + 1
            End If
        End If
    Next k
End Function

Private Function nm_of(vals As Variant, ByVal r As Long) As String
    nm_of = CellText(vals(r, 1)) & "  (" & CellText(vals(r, 4)) & ")"
End Function




' ------------------------------------------------------------
' -------------- SHARED / MACRO-SCOPED HELPERS ---------------
' ------------------------------------------------------------

' Build ASIN set from tabs index >=5 (skip current & hidden). Stop at first blank/formula-empty ASIN in col B.
Private Function BuildCrossTabUsedASINs_General(wb As Workbook, wsCurrent As Worksheet) As Object
    Dim d As Object: Set d = CreateObject("Scripting.Dictionary")
    Dim s As Long, r As Long
    Dim ws As Worksheet, asin As String

    For s = FirstOrderIdx() To wb.Sheets.count
        Set ws = wb.Sheets(s)
        If ws.Name <> wsCurrent.Name And ws.Visible = xlSheetVisible Then
            r = 2
            Do While True
                If Len(Trim$(CStr(ws.Cells(r, 2).Value))) = 0 Then Exit Do ' col B (ASIN) blank ? stop
                asin = Trim$(CStr(ws.Cells(r, 2).Value))
                If Len(asin) > 0 Then
                    If Not d.Exists(asin) Then d.Add asin, True
                End If
                r = r + 1
            Loop
        End If
    Next s

    Set BuildCrossTabUsedASINs_General = d
End Function

' Place up to quota from [minP..maxP], skipping 101, avoiding cross-dup (unless relaxed),
' avoiding duplicates inside the current tab, and avoiding duplicate family IDs (BB).
Private Function PlaceBucket_AllInv(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, _
    usableLastRow As Long, minP As Long, maxP As Long, quota As Long, _
    ByRef i As Long, ByRef usedRows As Object, ByVal crossUsed As Object, _
    ByVal pickedAsins As Object, ByVal pickedFamilies As Object, _
    ByVal avoidCrossDupes As Boolean, ByVal allowLE25CrossDupes As Boolean) As Long

    Dim candRows() As Long, c As Long, r As Long, pr As Double
    Dim asin As String, pass As Boolean, famID As String

    If quota <= 0 Then Exit Function

    ' --- Collect candidates
    For r = 2 To usableLastRow
        If Len(Trim$(CStr(wsSrc.Cells(r, 1).Value))) > 0 Then
            pr = SafeDbl(wsSrc.Cells(r, 13).Value)                ' Priority (M)
            If pr >= minP And pr <= maxP And pr >= 1 And pr <= 100 Then
                asin = Trim$(CStr(wsSrc.Cells(r, 4).Value))       ' ASIN (D)
                famID = Trim$(CStr(wsSrc.Cells(r, 54).Value))     ' Family ID (BB)
                If Len(asin) > 0 Then
                    pass = True

                    ' Cross-tab ASIN de-dupe
                    If avoidCrossDupes Then
                        If crossUsed.Exists(asin) Then
                            pass = (allowLE25CrossDupes And pr <= 25)
                        End If
                    End If

                    ' Within-tab family de-dupe
                    If pass And Len(famID) > 0 Then
                        If pickedFamilies.Exists(famID) Then
                            pass = False
                        End If
                    End If

                    ' Within-tab ASIN de-dupe & row de-dupe
                    If pass Then
                        If Not pickedAsins.Exists(asin) Then
                            If Not usedRows.Exists(r) Then
                                c = c + 1
                                ReDim Preserve candRows(1 To c)
                                candRows(c) = r
                            End If
                        End If
                    End If
                End If
            End If
        End If
    Next r

    If c = 0 Then Exit Function

    ' Sort by usage first, then random (usage-aware)
    UsageAwareSort_AllInv wsSrc, candRows

    ' --- Take up to quota
    Dim take As Long, k As Long, rowNum As Long
    Dim placed As Long

    take = Application.Min(quota, c)
    placed = 0

    For k = 1 To c
        If placed >= take Then Exit For

        rowNum = candRows(k)
        famID = Trim$(CStr(wsSrc.Cells(rowNum, 54).Value))
        asin = Trim$(CStr(wsSrc.Cells(rowNum, 4).Value))

        ' Double-check family at pick time to be safe
        If Len(famID) = 0 Or Not pickedFamilies.Exists(famID) Then
            CopyOneRow_AllInv wsSrc, wsDest, colsToCopy, rowNum, i
            usedRows.Add rowNum, True
            If Len(asin) > 0 Then pickedAsins.Add asin, True
            If Len(famID) > 0 Then pickedFamilies.Add famID, True
            Usage_Inc_AllInv asin, 1
            i = i + 1
            placed = placed + 1
        End If
    Next k

    PlaceBucket_AllInv = placed
End Function

' FBA: same but also SKIPS MELALEUCA!C = "M".
' PLUS: skip products where MELALEUCA!BD (FDA Code) is NOT 0 and NOT blank.
Private Function PlaceBucket_FBA(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, _
    usableLastRow As Long, minP As Long, maxP As Long, quota As Long, _
    ByRef i As Long, ByRef usedRows As Object, ByVal crossUsed As Object, _
    ByVal pickedAsins As Object, ByVal pickedFamilies As Object, _
    ByVal avoidCrossDupes As Boolean, ByVal allowLE25CrossDupes As Boolean) As Long

    Dim candRows() As Long, c As Long, r As Long, pr As Double
    Dim asin As String, pass As Boolean, isM As Boolean, famID As String
    Dim fdaCode As String, isFood As Boolean

    If quota <= 0 Then Exit Function

    ' --- Collect candidates
    For r = 2 To usableLastRow
        If Len(Trim$(CStr(wsSrc.Cells(r, 1).Value))) > 0 Then

            isM = (UCase$(Trim$(CStr(wsSrc.Cells(r, 3).Value))) = "M") ' FBA: skip if col C = "M"
            If Not isM Then

                ' NEW: FDA Code filter (BD = 56). Skip if NOT blank and NOT "0".
                fdaCode = Trim$(CStr(wsSrc.Cells(r, 56).Value)) ' BD
                isFood = (Len(fdaCode) > 0 And fdaCode <> "0")
                If Not isFood Then

                    pr = SafeDbl(wsSrc.Cells(r, 13).Value)
                    If pr >= minP And pr <= maxP And pr >= 1 And pr <= 100 Then
                        asin = Trim$(CStr(wsSrc.Cells(r, 4).Value))
                        famID = Trim$(CStr(wsSrc.Cells(r, 54).Value))
                        If Len(asin) > 0 Then
                            pass = True

                            ' Cross-tab de-dupe
                            If avoidCrossDupes Then
                                If crossUsed.Exists(asin) Then
                                    pass = (allowLE25CrossDupes And pr <= 25)
                                End If
                            End If

                            ' Family de-dupe within tab
                            If pass And Len(famID) > 0 Then
                                If pickedFamilies.Exists(famID) Then
                                    pass = False
                                End If
                            End If

                            If pass Then
                                If Not pickedAsins.Exists(asin) Then
                                    If Not usedRows.Exists(r) Then
                                        c = c + 1
                                        ReDim Preserve candRows(1 To c)
                                        candRows(c) = r
                                    End If
                                End If
                            End If
                        End If
                    End If

                End If ' FDA filter
            End If ' isM
        End If
    Next r

    If c = 0 Then Exit Function

    UsageAwareSort_FBA wsSrc, candRows

    Dim take As Long, k As Long, rowNum As Long
    Dim placed As Long

    take = Application.Min(quota, c)
    placed = 0

    For k = 1 To c
        If placed >= take Then Exit For

        rowNum = candRows(k)
        famID = Trim$(CStr(wsSrc.Cells(rowNum, 54).Value))
        asin = Trim$(CStr(wsSrc.Cells(rowNum, 4).Value))

        If Len(famID) = 0 Or Not pickedFamilies.Exists(famID) Then
            CopyOneRow_FBA wsSrc, wsDest, colsToCopy, rowNum, i
            usedRows.Add rowNum, True
            If Len(asin) > 0 Then pickedAsins.Add asin, True
            If Len(famID) > 0 Then pickedFamilies.Add famID, True
            Usage_Inc_AllInv asin, 1      ' share usage
            i = i + 1
            placed = placed + 1
        End If
    Next k

    PlaceBucket_FBA = placed
End Function

' Last resort: allow in-sheet repeats (kept minimal), still respecting family ID.
Private Function LastResortRepeat_AllInv(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, _
    usableLastRow As Long, minP As Long, maxP As Long, need As Long, _
    ByVal pickedFamilies As Object) As Long

    Dim candRows() As Long, c As Long, r As Long, pr As Double

    If need <= 0 Then Exit Function

    For r = 2 To usableLastRow
        If Len(Trim$(CStr(wsSrc.Cells(r, 1).Value))) > 0 Then
            pr = SafeDbl(wsSrc.Cells(r, 13).Value)
            If pr >= minP And pr <= maxP And pr >= 1 And pr <= 100 Then
                c = c + 1
                ReDim Preserve candRows(1 To c)
                candRows(c) = r
            End If
        End If
    Next r

    If c = 0 Then Exit Function

    UsageAwareSort_AllInv wsSrc, candRows

    Dim take As Long, k As Long, rowNum As Long, iDest As Long
    Dim famID As String, placed As Long, asin As String

    take = Application.Min(need, c)
    iDest = wsDest.Cells(wsDest.Rows.count, 2).End(xlUp).Row + 1
    If iDest < 2 Then iDest = 2

    placed = 0
    For k = 1 To c
        If placed >= take Then Exit For

        rowNum = candRows(k)
        famID = Trim$(CStr(wsSrc.Cells(rowNum, 54).Value))

        If Len(famID) = 0 Or Not pickedFamilies.Exists(famID) Then
            CopyOneRow_AllInv wsSrc, wsDest, colsToCopy, rowNum, iDest
            asin = Trim$(CStr(wsSrc.Cells(rowNum, 4).Value))
            If Len(asin) > 0 Then Usage_Inc_AllInv asin, 1
            If Len(famID) > 0 Then pickedFamilies.Add famID, True
            iDest = iDest + 1
            placed = placed + 1
        End If
    Next k

    LastResortRepeat_AllInv = placed
End Function

Private Function LastResortRepeat_FBA(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, _
    usableLastRow As Long, minP As Long, maxP As Long, need As Long, _
    ByVal pickedFamilies As Object) As Long

    Dim candRows() As Long, c As Long, r As Long, pr As Double, isM As Boolean
    Dim fdaCode As String, isFood As Boolean

    If need <= 0 Then Exit Function

    For r = 2 To usableLastRow
        If Len(Trim$(CStr(wsSrc.Cells(r, 1).Value))) > 0 Then

            isM = (UCase$(Trim$(CStr(wsSrc.Cells(r, 3).Value))) = "M")
            If Not isM Then

                ' NEW: FDA Code filter (BD = 56). Skip if NOT blank and NOT "0".
                fdaCode = Trim$(CStr(wsSrc.Cells(r, 56).Value)) ' BD
                isFood = (Len(fdaCode) > 0 And fdaCode <> "0")
                If Not isFood Then

                    pr = SafeDbl(wsSrc.Cells(r, 13).Value)
                    If pr >= minP And pr <= maxP And pr >= 1 And pr <= 100 Then
                        c = c + 1
                        ReDim Preserve candRows(1 To c)
                        candRows(c) = r
                    End If

                End If ' FDA filter
            End If
        End If
    Next r

    If c = 0 Then Exit Function

    UsageAwareSort_FBA wsSrc, candRows

    Dim take As Long, k As Long, rowNum As Long, iDest As Long
    Dim famID As String, placed As Long, asin As String

    take = Application.Min(need, c)
    iDest = wsDest.Cells(wsDest.Rows.count, 2).End(xlUp).Row + 1
    If iDest < 2 Then iDest = 2

    placed = 0
    For k = 1 To c
        If placed >= take Then Exit For

        rowNum = candRows(k)
        famID = Trim$(CStr(wsSrc.Cells(rowNum, 54).Value))

        If Len(famID) = 0 Or Not pickedFamilies.Exists(famID) Then
            CopyOneRow_FBA wsSrc, wsDest, colsToCopy, rowNum, iDest
            asin = Trim$(CStr(wsSrc.Cells(rowNum, 4).Value))
            If Len(asin) > 0 Then Usage_Inc_AllInv asin, 1
            If Len(famID) > 0 Then pickedFamilies.Add famID, True
            iDest = iDest + 1
            placed = placed + 1
        End If
    Next k

    LastResortRepeat_FBA = placed
End Function

' Copy one source row -> destination row i (keeps your formulas/columns exactly as before)
Private Sub CopyOneRow_AllInv(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, rowNum As Long, ByVal i As Long)
    Dim colIndex As Variant, setN As Double
    Dim destCol As Long: destCol = 1

    For Each colIndex In colsToCopy
        wsDest.Cells(i, destCol).Value = wsSrc.Cells(rowNum, colIndex).Value
        destCol = destCol + 1
    Next colIndex

    ' Quantity = set size (manual set in W, or a cheaper pack found by Relink_Packs) else 1
    setN = SafeDbl(wsSrc.Cells(rowNum, 79).Value)
    If setN > 0 Then
        wsDest.Cells(i, 9).Value = setN
    Else
        wsDest.Cells(i, 9).Value = 1
    End If

    ' Total WS / Profit / Points / flag are set-aware, so changing the quantity later keeps the points right
    SetRowFormulas wsDest, i, rowNum
End Sub

' FBA copy (same, FBA rule enforced earlier during candidate build)
Private Sub CopyOneRow_FBA(wsSrc As Worksheet, wsDest As Worksheet, colsToCopy As Variant, rowNum As Long, ByVal i As Long)
    Dim colIndex As Variant, setN As Double
    Dim destCol As Long: destCol = 1

    For Each colIndex In colsToCopy
        wsDest.Cells(i, destCol).Value = wsSrc.Cells(rowNum, colIndex).Value
        destCol = destCol + 1
    Next colIndex

    ' Quantity = set size (manual set in W, or a cheaper pack found by Relink_Packs) else 1
    setN = SafeDbl(wsSrc.Cells(rowNum, 79).Value)
    If setN > 0 Then
        wsDest.Cells(i, 9).Value = setN
    Else
        wsDest.Cells(i, 9).Value = 1
    End If

    ' Total WS / Profit / Points / flag are set-aware, so changing the quantity later keeps the points right
    SetRowFormulas wsDest, i, rowNum
End Sub

' Usage-aware ordering: lower usage first + random jitter (safe bounds).
Private Sub UsageAwareSort_AllInv(wsSrc As Worksheet, ByRef cand() As Long)
    Dim lb As Long, ub As Long, i As Long, j As Long, k As Long
    Dim usage() As Long, jitter() As Double
    Dim tmpRow As Long, tmpU As Long, tmpJ As Double, asin As String

    If Not IsArray(cand) Then Exit Sub
    On Error Resume Next
    lb = LBound(cand): ub = UBound(cand)
    On Error GoTo 0
    If ub <= lb Then Exit Sub

    ReDim usage(lb To ub)
    ReDim jitter(lb To ub)

    For k = lb To ub
        asin = CStr(wsSrc.Cells(cand(k), 4).Value)
        usage(k) = Usage_Get_AllInv(asin)
        jitter(k) = Rnd()    ' tie-breaker
    Next k

    For i = lb + 1 To ub
        tmpRow = cand(i): tmpU = usage(i): tmpJ = jitter(i)
        j = i - 1
        Do While j >= lb
            If (usage(j) > tmpU) Or (usage(j) = tmpU And jitter(j) > tmpJ) Then
                usage(j + 1) = usage(j)
                jitter(j + 1) = jitter(j)
                cand(j + 1) = cand(j)
                j = j - 1
            Else
                Exit Do
            End If
        Loop
        usage(j + 1) = tmpU
        jitter(j + 1) = tmpJ
        cand(j + 1) = tmpRow
    Next i
End Sub

Private Sub UsageAwareSort_FBA(wsSrc As Worksheet, ByRef cand() As Long)
    Dim lb As Long, ub As Long, i As Long, j As Long, k As Long
    Dim usage() As Long, jitter() As Double
    Dim tmpRow As Long, tmpU As Long, tmpJ As Double, asin As String

    If Not IsArray(cand) Then Exit Sub
    On Error Resume Next
    lb = LBound(cand): ub = UBound(cand)
    On Error GoTo 0
    If ub <= lb Then Exit Sub

    ReDim usage(lb To ub)
    ReDim jitter(lb To ub)

    For k = lb To ub
        asin = CStr(wsSrc.Cells(cand(k), 4).Value)
        usage(k) = Usage_Get_AllInv(asin)
        jitter(k) = Rnd()
    Next k

    For i = lb + 1 To ub
        tmpRow = cand(i): tmpU = usage(i): tmpJ = jitter(i)
        j = i - 1
        Do While j >= lb
            If (usage(j) > tmpU) Or (usage(j) = tmpU And jitter(j) > tmpJ) Then
                usage(j + 1) = usage(j)
                jitter(j + 1) = jitter(j)
                cand(j + 1) = cand(j)
                j = j - 1
            Else
                Exit Do
            End If
        Loop
        usage(j + 1) = tmpU
        jitter(j + 1) = tmpJ
        cand(j + 1) = tmpRow
    Next i
End Sub

' number from a cell that may hold text such as "$37.99" or "10.46"
Private Function MoneyVal(v As Variant) As Double
    Dim s As String
    If IsError(v) Then Exit Function
    If IsNumeric(v) And VarType(v) <> vbString Then
        MoneyVal = CDbl(v)
        Exit Function
    End If
    s = Replace(Replace(Trim$(CStr(v)), "$", ""), ",", "")
    If Len(s) > 0 Then
        If IsNumeric(s) Then MoneyVal = Val(s)
    End If
End Function

Private Function SafeDbl(v As Variant) As Double
    On Error Resume Next
    If IsNumeric(v) Then SafeDbl = CDbl(v) Else SafeDbl = 0
End Function

' --- Usage tracking via hidden PICK_USAGE (shared by both macros) ---
Private Function UsageSheet_AllInv() As Worksheet
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets("PICK_USAGE")
    On Error GoTo 0
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.count))
        ws.Name = "PICK_USAGE"
        ws.Range("A1:B1").Value = Array("ASIN", "COUNT")
        ws.Visible = xlSheetHidden
    End If
    Set UsageSheet_AllInv = ws
End Function

Private Function Usage_Get_AllInv(ByVal asin As String) As Long
    Dim ws As Worksheet, lastRow As Long, f As Range
    If Len(asin) = 0 Then Exit Function
    Set ws = UsageSheet_AllInv()
    lastRow = ws.Cells(ws.Rows.count, "A").End(xlUp).Row
    If lastRow >= 2 Then
        Set f = ws.Range("A2:A" & lastRow).Find(What:=asin, LookIn:=xlValues, LookAt:=xlWhole)
        If Not f Is Nothing Then Usage_Get_AllInv = CLng(Val(ws.Cells(f.Row, 2).Value))
    End If
End Function

Private Sub Usage_Inc_AllInv(ByVal asin As String, ByVal inc As Long)
    Dim ws As Worksheet, lastRow As Long, f As Range
    If Len(asin) = 0 Then Exit Sub
    Set ws = UsageSheet_AllInv()
    lastRow = ws.Cells(ws.Rows.count, "A").End(xlUp).Row
    If lastRow >= 2 Then
        Set f = ws.Range("A2:A" & lastRow).Find(What:=asin, LookIn:=xlValues, LookAt:=xlWhole)
    End If
    If f Is Nothing Then
        ws.Cells(IIf(lastRow < 2, 2, lastRow + 1), 1).Value = asin
        ws.Cells(IIf(lastRow < 2, 2, lastRow + 1), 2).Value = inc
    Else
        ws.Cells(f.Row, 2).Value = CLng(Val(ws.Cells(f.Row, 2).Value)) + inc
    End If
End Sub


