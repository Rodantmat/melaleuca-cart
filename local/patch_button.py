"""adds the 'Auto-Fill Cart' button to the 17 order-tab drawings of an .xlsm (XML level; the macro project is not touched)
   python patch_button.py in.xlsm out.xlsm"""
import zipfile, re, sys
src, dst = sys.argv[1], sys.argv[2]
zin = zipfile.ZipFile(src)
zout = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
def button(n):
    return ('<xdr:oneCellAnchor><xdr:from><xdr:col>15</xdr:col><xdr:colOff>57150</xdr:colOff><xdr:row>5</xdr:row><xdr:rowOff>152400</xdr:rowOff></xdr:from><xdr:ext cx="1619250" cy="228600"/>'
    '<xdr:sp macro="[0]!Auto_Fill_Cart" textlink=""><xdr:nvSpPr><xdr:cNvPr id="%d" name="btnAutoFillCart"/><xdr:cNvSpPr/></xdr:nvSpPr><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1619250" cy="228600"/></a:xfrm>'
    '<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 25000"/></a:avLst></a:prstGeom><a:solidFill><a:srgbClr val="C0392B"/></a:solidFill><a:ln w="9525"><a:solidFill><a:srgbClr val="FFFFFF"><a:alpha val="60000"/></a:srgbClr></a:solidFill></a:ln>'
    '<a:effectLst><a:outerShdw blurRad="38100" dist="19050" dir="5400000" algn="t" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="28000"/></a:srgbClr></a:outerShdw></a:effectLst></xdr:spPr>'
    '<xdr:txBody><a:bodyPr vertOverflow="clip" horzOverflow="clip" wrap="square" lIns="54000" tIns="18000" rIns="54000" bIns="18000" rtlCol="0" anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="en-US" sz="1000" b="1"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>Auto-Fill Cart</a:t></a:r></a:p></xdr:txBody></xdr:sp><xdr:clientData/></xdr:oneCellAnchor>') % n
cnt = 0
for it in zin.infolist():
    data = zin.read(it.filename)
    if re.fullmatch(r'xl/drawings/drawing\d+\.xml', it.filename):
        s = data.decode('utf8')
        if 'Add_New_Product' in s and 'Auto_Fill_Cart' not in s:     # an order tab
            ids = [int(x) for x in re.findall(r'<xdr:cNvPr id="(\d+)"', s)]
            s = s.replace('</xdr:wsDr>', button(max(ids) + 1) + '</xdr:wsDr>')
            data = s.encode('utf8'); cnt += 1
    zout.writestr(it, data)
zout.close()
print('buttons added on', cnt, 'order tabs')
