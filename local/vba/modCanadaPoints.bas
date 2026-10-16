Attribute VB_Name = "modCanadaPoints"
Option Explicit
'=====================================================================
' Two points tables: American and Canadian.
'   The Canadian store gives a few products other points than the US store (e.g. PreSpot Gel 2-Pack: 3 in the US, 4 in Canada).
'   Sync_Canada_Points
'     1. runs melaleuca_points_ca.py (compares the saved US and Canadian store catalogs -> feed\points_ca.tsv)
'     2. makes the sheet "MelaleucaCA": a copy of "Melaleuca" where those products carry their Canadian points
'     3. points every Canadian (orange / yellow) order tab at MelaleucaCA instead of Melaleuca
'   The order builder (Module1: MelFor) does the same for tabs it writes, so Generate All Orders builds Canadian tabs with Canadian points.
'   It runs by itself at the start of Generate All Orders (and after Import Account Offers). Nothing to do by hand.
'=====================================================================
Private Const BASE_DIR As String = "C:\AmazonFeed\"
Private Const CA_NAME As String = "MelaleucaCA"

Private Function ReadUtf8(ByVal path As String) As String
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.LoadFromFile path
    ReadUtf8 = Replace(st.ReadText, vbCr, "")
    st.Close
End Function

Private Function HeaderCol(ws As Worksheet, ByVal txt As String) As Long
    Dim c As Long
    For c = 1 To 200
        If Trim$(CStr(ws.Cells(1, c).Value)) = txt Then HeaderCol = c: Exit Function
    Next c
End Function

Public Sub Sync_Canada_Points(Optional ByVal quiet As Boolean = False)
    Dim wb As Workbook, wm As Worksheet, wc As Worksheet, ws As Worksheet
    Dim sh As Object, lines() As String, p() As String, i As Long, r As Long
    Dim cMela As Long, cPts As Long, cPack As Long, cSet As Long
    Dim nSingle As Long, nGroup As Long, nTab As Long, nItems As Long
    Dim calcPrev As Long, upd As Boolean, item As String, ca As Double, rep As String, txt As String
    Set wb = ThisWorkbook
    On Error Resume Next
    Set wm = wb.Worksheets("Melaleuca")
    On Error GoTo 0
    If wm Is Nothing Then Exit Sub
    ' 1. the table of products with other Canadian points
    If Dir(BASE_DIR & "melaleuca_points_ca.py") <> "" Then
        On Error Resume Next
        Set sh = CreateObject("WScript.Shell")
        sh.Run "cmd /c ""cd /d " & Left$(BASE_DIR, Len(BASE_DIR) - 1) & " && set PYTHONIOENCODING=utf-8:replace&& python melaleuca_points_ca.py feed > feed\points_ca_log.txt 2>&1""", 0, True
        On Error GoTo 0
    End If
    If Dir(BASE_DIR & "feed\points_ca.tsv") = "" Then
        If Not quiet Then MsgBox "No Canadian points table yet (feed\points_ca.tsv). Run Update Melaleuca Data / one Canadian fill first, then Generate All Orders.", vbInformation, "Canadian points"
        Exit Sub
    End If
    cMela = HeaderCol(wm, "Mela ID"): cPts = HeaderCol(wm, "Pts")
    cPack = HeaderCol(wm, "GROUP: pack item no."): cSet = HeaderCol(wm, "GROUP: set points (all units)")
    If cMela = 0 Or cPts = 0 Then Exit Sub
    upd = Application.ScreenUpdating: calcPrev = Application.Calculation
    Application.ScreenUpdating = False: Application.Calculation = xlCalculationManual: Application.DisplayAlerts = False
    On Error GoTo failed
    ' 2. the sheet MelaleucaCA
    On Error Resume Next
    wb.Worksheets(CA_NAME).Delete
    On Error GoTo failed
    wm.Copy After:=wm
    Set wc = ActiveSheet
    wc.Name = CA_NAME
    wc.Tab.Color = RGB(160, 160, 160)
    lines = Split(ReadUtf8(BASE_DIR & "feed\points_ca.tsv"), vbLf)
    For i = 1 To UBound(lines)
        p = Split(lines(i), vbTab)
        If UBound(p) >= 3 Then
            item = Trim$(p(0)): ca = Val(p(3))
            If Len(item) > 0 Then
                nItems = nItems + 1
                For r = 2 To 700
                    If CStr(wc.Cells(r, cMela).Value) = item Then
                        If Not wc.Cells(r, cPts).HasFormula Then wc.Cells(r, cPts).Value = ca: nSingle = nSingle + 1
                    End If
                Next r
                If cPack > 0 And cSet > 0 Then
                    For r = 2 To 201
                        If CStr(wc.Cells(r, cPack).Value) = item Then
                            If Not wc.Cells(r, cSet).HasFormula Then wc.Cells(r, cSet).Value = ca: nGroup = nGroup + 1
                        End If
                    Next r
                End If
            End If
        End If
    Next i
    ' 3. the Canadian order tabs read MelaleucaCA
    For Each ws In wb.Worksheets
        Select Case UCase$(ws.Name)
            Case "MELALEUCA", "MELALEUCACA", "ACCOUNTOFFERS", "SUMMARY", "MENU", "INVENTORY", "FBA", "PICK_USAGE"
            Case Else
                If Application.Run("MelFor", ws) = CA_NAME Then
                    ws.Cells.Replace What:="Melaleuca!", Replacement:=CA_NAME & "!", LookAt:=xlPart, MatchCase:=True
                    nTab = nTab + 1
                End If
        End Select
    Next ws
    wm.Activate
    Application.DisplayAlerts = True
    Application.Calculation = calcPrev
    If calcPrev = xlCalculationAutomatic Then Application.Calculate
    Application.ScreenUpdating = upd
    rep = "Canadian points: " & nItems & " product(s) with other points than in the US store (" & nSingle & " single row(s), " & nGroup & " pack/set row(s) changed in " & CA_NAME & "); " & nTab & " Canadian tab(s) read " & CA_NAME & "."
    If Not quiet Then MsgBox rep, vbInformation, "Canadian points"
    Exit Sub
failed:
    txt = Err.Description
    Application.DisplayAlerts = True
    Application.Calculation = calcPrev
    Application.ScreenUpdating = upd
    If Not quiet Then MsgBox "The Canadian points could not be set up: " & txt, vbExclamation, "Canadian points"
End Sub
