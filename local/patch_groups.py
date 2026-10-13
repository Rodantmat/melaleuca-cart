"""patch_groups.py in.xlsm out.xlsm  - removes from the Melaleuca tab's group table (CJ:CP) the three groups that have no store pack
(F264 MelaBoost, F2768 Sustain Active Hydration, F3771 SplasH2O): they were built from old Special Offers columns and the store gives no such set price.
Everything else in the workbook (macros included) is copied byte for byte."""
import sys, re, zipfile
KEYS = {"F264", "F2768", "F3771"}
COLS = ["CJ", "CK", "CL", "CM", "CN", "CO", "CP"]

def main(src, dst):
    zin = zipfile.ZipFile(src)
    wbx = zin.read("xl/workbook.xml").decode("utf-8")
    rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rid = re.search(r'<sheet name="Melaleuca"[^>]*r:id="(rId\d+)"', wbx).group(1)
    target = re.search(r'<Relationship Id="%s"[^>]*Target="([^"]+)"' % rid, rels).group(1)
    path = "xl/" + target.lstrip("/").replace("xl/", "")
    ss = zin.read("xl/sharedStrings.xml").decode("utf-8")
    sis = re.findall(r"<si>(.*?)</si>", ss, re.S)
    txt = lambda i: "".join(re.findall(r"<t[^>]*>(.*?)</t>", sis[i], re.S))
    bad = {i for i in range(len(sis)) if txt(i) in KEYS}
    xml = zin.read(path).decode("utf-8")
    n = 0
    def fix_row(m):
        nonlocal n
        row = m.group(0)
        r = re.search(r'<row r="(\d+)"', row).group(1)
        c = re.search(r'<c r="CJ%s"[^>]*t="s"[^>]*>\s*<v>(\d+)</v>' % r, row)
        if not c or int(c.group(1)) not in bad:
            return row
        for col in COLS:
            row, k = re.subn(r'<c r="%s%s"(?:[^>]*/>|[^>]*>.*?</c>)' % (col, r), "", row, flags=re.S)
            n += k
        return row
    xml2 = re.sub(r"<row [^>]*>.*?</row>", fix_row, xml, flags=re.S)
    print("cells removed:", n)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == path:
                data = xml2.encode("utf-8")
            zout.writestr(it, data)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
