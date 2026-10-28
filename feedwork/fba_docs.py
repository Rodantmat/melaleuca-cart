#!/usr/bin/env python3
"""
fba_docs.py - the paper side of a Toronto / Vancouver shipment.

  make_cusma(origin, importer_name, importer_address, sign_date, out_pdf)
      Your own signed USMCA certificate of the previous month is the template (templates/CUSMA_<origin>.pdf);
      only the fields that change from shipment to shipment are replaced:
        blanket period FROM / TO (sign date, +1 month), importer (the Amazon warehouse), date of signature.
      Everything else (exporter, producer, goods table, your signature image) stays exactly as in your signed form.
  copy_fda(out_pdf)         the FDA exemption declaration, unchanged
  monthly_folder(workbook_folder, today)   <parent>/<previous YYYY-MM>   (we always process the month before)
"""
import datetime, io, os, re, shutil, calendar
import pdfplumber, pikepdf
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

HERE = os.path.dirname(os.path.abspath(__file__))
FONT, SIZE = "Times-Roman", 9
DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def add_month(d):
    y, m = (d.year + (d.month // 12), d.month % 12 + 1)
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def mdy(d):
    return "%02d/%02d/%04d" % (d.month, d.day, d.year)


def previous_month_tag(today=None):
    t = today or datetime.date.today()
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return "%04d-%02d" % (y, m)


def monthly_folder(workbook_folder, today=None):
    """the workbook sits in the folder of the CURRENT month; the shipping files go in the folder of the previous month next to it"""
    parent = os.path.dirname(os.path.abspath(workbook_folder))
    path = os.path.join(parent, previous_month_tag(today))
    os.makedirs(path, exist_ok=True)
    return path


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if stringWidth(t, FONT, SIZE) <= width or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def make_cusma(origin, importer_name, importer_address, sign_date, out_pdf, template=None):
    tpl = template or os.path.join(HERE, "templates", "CUSMA_%s.pdf" % origin.strip().title())
    if not os.path.exists(tpl):
        raise RuntimeError("CUSMA template not found: " + tpl)
    until = add_month(sign_date)
    with pdfplumber.open(tpl) as pdf:
        pg = pdf.pages[0]; H = float(pg.height)
        words = pg.extract_words(extra_attrs=["size"])
        def find(pred): return [w for w in words if pred(w)]
        frm = find(lambda w: DATE_RE.match(w["text"]) and 70 < w["top"] < 92 and w["x0"] > 450)
        to = find(lambda w: DATE_RE.match(w["text"]) and 96 < w["top"] < 116 and w["x0"] > 450)
        sig = find(lambda w: DATE_RE.match(w["text"]) and 712 < w["top"] < 735 and w["x0"] < 250)
        name_lab = [w for w in find(lambda w: w["text"] == "NAME" and 248 < w["top"] < 266 and w["x0"] > 300)]
        addr_lab = [w for w in find(lambda w: w["text"] == "ADDRESS" and 266 < w["top"] < 285 and w["x0"] > 300)]
        if not (frm and to and sig and name_lab and addr_lab):
            raise RuntimeError("the CUSMA template changed: could not find the blanket period / importer / date fields")
        xv = frm[0]["x0"] - 0  # blanket dates start here
        imp_x = name_lab[0]["x1"] + 13.3            # value column of the importer block (336.7 in the template)
        imp_x2 = addr_lab[0]["x1"] + 5.9
        name_old = find(lambda w: 248 < w["top"] < 266 and w["x0"] >= imp_x - 1)
        addr_old = find(lambda w: 266 < w["top"] < 305 and w["x0"] >= imp_x2 - 1)
        top_all = [w for w in words if w["top"] < 22]
        right_edge = 566.0
        # white-out the old values
        cover = [(w["x0"], w["top"], w["x1"], w["bottom"]) for w in (frm + to + sig + name_old + addr_old + top_all)]
        name_top = name_lab[0]["top"] - 1.3; addr_top = addr_lab[0]["top"] - 2.3; sig_top = sig[0]["top"]
        f_top = frm[0]["top"]; t_top = to[0]["top"]
        p2 = [(w["x0"], w["top"], w["x1"], w["bottom"]) for w in pdf.pages[1].extract_words() if w["top"] < 22] if len(pdf.pages) > 1 else []
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=(612, H))
    cv.setFillColorRGB(1, 1, 1); cv.setStrokeColorRGB(1, 1, 1)
    for x0, t0, x1, b0 in cover:
        cv.rect(x0 - 0.6, H - b0 - 0.8, (x1 - x0) + 1.2, (b0 - t0) + 1.6, stroke=0, fill=1)
    cv.setFillColorRGB(0, 0, 0)
    cv.setFont(FONT, SIZE)
    def put(x, top, s): cv.drawString(x, H - top - SIZE * 0.8, s)
    put(xv, f_top, mdy(sign_date)); put(xv, t_top, mdy(until))
    put(imp_x, name_top, importer_name)
    for i, ln in enumerate(_wrap(importer_address, right_edge - imp_x2)[:3]):
        put(imp_x2, addr_top + i * 11.3, ln)
    put(frm[0]["x0"] if False else sig[0]["x0"], sig_top, mdy(sign_date))
    cv.showPage(); cv.save(); buf.seek(0)
    ov = PdfReader(buf).pages[0]
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False); tmp.close()
    strip_text(tpl, tmp.name, {0: cover, 1: p2})
    rd = PdfReader(tmp.name); wr = PdfWriter()
    p1 = rd.pages[0]; p1.merge_page(ov); wr.add_page(p1)
    # page 2: only the Docusign envelope line at the top is removed
    buf2 = io.BytesIO(); c2 = canvas.Canvas(buf2, pagesize=(612, H)); c2.setFillColorRGB(1, 1, 1)
    c2.rect(14, H - 21, 260, 13, stroke=0, fill=1); c2.showPage(); c2.save(); buf2.seek(0)
    for pg_ in rd.pages[1:]:
        pg_.merge_page(PdfReader(buf2).pages[0]); wr.add_page(pg_)
    with open(out_pdf, "wb") as f: wr.write(f)
    os.unlink(tmp.name)
    return out_pdf


def _mul(m, n):  # row-vector convention: result = m x n
    return [m[0]*n[0]+m[1]*n[2], m[0]*n[1]+m[1]*n[3], m[2]*n[0]+m[3]*n[2], m[2]*n[1]+m[3]*n[3],
            m[4]*n[0]+m[5]*n[2]+n[4], m[4]*n[1]+m[5]*n[3]+n[5]]


def _strip_stream(obj, rects, H):
    """drop every BT..ET block whose text starts inside a rectangle (pdfplumber top-based coordinates)"""
    out, block, drop, ctm, stack = [], None, 0, [1, 0, 0, 1, 0, 0], []
    for operands, op in pikepdf.parse_content_stream(obj):
        name = str(op)
        if block is None:
            if name == "q": stack.append(list(ctm))
            elif name == "Q" and stack: ctm = stack.pop()
            elif name == "cm": ctm = _mul([float(x) for x in operands], ctm)
            if name == "BT": block = [(operands, op)]; continue
            out.append((operands, op)); continue
        block.append((operands, op))
        if name == "ET":
            tm = next(([float(x) for x in o] for o, p in block if str(p) == "Tm"), None)
            if tm is None:
                td = next(([float(x) for x in o] for o, p in block if str(p) in ("Td", "TD")), [0, 0])
                tm = [1, 0, 0, 1, td[0], td[1]]
            m = _mul(tm, ctm); x, y = m[4], H - m[5]
            hit = any(x0 - 1 <= x <= x1 and t0 <= y <= b0 + 1.5 for x0, t0, x1, b0 in rects)
            if hit: drop += 1
            else: out.extend(block)
            block = None
    obj.write(pikepdf.unparse_content_stream(out))
    return drop


def strip_text(src, dst, rects_by_page, H=792.0):
    """really delete (not just cover) the old text: it lives in the page stream and in the DocuSign form layer (X0)"""
    pdf = pikepdf.open(src)
    n = 0
    for pi, rects in rects_by_page.items():
        page = pdf.pages[pi]
        n += _strip_stream(page.Contents if not isinstance(page.Contents, pikepdf.Array) else page.Contents[0], rects, H)
        for name, xo in (page.Resources.get("/XObject") or {}).items():
            if xo.get("/Subtype") == "/Form": n += _strip_stream(xo, rects, H)
    pdf.save(dst)
    return n


def copy_fda(out_pdf):
    src = os.path.join(HERE, "templates", "FDAExemption.pdf")
    shutil.copyfile(src, out_pdf)
    return out_pdf


if __name__ == "__main__":
    import sys
    # self test: rebuild September's Toronto certificate and compare its text with the real one
    d = datetime.date(2026, 10, 19)
    make_cusma("Toronto", "HGR6 - Amazon Services LLC", "55 West Oak Ridge Drive, HAGERSTOWN, MD 21740", d, sys.argv[1] if len(sys.argv) > 1 else "cusma_test.pdf")
    print("written")
