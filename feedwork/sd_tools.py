#!/usr/bin/env python3
"""
sd_tools.py - helper for the San Diego / Vancouver / Toronto AutoReport workbooks (no extra packages needed).

  python sd_tools.py labels  input.tsv  output.pdf  30|thermal
        Asks AMAZON for the product labels (Fulfillment Inbound API, createMarketplaceItemLabels), so the PDF is
        exactly what Seller Central prints.  Uses credentials.txt (the same one as amazon_feed.py).
        input.tsv : one product per line:  SKU <TAB> FNSKU <TAB> title <TAB> quantity   (UTF-8)
        30        : "30 Labels Sheet"  (Letter_30)
        thermal   : 25x50 Thermal Labels (50 x 25 mm, one label per page)

  python sd_tools.py numbers  file.numbers  output.tsv
        reads the first table of an Apple Numbers file and writes it as a tab separated file
        (row number, column number, type, value) so the workbook can import it.

  python sd_tools.py labels_local  input.tsv  output.pdf  30|thermal      (drawn locally, NOT from Amazon)
"""
import sys, struct, zipfile, zlib

# ---------------------------------------------------------------- Code 128 (set B, same as the Amazon labels)
PAT = ("212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 "
       "123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 "
       "232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 "
       "313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 "
       "111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
       "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 "
       "114311 411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112").split()

def code128_modules(text):
    """list of module widths (bar, space, bar, ...). Same encoding as the Amazon labels: code set B, and code set C
    for runs of 4 or more digits (e.g. X0052KQHCJ), which gives the same bars as Amazon prints."""
    vals = []
    n = len(text); i = 0; cur = None
    def digrun(k):
        j = k
        while j < n and text[j].isdigit(): j += 1
        return j - k
    while i < n:
        r = digrun(i)
        if r >= 4 or (cur == 'C' and r >= 2):
            if cur != 'C':
                vals.append(105 if cur is None else 99); cur = 'C'
            take = r - (r % 2)
            for k in range(0, take, 2): vals.append(int(text[i + k:i + k + 2]))
            i += take
        else:
            if cur != 'B':
                vals.append(104 if cur is None else 100); cur = 'B'
            vals.append(ord(text[i]) - 32); i += 1
    return _finish(vals)

def _finish(vals):
    chk = vals[0]
    for i, v in enumerate(vals[1:], 1):
        chk += i * v
    vals = vals + [chk % 103, 106]
    out = []
    for v in vals:
        out += [int(ch) for ch in PAT[v]]
    return out

# ---------------------------------------------------------------- Helvetica metrics
HW = {' ':278,'!':278,'"':355,'#':556,'$':556,'%':889,'&':667,"'":191,'(':333,')':333,'*':389,'+':584,',':278,'-':333,'.':278,'/':278,
      ':':278,';':278,'<':584,'=':584,'>':584,'?':556,'@':1015,'[':278,'\\':278,']':278,'^':469,'_':556,'`':333,'{':334,'|':260,'}':334,'~':584}
for _c in '0123456789': HW[_c] = 556
for _c, _w in zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', [667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611]): HW[_c] = _w
for _c, _w in zip('abcdefghijklmnopqrstuvwxyz', [556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500]): HW[_c] = _w
HW['–'] = 556; HW['—'] = 1000; HW['™'] = 1000

def sw(s, size):
    return sum(HW.get(c, 556) for c in s) * size / 1000.0

def shorten(s, width, size):
    """Amazon style: keep the start and the end of a long title and put ... in the middle."""
    if sw(s, size) <= width:
        return s
    n = len(s); h = 0; t = 0
    while h + t < n:
        cand = s[:h + 1] + '...' + (s[n - t:] if t else '')
        if sw(cand, size) > width: break
        h += 1
        cand = s[:h] + '...' + s[n - (t + 1):]
        if sw(cand, size) > width: break
        t += 1
    return s[:h] + '...' + (s[n - t:] if t else '')

def wrap(s, width, size):
    words = s.split(' '); lines = []; cur = ''
    for w in words:
        cand = (cur + ' ' + w) if cur else w
        if sw(cand, size) <= width or not cur: cur = cand
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def pdf_text(s):
    b = s.encode('cp1252', 'replace')
    return b.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')

# ---------------------------------------------------------------- PDF writer (plain PDF 1.4, standard font)
class Pdf:
    def __init__(self):
        self.pages = []
    def add(self, w, h, content):
        self.pages.append((w, h, content))
    def save(self, path):
        objs = []
        n = len(self.pages)
        # 1 catalog, 2 pages, 3 font, then (page, content) pairs
        objs.append(b'<< /Type /Catalog /Pages 2 0 R >>')
        kids = ' '.join('%d 0 R' % (4 + 2 * i) for i in range(n))
        objs.append(('<< /Type /Pages /Kids [%s] /Count %d >>' % (kids, n)).encode())
        objs.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
        for i, (w, h, c) in enumerate(self.pages):
            objs.append(('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>'
                         % (w, h, 5 + 2 * i)).encode())
            z = zlib.compress(c)
            objs.append(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(z) + z + b'\nendstream')
        out = bytearray(b'%PDF-1.4\n')
        offs = []
        for i, o in enumerate(objs, 1):
            offs.append(len(out))
            out += ('%d 0 obj\n' % i).encode() + o + b'\nendobj\n'
        x = len(out)
        out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)).encode()
        for o in offs: out += ('%010d 00000 n \n' % o).encode()
        out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, x)).encode()
        with open(path, 'wb') as f: f.write(out)

class Page:
    """drawing helper, y measured from the TOP of the page like the Amazon PDFs"""
    def __init__(self, w, h):
        self.w = w; self.h = h; self.ops = []
    def barcode(self, text, x, top, height, module, gain=0.0):
        """gain: the 30-up sheet prints every bar 0.12 pt thinner than its module (same as Amazon's PDF)"""
        mods = code128_modules(text); xx = x; bar = True
        for m in mods:
            if bar:
                self.ops.append('%.3f %.3f %.3f %.3f re f' % (xx, self.h - top - height, m * module - gain, height))
            xx += m * module; bar = not bar
        return xx - x
    def text(self, s, x, baseline_top, size):
        self.ops.append('BT /F1 %.2f Tf %.3f %.3f Td (%s) Tj ET' % (size, x, self.h - baseline_top, pdf_text(s).decode('latin-1')))
    def content(self):
        return ('0 g\n' + '\n'.join(self.ops)).encode('latin-1')

def make_labels(items, out_path, kind):
    """items: list of (fnsku, title, qty)"""
    flat = []
    for f, t, q in items:
        flat += [(f, t)] * int(q)
    pdf = Pdf()
    if kind == '30':
        W, H = 612.0, 792.0
        per = 30
        for p0 in range(0, max(len(flat), 1), per):
            pg = Page(W, H)
            for k, (f, t) in enumerate(flat[p0:p0 + per]):
                col = k % 3; row = k // 3
                x = 22.0 + 200.0 * col; top = 51.34 + 72.0 * row
                bw = pg.barcode(f, x, top, 15.0, 0.96, 0.12)
                fs = 8.0
                pg.text(f, x + bw / 2 - sw(f, fs) / 2, top + 23.8, fs)
                pg.text(shorten(t, 150.0, 9.0), x, top + 36.6, 9.0)
                pg.text('New', x, top + 46.6, 9.0)
            pdf.add(W, H, pg.content())
    else:
        W, H = 142.26, 71.13
        for f, t in flat:
            pg = Page(W, H)
            bw = pg.barcode(f, 18.0, 7.11, 23.47, 106.26 / sum(code128_modules(f)))   # Amazon stretches every thermal barcode to the same width
            fs = 8.0
            pg.text(f, 18.0 + bw / 2 - sw(f, fs) / 2, 40.6, fs)
            lines = wrap(shorten('New - ' + t, 158.0, fs), 106.26, fs)[:2]
            for i, ln in enumerate(lines):
                pg.text(ln, 18.0, 52.6 + 8.0 * i, fs)
            pdf.add(W, H, pg.content())
    if not pdf.pages:
        pg = Page(612.0, 792.0); pdf.add(612.0, 792.0, pg.content())
    pdf.save(out_path)
    return len(flat)

# ---------------------------------------------------------------- labels straight from Amazon
import re, json, os, time, urllib.parse, urllib.request, urllib.error
SP_API = "https://sellingpartnerapi-na.amazon.com"
LWA_URL = "https://api.amazon.com/auth/o2/token"
MARKETPLACE = "ATVPDKIKX0DER"
UA = "ReplenishmentPlanner/1.0 (Language=Python)"

def _credentials():
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (here, "C:\\AmazonFeed", os.path.join(os.path.expanduser("~"), "Desktop", "Amazon", "AmazonFeed")):
        path = os.path.join(folder, "credentials.txt")
        if os.path.exists(path):
            c = {}
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        c[k.strip().upper()] = v.strip().strip('"').strip("'")
            if all(c.get(k) for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")):
                return c
    raise RuntimeError("credentials.txt (CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN) was not found next to sd_tools.py or in C:\\AmazonFeed")

def _token(c):
    data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": c["REFRESH_TOKEN"],
                                   "client_id": c["CLIENT_ID"], "client_secret": c["CLIENT_SECRET"]}).encode()
    req = urllib.request.Request(LWA_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        raise RuntimeError("Amazon refused the login (HTTP %s): %s" % (e.code, e.read().decode(errors="replace")[:300]))

def _post_labels(c, tok, items, kind):
    body = {"marketplaceId": MARKETPLACE, "mskuQuantities": [{"msku": m, "quantity": q} for m, q in items]}
    if kind == "30":
        body.update({"labelType": "STANDARD_FORMAT", "pageType": "Letter_30"})
    else:
        body.update({"labelType": "THERMAL_PRINTING", "width": 50, "height": 25})
    data = json.dumps(body).encode()
    for attempt in range(6):
        req = urllib.request.Request(SP_API + "/inbound/fba/2024-03-20/items/labels", data=data, method="POST",
                                     headers={"x-amz-access-token": tok, "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(min(60, 4 * 2 ** attempt)); continue
            raise RuntimeError("Amazon answered HTTP %s: %s" % (e.code, msg[:700]))
        except urllib.error.URLError as e:
            if attempt < 5:
                time.sleep(5); continue
            raise RuntimeError("no connection to Amazon: %s" % e)

def amazon_labels(items, out_path, kind):
    """items: list of (msku, quantity). Writes out_path (or out_path with _part2, _part3 ... when there are more than 100 products)."""
    c = _credentials(); tok = _token(c)
    chunks = [items[i:i + 100] for i in range(0, len(items), 100)]
    written = []
    for n, chunk in enumerate(chunks, 1):
        r = _post_labels(c, tok, chunk, kind)
        docs = r.get("documentDownloads") or []
        if not docs or not docs[0].get("uri"):
            raise RuntimeError("Amazon did not return a label file: " + json.dumps(r)[:300])
        data = urllib.request.urlopen(docs[0]["uri"], timeout=120).read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError("Amazon returned something that is not a PDF")
        path = out_path if len(chunks) == 1 else out_path[:-4] + "_part%d.pdf" % n
        with open(path, "wb") as f: f.write(data)
        written.append(path)
    return written

# ---------------------------------------------------------------- Send to Amazon: plan + boxes (Fulfillment Inbound 2024-03-20)
INB = "/inbound/fba/2024-03-20"

class ApiError(RuntimeError):
    pass

def _api(c, method, path, body=None, params=None):
    url = SP_API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(7):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"x-amz-access-token": _token(c), "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 6:
                time.sleep(min(60, 3 * 2 ** attempt)); continue
            ex = ApiError("Amazon answered HTTP %s on %s %s: %s" % (e.code, method, path.replace(INB, ""), msg[:3000]))
            ex.body = msg
            raise ex
        except urllib.error.URLError as e:
            if method == "GET" and attempt < 6:
                time.sleep(5); continue
            raise RuntimeError("no connection to Amazon: %s" % e)

def _wait(c, op, what, say):
    """poll an asynchronous Amazon operation until it finishes"""
    oid = op.get("operationId")
    if not oid:
        raise RuntimeError("Amazon gave no operationId for " + what + ": " + json.dumps(op)[:300])
    for i in range(120):
        r = _api(c, "GET", INB + "/operations/" + oid)
        st = r.get("operationStatus")
        if st == "SUCCESS":
            return r
        if st == "FAILED":
            probs = "; ".join("%s: %s %s" % (p.get("code"), p.get("message"), p.get("details") or "") for p in (r.get("operationProblems") or []))
            raise RuntimeError(what + " failed at Amazon: " + (probs or json.dumps(r)[:500]))
        time.sleep(2 if i < 10 else 5)
    raise RuntimeError(what + " is taking too long at Amazon (operation " + oid + ")")

def _paged(c, path, key, params=None):
    out = []; tok = None; size = 100
    for _ in range(200):
        q = dict(params or {}); q["pageSize"] = size
        if tok: q["paginationToken"] = tok
        try:
            r = _api(c, "GET", path, params=q)
        except ApiError as e:
            m_ = re.search(r"less than or equal to (\d+)", getattr(e, "body", ""))
            if m_ and int(m_.group(1)) < size:
                size = int(m_.group(1)); continue
            raise
        out += r.get(key) or []
        tok = (r.get("pagination") or {}).get("nextToken")
        if not tok: break
    return out

def read_send_file(path):
    """TSV from the workbook:  NAME<TAB>text | CITY<TAB>text | BOX<TAB>n<TAB>lb<TAB>w<TAB>l<TAB>h | ITEM<TAB>sku<TAB>box<TAB>qty"""
    name = city = ""; boxes = {}; cells = []; exp = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            p = line.rstrip("\r\n").split("\t")
            if not p or not p[0]: continue
            k = p[0].upper()
            if k == "NAME" and len(p) > 1: name = p[1].strip()
            elif k == "CITY" and len(p) > 1: city = p[1].strip()
            elif k == "BOX" and len(p) >= 6:
                boxes[int(float(p[1]))] = tuple(float(x) for x in p[2:6])   # lb, w, l, h
            elif k == "EXP" and len(p) >= 2 and p[1].strip(): exp["*"] = p[1].strip()
            elif k == "EXPSKU" and len(p) >= 3 and p[2].strip(): exp[p[1].strip()] = p[2].strip()
            elif k == "ITEM" and len(p) >= 4:
                q = int(float(p[3]))
                if q > 0: cells.append((p[1].strip(), int(float(p[2])), q))
    return name, city, boxes, cells, exp

def ship_from(city):
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (here, "C:\\AmazonFeed"):
        fp = os.path.join(folder, "ship_from.json")
        if os.path.exists(fp):
            with open(fp, encoding="utf-8-sig") as f:
                d = json.load(f)
            for k, v in d.items():
                if k.strip().lower() == city.strip().lower():
                    bad = [x for x in ("name", "addressLine1", "city", "stateOrProvinceCode", "postalCode", "countryCode", "phoneNumber") if not str(v.get(x, "")).strip() or str(v.get(x)).startswith("FILL")]
                    if bad:
                        raise RuntimeError("ship_from.json: the address for %s is incomplete (%s). Open ship_from.json next to sd_tools.py and fill it in once." % (city, ", ".join(bad)))
                    return v
            raise RuntimeError("ship_from.json has no address for '%s'." % city)
    raise RuntimeError("ship_from.json was not found next to sd_tools.py (run INSTALL_SANDIEGO.bat again).")

def send_to_amazon(path, say=print, cancel_after=False, owners=("NONE", "SELLER"), placement=True):
    name, city, boxes, cells, exp = read_send_file(path)
    if not boxes or not cells:
        raise RuntimeError("no boxes with products were found on the Summary sheet (fill the Box columns and the weight/size rows first).")
    for n, b in sorted(boxes.items()):
        if min(b) <= 0:
            raise RuntimeError("Box%d is missing its weight or size (W Lbs / W Inch / L Inch / H Inch rows)." % n)
    used = sorted(set(b for _, b, _ in cells))
    missing = [n for n in used if n not in boxes]
    if missing:
        raise RuntimeError("Box%s has products but no weight/size on the Summary sheet." % ", Box".join(str(n) for n in missing))
    totals = {}
    for sku, b, q in cells: totals[sku] = totals.get(sku, 0) + q
    if any(q > 10000 for q in totals.values()): raise RuntimeError("a quantity is over 10000")
    src = dict(ship_from(city))
    c = _credentials()
    say("plan '%s' | ship from %s | %d SKUs, %d units, %d boxes" % (name, city, len(totals), sum(totals.values()), len(used)))
    own = {m: {"prepOwner": owners[0], "labelOwner": owners[1]} for m in totals}
    need_exp = set()
    pid = None
    for attempt in range(6):
        items = []
        for m, q in sorted(totals.items()):
            it = dict({"msku": m, "quantity": q}, **own[m])
            if m in need_exp or m in exp:
                d = exp.get(m) or exp.get("*")
                if d: it["expiration"] = d
            items.append(it)
        body = {"destinationMarketplaces": [MARKETPLACE], "items": items, "sourceAddress": src}
        if name: body["name"] = name
        try:
            op = _api(c, "POST", INB + "/inboundPlans", body)
            pid = op.get("inboundPlanId")
            _wait(c, op, "creating the plan", say)
            break
        except ApiError as e:
            # Amazon tells, per product, which prep/label owner it accepts: take its answer and try again
            fixed = 0
            for m_ in re.finditer(r'(\S+) (?:does not require|requires|does not need|needs) (prepOwner|labelOwner)[^"]*?Accepted values: \[([^\]]*)\]', getattr(e, "body", "")):
                sku_, fld, acc = m_.group(1), m_.group(2), [x.strip() for x in m_.group(3).split(",") if x.strip()]
                if sku_ in own and acc:
                    new = "SELLER" if "SELLER" in acc else acc[0]
                    if own[sku_][fld] != new: own[sku_][fld] = new; fixed += 1
            if not fixed: raise
        except RuntimeError as e:
            # the plan was made but Amazon rejected products: expiration dates are asked per product
            txt = str(e)
            if pid:
                try: _api(c, "PUT", INB + "/inboundPlans/%s/cancellation" % pid)
                except Exception: pass
                pid = None
            ex_skus = set(re.findall(r"FBA_INB_0180[^;]*?resource '([^']+)'", txt))
            haz = sorted(set(re.findall(r"FBA_INB_0009[^;]*?resource '([^']+)'", txt)))
            if haz:
                raise RuntimeError("Amazon needs dangerous-goods (hazmat) information for: %s. Complete it in Seller Central (Manage Inventory > the product > Edit) or take it off the order, then run again." % ", ".join(haz))
            if ex_skus and not (exp.get("*") or all(x in exp for x in ex_skus)):
                raise RuntimeError("Amazon requires an expiration date for %d products (%s). Fill the Expiration date cell on the Menu sheet and run again." % (len(ex_skus), ", ".join(sorted(ex_skus)[:8]) + ("..." if len(ex_skus) > 8 else "")))
            if not ex_skus or (ex_skus <= need_exp and attempt > 0):
                raise
            need_exp |= ex_skus
            say("expiration date added to %d products that need it" % len(ex_skus))
    else:
        raise RuntimeError("Amazon kept refusing the plan")
    say("1/5 plan created: " + str(pid))
    try:
        say("1/5 inventory accepted by Amazon")
        _wait(c, _api(c, "POST", INB + "/inboundPlans/%s/packingOptions" % pid), "packing options", say)
        opts = _paged(c, INB + "/inboundPlans/%s/packingOptions" % pid, "packingOptions")
        if not opts: raise RuntimeError("Amazon returned no packing option")
        for o in opts:
            say("   option %s: %d group(s), status %s, discounts %s, fees %s" % (o.get("packingOptionId"), len(o.get("packingGroups") or []), o.get("status"), json.dumps(o.get("discounts")), json.dumps(o.get("fees"))))
        # mixed boxes need ONE packing group: take the option with the fewest groups
        opt = sorted(opts, key=lambda o: len(o.get("packingGroups") or []))[0]
        groups = opt.get("packingGroups") or []
        say("2/5 packing option %s with %d group(s)" % (opt.get("packingOptionId"), len(groups)))
        gitems = {}
        for g in groups:
            git = _paged(c, INB + "/inboundPlans/%s/packingGroups/%s/items" % (pid, g), "items")
            say("   group %s: %d products %s" % (g[:12], len(git), json.dumps(git[:2])[:400]))
            for it in git:
                gitems[it.get("msku")] = g
        _wait(c, _api(c, "POST", INB + "/inboundPlans/%s/packingOptions/%s/confirmation" % (pid, opt["packingOptionId"])), "confirming the packing option", say)
        say("3/5 packing option confirmed")
        per_group = {}
        for n in used:
            lb, w, l, h = boxes[n]
            its = {}
            for sku, b, q in cells:
                if b == n: its[sku] = its.get(sku, 0) + q
            gs = set(gitems.get(m) for m in its)
            if len(gs) != 1 or None in gs:
                raise RuntimeError("Box%d mixes products that Amazon put in different packing groups (%s)." % (n, ", ".join(sorted(its))))
            g = gs.pop()
            per_group.setdefault(g, []).append({
                "contentInformationSource": "BOX_CONTENT_PROVIDED", "quantity": 1,
                "dimensions": {"length": l, "width": w, "height": h, "unitOfMeasurement": "IN"},
                "weight": {"unit": "LB", "value": lb},
                "items": [dict({"msku": m, "quantity": q}, **own[m]) for m, q in sorted(its.items())]})
        pg = [{"packingGroupId": g, "boxes": bx} for g, bx in per_group.items()]
        _wait(c, _api(c, "POST", INB + "/inboundPlans/%s/packingInformation" % pid, {"packageGroupings": pg}), "box contents", say)
        say("4/5 box contents and sizes saved (%d boxes)" % len(used))
        if placement:
            _wait(c, _api(c, "POST", INB + "/inboundPlans/%s/placementOptions" % pid), "shipment options", say)
            say("5/5 shipment options generated - plan is ready for you at the next step")
    except Exception:
        if pid and cancel_after:
            try: _api(c, "PUT", INB + "/inboundPlans/%s/cancellation" % pid)
            except Exception: pass
        raise
    result = {"inboundPlanId": pid}
    if cancel_after:
        # test mode: verify what Amazon stored, then cancel the test plan
        chk = _paged(c, INB + "/inboundPlans/%s/boxes" % pid, "boxes")
        say("verify: Amazon lists %d boxes" % len(chk))
        result["boxes"] = len(chk)
        _api(c, "PUT", INB + "/inboundPlans/%s/cancellation" % pid)
        say("test plan cancelled")
    return result

# ---------------------------------------------------------------- Apple Numbers reader (first table only)
def _snappy(b):
    i = 0; n = 0; shift = 0
    while True:
        c = b[i]; i += 1; n |= (c & 0x7f) << shift; shift += 7
        if not c & 0x80: break
    out = bytearray()
    while i < len(b):
        t = b[i]; i += 1; k = t & 3
        if k == 0:
            l = t >> 2
            if l < 60: l += 1
            else:
                nb = l - 59; l = int.from_bytes(b[i:i + nb], 'little') + 1; i += nb
            out += b[i:i + l]; i += l
        else:
            if k == 1: l = ((t >> 2) & 7) + 4; off = ((t >> 5) << 8) | b[i]; i += 1
            elif k == 2: l = (t >> 2) + 1; off = int.from_bytes(b[i:i + 2], 'little'); i += 2
            else: l = (t >> 2) + 1; off = int.from_bytes(b[i:i + 4], 'little'); i += 4
            for _ in range(l): out.append(out[-off])
    return bytes(out)

def _iwa(d):
    i = 0; out = b''
    while i < len(d):
        L = int.from_bytes(d[i + 1:i + 4], 'little'); out += _snappy(d[i + 4:i + 4 + L]); i += 4 + L
    return out

def _varint(b, i):
    r = 0; s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return r, i

def _pb(b):
    i = 0; f = []
    while i < len(b):
        k, i = _varint(b, i); fn = k >> 3; wt = k & 7
        if wt == 0: v, i = _varint(b, i)
        elif wt == 2:
            l, i = _varint(b, i); v = b[i:i + l]; i += l
        elif wt == 1: v = b[i:i + 8]; i += 8
        elif wt == 5: v = b[i:i + 4]; i += 4
        else: raise ValueError('bad wire type')
        f.append((fn, wt, v))
    return f

def _objects(raw):
    i = 0; res = []
    while i < len(raw):
        l, i = _varint(raw, i); ai = _pb(raw[i:i + l]); i += l
        infos = [_pb(v) for fn, wt, v in ai if fn == 2]
        for mi in infos:
            typ = [v for fn, wt, v in mi if fn == 1][0]
            ln = [v for fn, wt, v in mi if fn == 3][0]
            res.append((typ, raw[i:i + ln])); i += ln
    return res

def _dec128(b):
    lo = int.from_bytes(b[:8], 'little'); hi = int.from_bytes(b[8:], 'little')
    exp = ((hi >> 49) & 0x3fff) - 6176
    mant = ((hi & ((1 << 49) - 1)) << 64) | lo
    v = mant * (10 ** exp) if exp >= 0 else mant / (10 ** -exp)
    return -v if hi >> 63 else v

def read_numbers(path):
    z = zipfile.ZipFile(path)
    strings = {}
    for n in z.namelist():
        base = n.split('/')[-1]
        if n.startswith('Index/Tables/DataList') and n.endswith('.iwa'):
            for typ, p in _objects(_iwa(z.read(n))):
                f = _pb(p)
                kind = [v for fn, wt, v in f if fn == 1]
                if kind and kind[0] == 1:
                    for fn, wt, v in f:
                        if fn == 3:
                            d = {a: c for a, b2, c in _pb(v)}
                            if 3 in d and 1 in d: strings.setdefault(d[1], d[3].decode('utf8', 'replace'))
    cells = {}
    for n in z.namelist():
        if n.startswith('Index/Tables/Tile') and n.endswith('.iwa'):
            for typ, p in _objects(_iwa(z.read(n))):
                if typ != 6002: continue
                for fn, wt, v in _pb(p):
                    if fn != 5: continue
                    d = {a: c for a, b2, c in _pb(v)}
                    buf = d.get(6); offs = d.get(7)
                    if buf is None or offs is None: continue
                    r = d.get(1, 0)
                    offs = struct.unpack('<%dH' % (len(offs) // 2), offs)
                    valid = [y for y in offs if y != 0xffff]
                    for k, x in enumerate(offs):
                        if x == 0xffff: continue
                        nxt = min([y for y in valid if y > x] + [len(buf)])
                        c = buf[x:nxt]; t = c[1]
                        val = None
                        if t == 3 and len(c) >= 16:
                            val = strings.get(struct.unpack('<I', c[12:16])[0])
                        elif t in (2, 10) and len(c) >= 28:
                            val = _dec128(c[12:28])
                            if val == int(val): val = int(val)
                        if val is not None: cells[(r, k)] = val
    return cells

def numbers_to_tsv(src, dst):
    cells = read_numbers(src)
    with open(dst, 'w', encoding='utf-8', newline='') as f:
        for (r, c), v in sorted(cells.items()):
            if isinstance(v, str):
                f.write('%d\t%d\ts\t%s\n' % (r + 1, c + 1, v.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')))
            else:
                f.write('%d\t%d\tn\t%s\n' % (r + 1, c + 1, repr(v)))
    return len(cells)

if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) == 4 and a[0] in ('labels', 'labels_local'):
        kind = '30' if a[3] == '30' else 'thermal'
        rows = []; nlines = 0; ncols = set()
        with open(a[1], encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip(): continue
                p = line.rstrip('\r\n').split('\t')
                nlines += 1; ncols.add(len(p))
                if len(p) >= 4 and p[0].strip():
                    try: q = int(float(p[3]))
                    except ValueError: continue
                    if q > 0: rows.append((p[0].strip(), p[1].strip(), p[2].strip(), q))
        if not rows:
            if nlines and max(ncols) < 4:
                print('ERROR: the list from the workbook has %s columns instead of 4 (SKU, FNSKU, title, quantity). '
                      'The workbook still has the OLD macros: close Excel and run INSTALL_SANDIEGO.bat again, then open the workbook.' % sorted(ncols))
            else:
                print('ERROR: no products with a SKU and a quantity were found in the list (%d lines read).' % nlines)
            sys.exit(1)
        if a[0] == 'labels':
            try:
                files = amazon_labels([(r[0], r[3]) for r in rows], a[2], kind)
            except Exception as e:
                print('ERROR: ' + str(e)); sys.exit(1)
            print('labels from Amazon: %d units, %d products, files: %s' % (sum(r[3] for r in rows), len(rows), ', '.join(files)))
        else:
            n = make_labels([(r[1], r[2], r[3]) for r in rows], a[2], kind)
            print('labels (drawn locally):', n)
    elif len(a) >= 2 and a[0] == 'inbound':
        try:
            r = send_to_amazon(a[1], say=print, cancel_after=(len(a) > 2 and a[2] == 'test'))
        except Exception as e:
            print('ERROR: ' + str(e)); sys.exit(1)
        print('DONE plan ' + str(r.get('inboundPlanId')))
    elif len(a) == 3 and a[0] == 'numbers':
        print('cells:', numbers_to_tsv(a[1], a[2]))
    else:
        print(__doc__); sys.exit(2)
