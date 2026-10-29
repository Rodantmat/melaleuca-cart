#!/usr/bin/env python3
"""
Amazon SP-API feed puller  --  Phase 1  (Flipping Magic LLC, US marketplace)

What it does
  test    : checks your credentials and prints which store/marketplace they belong to.
  pull    : requests the Amazon reports, waits, downloads them into "raw" (latest + dated archive).
  build   : turns the raw reports into the ready-to-load files in "feed" (for the Excel macro).
  refresh : pull + build in one go (this is what Excel and the scheduled task run).

Needs only Python 3.8+ (standard library, nothing to pip install).
Reads credentials from credentials.txt in the SAME folder as this script:
    CLIENT_ID=...
    CLIENT_SECRET=...
    REFRESH_TOKEN=...
Nothing secret is ever printed or written to the output files.
"""
import argparse, datetime as dt, gzip, json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request
try:
    import amazon_pricing as AP          # live Buy Box prices (optional: without this file the old behaviour is kept)
except Exception:
    AP = None

BASE = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE, "credentials.txt")
RAW_DIR = os.path.join(BASE, "raw")
FEED_DIR = os.path.join(BASE, "feed")
FEE_CACHE = os.path.join(FEED_DIR, "fees_cache.json")
FEE_GOOD = os.path.join(FEED_DIR, "fees_good.json")        # last complete fee seen per SKU (never overwritten by a bad one)
PRICING_FILE = os.path.join(RAW_DIR, "pricing_latest.json")      # live Buy Box prices per ASIN (amazon_pricing.py)
FEE_OVERRIDE = os.path.join(BASE, "fee_overrides.tsv")  # optional, you type: sku<TAB>total fee<TAB>FBA fee
ARCH_DIR = os.path.join(RAW_DIR, "archive")
API = "https://sellingpartnerapi-na.amazon.com"
LWA_URL = "https://api.amazon.com/auth/o2/token"
MARKETPLACE = "ATVPDKIKX0DER"          # United States
UA = "ReplenishmentPlanner/1.0 (Language=Python)"

# key -> (Amazon report type, output file stem)
REPORTS = {
    "planning": ("GET_FBA_INVENTORY_PLANNING_DATA", "fba_inventory_planning"),
    "myi":      ("GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA", "fba_myi_inventory"),
    "listings": ("GET_MERCHANT_LISTINGS_ALL_DATA", "merchant_listings"),
    "feeprev":  ("GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA", "fba_fee_preview"),
}
MYI_FALLBACK_TYPE = "GET_FBA_MYI_ALL_INVENTORY_DATA"
ORDERS_TYPE = "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"


class SpApiError(Exception):
    pass


# ----------------------------------------------------------------- credentials
def load_credentials(path=CRED_FILE):
    if not os.path.exists(path):
        sys.exit("credentials.txt not found next to the script: " + path)
    creds = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip().upper()] = v.strip().strip('"').strip("'")
    missing = [k for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN") if not creds.get(k)]
    if missing:
        sys.exit("credentials.txt is missing: " + ", ".join(missing))
    if not creds["REFRESH_TOKEN"].startswith("Atzr|"):
        print("WARNING: REFRESH_TOKEN does not start with 'Atzr|' - check you copied the refresh token.")
    return creds


_token = {"value": None, "expires": 0}


def get_access_token(creds, force=False):
    if not force and _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": creds["REFRESH_TOKEN"],
        "client_id": creds["CLIENT_ID"],
        "client_secret": creds["CLIENT_SECRET"],
    }).encode()
    req = urllib.request.Request(LWA_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            j = json.loads(body)
            body = j.get("error", "") + ": " + j.get("error_description", "")
        except Exception:
            pass
        raise SpApiError("Login with Amazon refused the credentials (HTTP %s): %s" % (e.code, body))
    _token["value"] = j["access_token"]
    _token["expires"] = time.time() + int(j.get("expires_in", 3600))
    return _token["value"]


# --------------------------------------------------------------------- API call
def api(creds, method, path, params=None, body=None, tries=8):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    refreshed = False
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "x-amz-access-token": get_access_token(creds),
            "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504):
                wait = min(120, 5 * (2 ** attempt))
                print("  (Amazon busy / rate limit, HTTP %s - waiting %ss)" % (e.code, wait))
                time.sleep(wait)
                continue
            if e.code in (401, 403) and not refreshed and "expired" in msg.lower():
                get_access_token(creds, force=True); refreshed = True
                continue
            raise SpApiError("HTTP %s on %s %s: %s" % (e.code, method, path, msg[:600]))
        except urllib.error.URLError as e:
            time.sleep(5)
            if attempt == tries - 1:
                raise SpApiError("Network error: %s" % e)
    raise SpApiError("Gave up after repeated retries on " + path)


# ---------------------------------------------------------------------- reports
def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_report(creds, rtype, start=None, end=None):
    body = {"reportType": rtype, "marketplaceIds": [MARKETPLACE]}
    if start and end:
        body["dataStartTime"], body["dataEndTime"] = iso(start), iso(end)
    return api(creds, "POST", "/reports/2021-06-30/reports", body=body)["reportId"]


def wait_for(creds, jobs, max_minutes=60):
    """jobs: {label: reportId}. Returns {label: (status, documentId)}."""
    done, deadline = {}, time.time() + max_minutes * 60
    while len(done) < len(jobs) and time.time() < deadline:
        for label, rid in jobs.items():
            if label in done:
                continue
            r = api(creds, "GET", "/reports/2021-06-30/reports/" + rid)
            st = r.get("processingStatus")
            if st in ("DONE", "CANCELLED", "FATAL"):
                done[label] = (st, r.get("reportDocumentId"))
                print("  %-28s %s" % (label, st))
                if st != "DONE":
                    why = ""
                    try:
                        if r.get("reportDocumentId"):
                            why = decode(download(creds, r["reportDocumentId"]))[:400].replace("\n", " | ")
                    except Exception as e:
                        why = "(no detail: %s)" % str(e)[:100]
                    print("    Amazon says: %s  [reportId %s, type %s]" % (why or "(no detail given)", rid, r.get("reportType")))
        if len(done) < len(jobs):
            time.sleep(20)
    for label in jobs:
        done.setdefault(label, ("TIMEOUT", None))
    return done


def download(creds, doc_id):
    d = api(creds, "GET", "/reports/2021-06-30/documents/" + doc_id)
    req = urllib.request.Request(d["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        blob = r.read()
    if str(d.get("compressionAlgorithm", "")).upper() == "GZIP":
        blob = gzip.decompress(blob)
    return blob


def decode(blob):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def save(stem, blob, stamp):
    os.makedirs(ARCH_DIR, exist_ok=True)
    latest = os.path.join(RAW_DIR, stem + "_latest.tsv")
    with open(latest, "wb") as f:
        f.write(blob)
    with open(os.path.join(ARCH_DIR, "%s_%s.tsv" % (stem, stamp)), "wb") as f:
        f.write(blob)
    return latest


PII_COLS = {"ship-city", "ship-state", "ship-postal-code", "ship-country", "cpf",
            "purchase-order-number", "merchant-order-id"}


def strip_pii(text):
    """Drop buyer-location / PII-ish columns from an order TSV (we never need them)."""
    lines = text.splitlines()
    if not lines:
        return text
    hdr = lines[0].split("\t")
    keep = [i for i, h in enumerate(hdr) if h.strip().lower() not in PII_COLS]
    out = []
    for ln in lines:
        p = ln.split("\t")
        out.append("\t".join(p[i] if i < len(p) else "" for i in keep))
    return "\n".join(out) + "\n"


def merge_chunks(blobs):
    """Join date-chunked TSVs: one header, all rows."""
    out, header = [], None
    for b in blobs:
        lines = decode(b).splitlines()
        if not lines:
            continue
        if header is None:
            header = lines[0]
            out.append(header)
        out.extend(l for l in lines[1:] if l.strip())
    return strip_pii("\n".join(out) + "\n").encode("utf-8")


# --------------------------------------------------------------------- build (phase 2)
def read_tsv(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        text = decode(f.read())
    lines = text.splitlines()
    if not lines:
        return []
    hdr = [h.strip() for h in lines[0].split("\t")]
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        p = ln.split("\t")
        p += [""] * (len(hdr) - len(p))
        rows.append(dict(zip(hdr, [x.strip() for x in p])))
    return rows


def num(s, default=None):
    if s is None:
        return default
    s = str(s).replace("$", "").replace(",", "").strip()
    if s in ("", "--", "None", "N/A", "n/a", "nan"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def first(*vals):
    for v in vals:
        if v not in (None, ""):
            return v
    return None


_KEYWORDS = re.compile(r"\b(asin|fnsku|sku|inbound|unfulfillable|featured offer|sales rank|total fees)\b", re.I)


def clean_name(s):
    """Product names must never contain the words your Inventory formulas search for."""
    s = (s or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    return _KEYWORDS.sub(lambda m: m.group(0)[0] + "." + m.group(0)[1:], s)


def snake(h):
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


def fetch_fees(creds, wanted, cache, warnings):
    """wanted: {sku: (price, is_fba)}. Updates cache {sku: {total, fba, price, ts}}."""
    now = time.time()
    todo = []
    for sku, (price, fba) in wanted.items():
        c = cache.get(sku)
        stale = (not c) or abs(c.get("price", 0) - price) > 0.01 * max(price, 1) \
            or now - c.get("ts", 0) > 7 * 86400 or c.get("fba") != fba
        if stale:
            todo.append((sku, price, fba))
    if not todo:
        return
    print("Asking Amazon for fee estimates on %d products ..." % len(todo))
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        body = [{"FeesEstimateRequest": {
                    "MarketplaceId": MARKETPLACE, "IsAmazonFulfilled": bool(fba),
                    "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": round(price, 2)}},
                    "Identifier": sku},
                 "IdType": "SellerSKU", "IdValue": sku} for sku, price, fba in batch]
        try:
            r = api(creds, "POST", "/products/fees/v0/feesEstimate", body=body)
        except SpApiError as e:
            warnings.append("fee estimate batch failed: " + str(e)[:200])
            time.sleep(3)
            continue
        res = r if isinstance(r, list) else r.get("payload", r.get("FeesEstimateResultList", []))
        meta = {s: (p, f) for s, p, f in batch}
        for item in res or []:
            ident = item.get("FeesEstimateIdentifier") or {}
            sku = ident.get("IdValue") or (item.get("FeesEstimateRequest") or {}).get("Identifier")
            est = item.get("FeesEstimate") or {}
            tot = num((est.get("TotalFeesEstimate") or {}).get("Amount"))
            if sku not in meta or tot is None:
                if sku:
                    warnings.append("no fee for %s: %s" % (sku, str((item.get("Error") or item.get("Status")))[:80]))
                continue
            fbafee = sum(num((d.get("FinalFee") or {}).get("Amount"), 0) for d in est.get("FeeDetailList", [])
                         if d.get("FeeType") == "FBAFees")
            if meta[sku][1] and fbafee <= 0:
                # Amazon returned only the referral fee for an FBA product: incomplete, do not trust it
                cache.pop(sku, None)
                warnings.append("incomplete fee (no FBA fee) for %s - not used" % sku)
                continue
            cache[sku] = {"total": tot, "fba": meta[sku][1], "fba_fee": fbafee,
                          "price": meta[sku][0], "ts": now}
        time.sleep(2.5)


def orders_by_asin():
    rows = read_tsv(os.path.join(RAW_DIR, "orders_90d_latest.tsv"))
    if rows is None:
        for fn in os.listdir(RAW_DIR) if os.path.isdir(RAW_DIR) else []:
            if fn.startswith("orders_") and fn.endswith("_latest.tsv"):
                rows = read_tsv(os.path.join(RAW_DIR, fn)); break
    out = {}
    if not rows:
        return out
    today = dt.date.today()
    for r in rows:
        if "cancel" in (r.get("order-status", "") + r.get("item-status", "")).lower():
            continue
        asin, q = r.get("asin", ""), num(r.get("quantity"), 0)
        try:
            d = dt.date.fromisoformat(r.get("purchase-date", "")[:10])
        except ValueError:
            continue
        age = (today - d).days
        a = out.setdefault(asin, {"u7": 0, "u30": 0, "u60": 0, "u90": 0, "rev90": 0.0, "q30": 0, "rev30": 0.0,
                                  "o30": set(), "last": ""})
        for lim, k in ((7, "u7"), (30, "u30"), (60, "u60"), (90, "u90")):
            if age < lim:
                a[k] += q
        if age < 90:
            a["rev90"] += num(r.get("item-price"), 0)
        if age < 30 and (num(r.get("item-price"), 0) or 0) > 0:
            a["q30"] += q
            a["rev30"] += num(r.get("item-price"), 0)
        if age < 30:
            a["o30"].add(r.get("amazon-order-id", ""))
        a["last"] = max(a["last"], d.isoformat())
    return out


ALIAS_FILE = os.path.join(BASE, "asin_aliases.tsv")


def load_aliases():
    """asin_aliases.tsv (tab separated): new_asin <TAB> old_asin[,old_asin2] <TAB> note.  Lines starting with # are ignored.
    Use it when a product was recreated under a new ASIN: the sales history of the old ASIN(s) is added to the new one."""
    out = {}
    if not os.path.exists(ALIAS_FILE):
        return out
    for ln in open(ALIAS_FILE, encoding="utf-8-sig", errors="replace").read().splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        c = [x.strip() for x in ln.split("\t")]
        if len(c) >= 2 and re.fullmatch(r"B[0-9A-Z]{9}", c[0]):
            olds = [x.strip() for x in c[1].split(",") if re.fullmatch(r"B[0-9A-Z]{9}", x.strip()) and x.strip() != c[0]]
            if olds:
                out.setdefault(c[0], []).extend(olds)
    return out


def apply_aliases(ords, aliases, warnings):
    """adds the order history of the old ASINs to the new ASIN (units, revenue, orders, last sale date).
    Prices of the old product are NOT mixed into the new ASIN's sold-price figures (q30/rev30 stay untouched)."""
    for new, olds in aliases.items():
        moved = 0
        for old in olds:
            o = ords.get(old)
            if not o:
                continue
            n = ords.setdefault(new, {"u7": 0, "u30": 0, "u60": 0, "u90": 0, "rev90": 0.0, "q30": 0, "rev30": 0.0, "o30": set(), "last": ""})
            for k in ("u7", "u30", "u60", "u90"):
                n[k] += o[k]
            n["rev90"] += o["rev90"]
            n["o30"] |= o["o30"]
            n["last"] = max(n["last"], o["last"])
            moved += o["u90"]
        if moved:
            warnings.append("sales history carried over to %s from %s: %d units in 90 days" % (new, ", ".join(olds), moved))


def suggest_aliases(info, ords, aliases, ghosts, warnings):
    """Never applied automatically: lists active products whose name looks like a product that disappeared but had sales."""
    import difflib
    covered = {o for v in aliases.values() for o in v}
    rows = [["old_asin", "old_sku", "old_name", "units_90d", "possible_new_sku", "possible_new_asin", "possible_new_name", "name_match"]]
    for g in ghosts:
        gi = info[g]
        if gi["asin"] in covered or not ords.get(gi["asin"], {}).get("u90"):
            continue
        gn = clean_name(first(gi["l"].get("item-name"), gi["p"].get("product-name"), gi["m"].get("product-name")) or "").lower()
        best = []
        for sku, i in info.items():
            if sku in ghosts or not i["l"] or not i["asin"] or i["asin"] == gi["asin"]:
                continue
            nn = clean_name(first(i["l"].get("item-name"), i["p"].get("product-name")) or "").lower()
            r = difflib.SequenceMatcher(None, gn, nn).ratio()
            if r >= 0.5:
                best.append((r, sku, i["asin"], nn))
        best.sort(reverse=True)
        for r, sku, asin, nn in best[:2]:
            rows.append([gi["asin"], g, gn[:60], ords[gi["asin"]]["u90"], sku, asin, nn[:60], "%.0f%%" % (100 * r)])
        if not best:
            rows.append([gi["asin"], g, gn[:60], ords[gi["asin"]]["u90"], "", "", "(no similar active product)", ""])
    if len(rows) > 1:
        with open(os.path.join(FEED_DIR, "alias_suggestions.tsv"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join("\t".join(str(x) for x in r) for r in rows) + "\n")
        warnings.append("%d product(s) disappeared but had sales in the last 90 days: see feed\\alias_suggestions.tsv (if one was recreated, add it to asin_aliases.tsv)" % (len(rows) - 1))


PLAN_COLS = ["units-shipped-t7", "units-shipped-t30", "units-shipped-t60", "units-shipped-t90",
             "sales-shipped-last-30-days", "sales-shipped-last-90-days", "days-of-supply",
             "historical-days-of-supply", "Short term historical days of supply",
             "Long term historical days of supply", "weeks-of-cover-t30", "weeks-of-cover-t90",
             "sell-through", "available", "inbound-quantity", "inbound-working", "inbound-shipped",
             "inbound-received", "fc-transfer", "Total Reserved Quantity", "unfulfillable-quantity",
             "inv-age-0-to-90-days", "inv-age-91-to-180-days", "inv-age-181-to-270-days",
             "inv-age-271-to-365-days", "inv-age-366-to-455-days", "inv-age-456-plus-days",
             "estimated-storage-cost-next-month", "estimated-excess-quantity", "no-sale-last-6-months",
             "Recommended ship-in quantity", "Recommended ship-in date",
             "Exempted from Low-Inventory-Level fee?", "Low-Inventory-Level fee applied in current week?",
             "fba-inventory-level-health-status", "is-seasonal-in-next-3-months",
             "your-price", "featuredoffer-price", "sales-rank"]


MYI_HDR = ["sku", "fnsku", "asin", "product-name", "condition", "your-price", "mfn-listing-exists",
           "mfn-fulfillable-quantity", "afn-listing-exists", "afn-warehouse-quantity",
           "afn-fulfillable-quantity", "afn-unsellable-quantity", "afn-reserved-quantity",
           "afn-total-quantity", "per-unit-volume", "afn-inbound-working-quantity",
           "afn-inbound-shipped-quantity", "afn-inbound-receiving-quantity", "afn-researching-quantity",
           "afn-reserved-future-supply", "afn-future-supply-buyable", "afn-fc-transfer-quantity",
           "afn-onhand-buyable-quantity", "store"]


def myi_from_planning(plan_rows, lst_rows=None):
    """Rebuild the 24-column FBA layout from the planning report (used when the FBA report fails)."""
    out = []
    lprice = {r.get("seller-sku", ""): num(r.get("price")) for r in (lst_rows or [])}
    for p in plan_rows:
        av, unf = num(p.get("available"), 0), num(p.get("unfulfillable-quantity"), 0)
        res = num(p.get("Total Reserved Quantity"), 0)
        d = {"sku": p.get("sku"), "fnsku": p.get("fnsku"), "asin": p.get("asin"),
             "product-name": clean_name(p.get("product-name")), "condition": p.get("condition", "New"),
             "your-price": first(num(p.get("your-price")), lprice.get(p.get("sku", ""))), "mfn-listing-exists": "No", "afn-listing-exists": "Yes",
             "afn-warehouse-quantity": av + res + unf, "afn-fulfillable-quantity": av,
             "afn-unsellable-quantity": unf, "afn-reserved-quantity": res,
             "afn-total-quantity": av + res + unf, "per-unit-volume": p.get("item-volume"),
             "afn-inbound-working-quantity": num(p.get("inbound-working"), 0),
             "afn-inbound-shipped-quantity": num(p.get("inbound-shipped"), 0),
             "afn-inbound-receiving-quantity": num(p.get("inbound-received"), 0),
             "afn-fc-transfer-quantity": num(p.get("fc-transfer"), 0), "afn-onhand-buyable-quantity": av}
        out.append("\t".join("" if d.get(h) is None else (("%g" % d[h]) if isinstance(d[h], float) else str(d[h]))
                              for h in MYI_HDR))
    return "\t".join(MYI_HDR) + "\n" + "\n".join(out) + "\n"


def fee_preview_fallback(cache, info, warnings):
    """Fill fees the Product Fees API could not give, from the Fee Preview report (at your current price)."""
    fp = os.path.join(RAW_DIR, "fba_fee_preview_latest.tsv")
    rows = read_tsv(fp)
    if not rows:
        return
    if time.time() - os.path.getmtime(fp) > 3 * 86400:
        warnings.append("fee preview file is older than 3 days - not used"); return
    keys = rows[0].keys()
    kt = next((k for k in keys if k.lower().replace("_", "-") == "estimated-fee-total"), None)
    kf = next((k for k in keys if "fulfil" in k.lower() and "per-unit" in k.lower() and "domestic" in k.lower()
               or k.lower() in ("expected-fulfillment-fee-per-unit",)), None)
    if not kt:
        warnings.append("fee preview report has no estimated-fee-total column"); return
    used = 0
    for r in rows:
        sku = r.get("sku", "")
        tot = num(r.get(kt))
        ff = num(r.get(kf), 0) if kf else 0
        if sku in info and sku not in cache and tot is not None and (ff > 0 or not info[sku]["fba"]):
            cache[sku] = {"total": tot, "fba": info[sku]["fba"], "fba_fee": ff,
                          "price": first(num(r.get("your-price")), 0), "ts": time.time(), "src": "fee_preview"}
            used += 1
    if used:
        warnings.append("%d fee(s) came from the Fee Preview report (at your price, not the Buy Box price)" % used)



def glob_any(folder, pattern):
    import glob
    return glob.glob(os.path.join(folder, pattern))


DEMAND_URL = "https://raw.githubusercontent.com/Rodantmat/melaleuca-cart/feed-latest/demand_hist.json"


def fetch_demand_hist(creds=None):
    """-> (path of a usable demand_hist.json or None, why).  Downloads it when the local copy is older than 6 hours; keeps using an older copy (up to 5 days) when the download fails.
    credentials.txt may hold DEMAND_URL= (another address) and GITHUB_TOKEN= (only if the repository is ever made private)."""
    path = os.path.join(FEED_DIR, "demand_hist.json")
    age = (time.time() - os.path.getmtime(path)) / 3600.0 if os.path.exists(path) else None
    if age is not None and age < 6:
        return path, "copy from %.1f h ago" % age
    url = (creds or {}).get("DEMAND_URL") or DEMAND_URL
    hdr = {"User-Agent": UA}
    tok = (creds or {}).get("GITHUB_TOKEN")
    if tok:
        hdr["Authorization"] = "Bearer " + tok
    try:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        obj = json.loads(data.decode("utf-8"))
        if not isinstance(obj, dict) or "sold" not in obj:
            raise ValueError("not a demand file")
        os.makedirs(FEED_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path, "downloaded, history up to %s" % obj.get("generated", "?")
    except Exception as e:
        if age is not None and age < 24 * 5:
            return path, "download failed (%s), using the copy from %.0f h ago" % (str(e)[:60], age)
        return None, "download failed: %s" % str(e)[:80]

def cmd_build(creds, skip_fees=False):
    os.makedirs(FEED_DIR, exist_ok=True)
    warnings = []
    plan_rows = read_tsv(os.path.join(RAW_DIR, "fba_inventory_planning_latest.tsv"))
    myi_rows = read_tsv(os.path.join(RAW_DIR, "fba_myi_inventory_latest.tsv"))
    lst_rows = read_tsv(os.path.join(RAW_DIR, "merchant_listings_latest.tsv"))
    for nm, v in (("planning", plan_rows), ("fba inventory", myi_rows), ("listings", lst_rows)):
        if v is None:
            warnings.append("missing raw file: " + nm + " (run 'pull' first)")
    # was the FBA inventory report refreshed in the last pull? if not, never trust a stale copy
    try:
        lr = json.load(open(os.path.join(RAW_DIR, "last_run.json")))
        myi_ok = lr.get("status", {}).get("myi", "OK") == "OK"
    except Exception:
        myi_ok = True
    synthesized = False
    if (not myi_ok or myi_rows is None) and plan_rows:
        txt = myi_from_planning(plan_rows, lst_rows)
        with open(os.path.join(RAW_DIR, "fba_myi_inventory_latest.tsv"), "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)
        myi_rows = read_tsv(os.path.join(RAW_DIR, "fba_myi_inventory_latest.tsv"))
        synthesized = True
        warnings.append("FBA inventory report was unavailable: FBA tab rebuilt from the planning report")
    if plan_rows and myi_rows is not None and not synthesized:
        have = {r.get("sku") for r in myi_rows}
        miss = [p for p in plan_rows if p.get("sku") and p.get("sku") not in have]
        if miss:
            extra = myi_from_planning(miss, lst_rows).split("\n", 1)[1]
            fp = os.path.join(RAW_DIR, "fba_myi_inventory_latest.tsv")
            with open(fp, "rb") as f:
                body = f.read()
            if not body.endswith(b"\n"):
                body += b"\n"
            with open(fp, "wb") as f:
                f.write(body + extra.encode("utf-8"))
            myi_rows = read_tsv(fp)
            warnings.append("%d SKU(s) were in the planning report but missing from the FBA inventory report - added from planning: %s" %
                            (len(miss), ", ".join(sorted(p["sku"] for p in miss))[:300]))
    plan = {r["sku"]: r for r in (plan_rows or [])}
    myi = {r["sku"]: r for r in (myi_rows or [])}
    lst = {r["seller-sku"]: r for r in (lst_rows or [])}
    skus = sorted(set(plan) | set(myi) | set(lst))
    if not skus:
        print("Nothing to build - no raw data found."); return 1
    ords = orders_by_asin()
    aliases = load_aliases()
    apply_aliases(ords, aliases, warnings)
    cache = json.load(open(FEE_CACHE)) if os.path.exists(FEE_CACHE) else {}
    for _k in [k for k, v in cache.items() if v.get("src") in ("estimate", "last_good", "override")]:
        cache.pop(_k)           # stand-ins are rebuilt every run so a real Amazon fee always replaces them
    for _k in [k for k, v in cache.items() if v.get("fba") and v.get("fba_fee", 0) <= 0]:
        cache.pop(_k)           # old incomplete entries are re-checked

    info = {}
    for sku in skus:
        p, m, l = plan.get(sku, {}), myi.get(sku, {}), lst.get(sku, {})
        asin = first(p.get("asin"), m.get("asin"), l.get("asin1"), l.get("asin2"), l.get("product-id"))
        is_fba = bool(p or (m and m.get("afn-listing-exists", "").lower() == "yes")
                      or l.get("fulfillment-channel", "").upper().startswith("AMAZON"))
        fo = num(p.get("featuredoffer-price"))
        yp = first(num(p.get("your-price")), num(m.get("your-price")), num(l.get("price")))
        info[sku] = dict(p=p, m=m, l=l, asin=asin, fba=is_fba, fo=fo, yp=yp, fo_plan=fo, esp_src="planning" if fo else "", flag="", live=None)
    # ---- the price the profit is calculated on: the live Buy Box, not your own offer price
    live_all, live_age = (AP.load(PRICING_FILE) if AP else (None, None))
    if AP and live_all is None:
        warnings.append("live Buy Box prices are %s: the Buy Box of the planning report is used instead (run refresh to read them live)" %
                        ("missing" if live_age is None else "%.0f hours old" % live_age))
    if AP:
        for sku, i in info.items():
            if not i["fba"] or not i["asin"]:
                continue
            o_ = ords.get(i["asin"], {})
            real30 = (o_.get("rev30", 0) / o_["q30"]) if o_.get("q30", 0) >= 3 else None
            lv = (live_all or {}).get(i["asin"])
            if live_all is None:
                continue                         # no live data at all: keep the planning-report Buy Box as before
            esp, src, flag = AP.effective_price(lv, i["fo_plan"], real30, i["yp"], q30=o_.get("q30", 0))
            i["live"], i["esp_src"], i["flag"], i["real30"] = lv, src, flag, real30
            i["fo"] = esp
    # SKUs that no longer have a listing (not in the listings report) and have no stock and nothing inbound:
    # Amazon cannot give a fee for them. They stay in the sheet (so your formulas keep working) but are marked and skipped.
    ghosts = []
    if lst_rows:
        for sku, i in info.items():
            if not i["l"] and num(i["p"].get("available"), 0) == 0 and num(i["p"].get("inbound-quantity"), 0) == 0 \
                    and num(i["m"].get("afn-total-quantity"), 0) == 0:
                ghosts.append(sku); i["flag"] = (i["flag"] + " NOT LISTED").strip(); i["fo"] = None; i["esp_src"] = "none"   # no listing = no price, so nothing gets bought for it
        if ghosts:
            warnings.append("%d SKU(s) have no listing on Amazon any more (no stock, nothing inbound) - not priced, no fee asked: %s" %
                            (len(ghosts), ", ".join(sorted(ghosts))))
    suggest_aliases(info, ords, aliases, ghosts, warnings)
    if not skip_fees and creds is not None:
        wanted = {s: (first(i["fo"], i["yp"]), i["fba"]) for s, i in info.items()
                  if i["asin"] and first(i["fo"], i["yp"]) and s not in ghosts}
        try:
            fetch_fees(creds, wanted, cache, warnings)
        except SpApiError as e:
            warnings.append("fees: " + str(e)[:200])
    fee_preview_fallback(cache, info, warnings)
    # complete fees are remembered; a SKU with no complete fee today falls back to the last complete one
    try:
        good = json.load(open(FEE_GOOD)) if os.path.exists(FEE_GOOD) else {}
    except Exception:
        good = {}
    for sku, v in cache.items():
        if sku in info and (v.get("fba_fee", 0) > 0 or not info[sku]["fba"]) and v.get("total", 0) > 0:
            good[sku] = {"total": v["total"], "fba_fee": v.get("fba_fee", 0), "price": v.get("price", 0),
                         "date": dt.date.today().isoformat()}
    used_good = []
    for sku, i in info.items():
        if sku not in cache and sku in good:
            g = good[sku]
            cache[sku] = {"total": g["total"], "fba": i["fba"], "fba_fee": g["fba_fee"], "price": g["price"],
                          "src": "last_good"}
            used_good.append(sku)
    if used_good:
        warnings.append("%d fee(s) are the last known complete fee (Amazon gave none/incomplete today): %s"
                        % (len(used_good), ", ".join(used_good[:12])))
    # last resort, automatic: referral 15% of price + typical FBA fee of similar-priced products (clearly flagged)
    known = [(first(i["fo"], i["yp"]), cache[s_]["fba_fee"]) for s_, i in info.items()
             if s_ in cache and i["fba"] and cache[s_].get("fba_fee", 0) > 0 and first(i["fo"], i["yp"])]
    est = []
    for sku, i in info.items():
        px = first(i["fo"], i["yp"])
        if sku in cache or not px or not i["fba"]:
            continue
        near = sorted(f for p_, f in known if 0.7 * px <= p_ <= 1.3 * px) or sorted(f for _, f in known)
        if not near:
            continue
        fba = near[len(near) // 2]
        cache[sku] = {"total": round(0.15 * px + fba, 2), "fba": True, "fba_fee": round(fba, 2),
                      "price": px, "src": "estimate"}
        est.append(sku)
    if est:
        warnings.append("%d fee(s) are ESTIMATES (15%% referral + typical FBA fee) until Amazon gives a real one: %s"
                        % (len(est), ", ".join(est[:12])))
    if os.path.exists(FEE_OVERRIDE):                      # your own numbers win over everything
        for r in read_tsv(FEE_OVERRIDE) or []:
            sku, tot = r.get("sku", ""), num(r.get("total"))
            if sku in info and tot:
                cache[sku] = {"total": tot, "fba": info[sku]["fba"], "fba_fee": first(num(r.get("fba_fee")), 0),
                              "price": 0, "src": "override"}
    json.dump(cache, open(FEE_CACHE, "w"))
    json.dump(good, open(FEE_GOOD, "w"))

    today = dt.date.today()
    stamp_txt = today.strftime("%b %d, %Y") + ", 12:00 AM"
    inv_lines, plan_lines = [], []
    plan_hdr = ["asin", "sku"] + [snake(c) for c in PLAN_COLS] + \
        ["ord_units_7", "ord_units_30", "ord_units_60", "ord_units_90", "ord_sales_90",
         "ord_orders_30", "ord_last_sale_date", "fee_total", "fee_fba", "fee_price_used",
         "bb_live", "bb_report", "low_new", "low_fba", "offers_n", "real_price_30", "price_used", "price_src", "price_flag"]
    # true demand (corrected for out-of-stock days).  Sources, in this order:
    #   1. a folder with the order/ledger history (the cloud feed: env DEMAND_STATE or ./state)
    #   2. the compact copy the cloud feed publishes every day (feed\\demand_hist.json) - downloaded here, 150 KB, no sign-in needed
    # absent / failed = the dem_* columns stay empty and the workbook plans with the old sales speed (never an error)
    dem_sold, dem_stock = {}, {}
    _dem = None
    try:
        import demand as _dem
        sd = os.environ.get("DEMAND_STATE") or os.path.join(BASE, "state")
        if os.path.isdir(sd) and glob_any(sd, "orders_*.tsv"):
            dem_sold, dem_stock = _dem.load(sd)
            print("demand history: %d products with orders, %d with a stock ledger (folder %s)" % (len(dem_sold), len(dem_stock), sd))
        else:
            hp, why = fetch_demand_hist(creds)
            if hp:
                dem_sold, dem_stock = _dem.load_compact(hp)
                print("demand history: %d products with orders, %d with a stock ledger (%s)" % (len(dem_sold), len(dem_stock), why))
            else:
                warnings.append("demand history not available (%s) - dem_* columns are empty, the workbook uses the old sales speed" % why)
        plan_hdr += _dem.COLS
    except Exception as e:
        _dem = None
        warnings.append("demand columns skipped: %s" % str(e)[:120])
    audit = []
    for sku in skus:
        i = info[sku]; p, m, l = i["p"], i["m"], i["l"]
        if not i["asin"]:
            warnings.append("no ASIN for sku %s - skipped" % sku); continue
        avail = first(num(m.get("afn-fulfillable-quantity")), num(p.get("available")), 0)
        if m:
            inbound = sum(num(m.get(k), 0) for k in ("afn-inbound-working-quantity",
                          "afn-inbound-shipped-quantity", "afn-inbound-receiving-quantity"))
        else:
            inbound = num(p.get("inbound-quantity"), 0)
        unf = first(num(m.get("afn-unsellable-quantity")), num(p.get("unfulfillable-quantity")), 0)
        res = first(num(m.get("afn-reserved-quantity")), num(p.get("Total Reserved Quantity")), 0)
        onhand = first(num(m.get("afn-warehouse-quantity")), avail + res + unf)
        st = l.get("status", "") or "Active"
        if i["fba"] and avail == 0 and st.lower() == "active":
            st = "Out of stock Replenish inventory"
        c_txt = "%s Last updated %s" % (st, stamp_txt)
        name = clean_name(first(p.get("product-name"), m.get("product-name"), l.get("item-name"), sku))
        d_txt = "Product image %s ASIN %s SKU %s" % (name, i["asin"], sku)
        fn = first(p.get("fnsku"), m.get("fnsku"))
        if i["fba"] and fn:
            d_txt += " FNSKU " + fn
        s30, u30, rk = num(p.get("sales-shipped-last-30-days")), num(p.get("units-shipped-t30")), num(p.get("sales-rank"))
        e_txt = ("Sales $%s Units sold %d" % (format(s30, ",.0f"), u30)) if (s30 is not None and u30 is not None) \
            else "Sales -- Units sold --"
        e_txt += " Page views -- Sales rank %s (%s)" % ((format(rk, ",.0f") if rk else "--"),
                                                     clean_name(p.get("product-group", "") or "n/a"))
        f_txt = ("On-hand (FBA) %d Available %d Inbound %d Unfulfillable %d Reserved %d"
                 % (onhand, avail, inbound, unf, res)) if i["fba"] else "Available (FBM) Shipping template Migrated Template"
        # FBM listings are not in the planning report, so take their price from the listings report
        # no Buy Box price (or an FBM listing): use your own listed price, unless the listing is blocked/incomplete
        shown = i["fo"] or (i["yp"] if st.lower() in ("active", "inactive") else None)
        if i["fba"] and not i["fo"] and i.get("esp_src") == "none":
            shown = 0.0              # no Buy Box, no recent sale: no honest price exists -> $0.00 (never your own unverified price): the product scores 0
        g_txt = "Price USD Featured offer %s Business price Set View reference prices" % \
            (("$%.2f + $0.00" % shown) if (shown is not None and (shown > 0 or i.get("esp_src") == "none")) else "--")
        fee = cache.get(sku)
        if fee and i["fba"]:
            h_txt = "Total fees $%.2f FBA fee $%.2f" % (fee["total"], fee.get("fba_fee", 0))
        elif fee:
            h_txt = "Total fees $%.2f" % fee["total"]
        else:
            h_txt = "Total fees --"
        inv_lines.append("\t".join([c_txt, d_txt, e_txt, f_txt, g_txt, h_txt]))

        o = ords.get(i["asin"], {})
        row = [i["asin"], sku] + [p.get(c, "") for c in PLAN_COLS] + \
            [o.get("u7", 0), o.get("u30", 0), o.get("u60", 0), o.get("u90", 0), round(o.get("rev90", 0), 2),
             len(o.get("o30", ())), o.get("last", ""),
             "%.2f" % fee["total"] if fee else "", "%.2f" % fee.get("fba_fee", 0) if fee else "",
             "%.2f" % fee["price"] if fee else ""]
        lv = i.get("live") or {}
        _f = lambda v: ("%.2f" % v) if v else ""
        extra = [_f(lv.get("bb")), _f(i.get("fo_plan")), _f(lv.get("low_new")), _f(lv.get("low_afn")), lv.get("n_offers", ""),
                 _f(i.get("real30")), _f(i.get("fo")), i.get("esp_src", ""), i.get("flag", "")]
        row += extra
        if _dem:
            dm = _dem.one(dem_sold.get(sku, {}), dem_stock.get(sku, {}), today, avail if i["fba"] else None, inbound) if (sku in dem_sold or sku in dem_stock) else {}
            row += [dm.get(c, "") for c in _dem.COLS]
        plan_lines.append("\t".join(str(x) for x in row))
        if i["fba"]:
            audit.append([i["asin"], sku, name[:60], _f(i["yp"]), _f(i.get("fo_plan")), _f(lv.get("bb")), _f(lv.get("low_new")), _f(lv.get("low_afn")),
                          lv.get("n_offers", ""), _f(i.get("real30")), o.get("u30", 0), _f(i.get("fo")), i.get("esp_src", ""), i.get("flag", "")])

    def w(name, text):
        with open(os.path.join(FEED_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    w("inventory_C_H.tsv", "\n".join(inv_lines) + "\n")
    w("price_audit.tsv", "\n".join("\t".join(str(x) for x in r_) for r_ in
        [["asin", "sku", "product", "your_price", "buy_box_report", "buy_box_live", "lowest_new", "lowest_fba", "offers", "sold_price_30d", "units_30d",
          "PRICE_USED", "source", "flag"]] + audit) + "\n")
    w("planning_Z.tsv", "\t".join(plan_hdr) + "\n" + "\n".join(plan_lines) + "\n")
    if myi_rows is not None:
        raw = decode(open(os.path.join(RAW_DIR, "fba_myi_inventory_latest.tsv"), "rb").read())
        w("fba_A_X.tsv", "\n".join(l for l in raw.splitlines() if l.strip()) + "\n")
    snap = first(*[r.get("snapshot-date") for r in (plan_rows or [])[:1]]) or ""
    status = {"built": dt.datetime.now().isoformat(timespec="seconds"), "amazon_snapshot": snap,
              "inventory_rows": len(inv_lines), "fba_rows": len(myi_rows or []),
              "fees_known": sum(1 for s in skus if s in cache), "warnings": warnings[:50]}
    w("feed_status.json", json.dumps(status, indent=2))
    print("\nBuilt feed files in: " + FEED_DIR)
    print("  Inventory rows: %d | FBA rows: %d | fees known: %d" %
          (status["inventory_rows"], status["fba_rows"], status["fees_known"]))
    for x in warnings[:10]:
        print("  note: " + x)
    return 0


# --------------------------------------------------------------------- commands
def cmd_test(creds):
    print("Checking login with Amazon ...")
    get_access_token(creds, force=True)
    print("  OK - credentials accepted.")
    print("Asking Amazon which stores this app can see ...")
    r = api(creds, "GET", "/sellers/v1/marketplaceParticipations")
    rows = r.get("payload", r) or []
    found_us = False
    for p in rows:
        m, part = p.get("marketplace", {}), p.get("participation", {})
        print("  %-3s %-22s participating=%s" % (m.get("countryCode"), m.get("name"), part.get("isParticipating")))
        found_us = found_us or m.get("id") == MARKETPLACE
    print("\nRESULT: " + ("SUCCESS - US marketplace is reachable." if found_us else
          "Connected, but the US marketplace was not listed - tell Claude what is printed above."))


def cmd_pull(creds, days, only, skip_orders, skip_pricing=False):
    os.makedirs(RAW_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    status, summary = {}, []
    wanted = [k for k in REPORTS if (not only or k in only)]
    jobs, kinds = {}, {}

    print("Requesting reports ...")
    for k in wanted:
        rtype, stem = REPORTS[k]
        try:
            jobs[k] = create_report(creds, rtype); kinds[k] = ("single", stem)
        except SpApiError as e:
            status[k] = "REQUEST FAILED: " + str(e)[:300]; print("  %s: %s" % (k, status[k]))
        time.sleep(2)

    if not skip_orders and (not only or "orders" in only):
        end = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0) - dt.timedelta(minutes=10)
        remaining, chunk_no = days, 0
        while remaining > 0:
            span = min(29, remaining)
            start = end - dt.timedelta(days=span)
            label = "orders_%02d" % chunk_no
            try:
                jobs[label] = create_report(creds, ORDERS_TYPE, start, end)
                kinds[label] = ("order_chunk", "orders_%dd" % days)
            except SpApiError as e:
                status[label] = "REQUEST FAILED: " + str(e)[:300]; print("  %s: %s" % (label, status[label]))
            end, remaining, chunk_no = start, remaining - span, chunk_no + 1
            time.sleep(2)

    print("Waiting for Amazon to build them (usually 1-10 minutes) ...")
    results = wait_for(creds, jobs) if jobs else {}
    order_blobs, order_stem = [], None
    for label, (st, doc) in results.items():
        kind, stem = kinds[label]
        if st != "DONE" or not doc:
            status[label] = st; continue
        try:
            blob = download(creds, doc)
        except Exception as e:
            status[label] = "DOWNLOAD FAILED: %s" % e; continue
        if kind == "single":
            save(stem, blob, stamp); status[label] = "OK"
            lines = decode(blob).splitlines()
            summary.append((stem, len(lines) - 1, lines[0].split("\t") if lines else []))
        else:
            order_blobs.append(blob); order_stem = stem; status[label] = "OK"
    # FBA inventory report sometimes returns FATAL: retry once, then try the alternate report type
    if status.get("myi") in ("FATAL", "CANCELLED", "TIMEOUT") and (not only or "myi" in only):
        for attempt, rtype in enumerate((MYI_FALLBACK_TYPE,)):   # the first type already failed; do not repeat it
            print("  FBA inventory report failed - retrying (%s) ..." % rtype)
            try:
                rid = create_report(creds, rtype)
                st, doc = wait_for(creds, {"myi": rid}, 20)["myi"]
                if st == "DONE" and doc:
                    blob = download(creds, doc)
                    save("fba_myi_inventory", blob, stamp); status["myi"] = "OK"
                    lines = decode(blob).splitlines()
                    summary.append(("fba_myi_inventory", len(lines) - 1, lines[0].split("\t") if lines else []))
                    break
            except SpApiError as e:
                print("    " + str(e)[:200])
    if order_blobs:
        merged = merge_chunks(order_blobs)
        save(order_stem, merged, stamp)
        lines = decode(merged).splitlines()
        summary.append((order_stem, len(lines) - 1, lines[0].split("\t") if lines else []))

    if AP and not skip_pricing:
        try:
            pr = read_tsv(os.path.join(RAW_DIR, "fba_inventory_planning_latest.tsv")) or []
            ls = read_tsv(os.path.join(RAW_DIR, "merchant_listings_latest.tsv")) or []
            asins = {r.get("asin", "") for r in pr} | {r.get("asin1", "") for r in ls}
            print("Reading the live Buy Box price of %d ASINs (about %d minutes) ..." % (len(asins), max(1, len(asins) // 40)))
            live = AP.fetch(api, creds, asins)
            AP.save(PRICING_FILE, live)
            status["pricing"] = "OK"
            print("  live prices: %d ASINs" % len(live))
        except Exception as e:
            status["pricing"] = "FAILED: " + str(e)[:200]
            print("  live Buy Box prices could not be read (%s) - the planning report's Buy Box is used instead" % str(e)[:150])
    with open(os.path.join(RAW_DIR, "headers_summary.txt"), "w", encoding="utf-8") as f:
        f.write("Generated %s  (column names and row counts only, no data)\n\n" % stamp)
        for stem, n, cols in summary:
            f.write("== %s  |  %d rows  |  %d columns\n" % (stem, n, len(cols)))
            f.write("\n".join("   %2d  %s" % (i + 1, c) for i, c in enumerate(cols)) + "\n\n")
    with open(os.path.join(RAW_DIR, "last_run.json"), "w", encoding="utf-8") as f:
        json.dump({"finished": dt.datetime.now().isoformat(timespec="seconds"), "status": status}, f, indent=2)

    print("\nSummary")
    for k, v in status.items():
        print("  %-14s %s" % (k, v))
    print("\nFiles are in: " + RAW_DIR)
    print("Send Claude the file raw\\headers_summary.txt (it contains no sales data).")
    soft = ("feeprev", "pricing") + (("myi",) if status.get("planning") == "OK" else ())   # myi is rebuilt from planning if it failed
    hard = {k: v for k, v in status.items() if k not in soft}
    return 0 if all(v == "OK" for v in hard.values()) else 1


class _Tee:
    """Copies everything printed to refresh_log.txt as well (the log is kept to about 1 MB)."""
    def __init__(self, stream, fh):
        self.s, self.fh = stream, fh
    def write(self, t):
        try: self.s.write(t)
        except Exception: pass
        try: self.fh.write(t); self.fh.flush()
        except Exception: pass
        return len(t)
    def flush(self):
        try: self.s.flush()
        except Exception: pass
    def __getattr__(self, n):
        return getattr(self.s, n)


def start_log(cmd):
    try:
        path = os.path.join(BASE, "refresh_log.txt")
        if os.path.exists(path) and os.path.getsize(path) > 1000000:
            keep = open(path, "rb").read()[-300000:]
            open(path, "wb").write(keep)
        fh = open(path, "a", encoding="utf-8", errors="replace")
        fh.write("\n==== %s | %s ====\n" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cmd))
        sys.stdout = _Tee(sys.stdout, fh)
        sys.stderr = _Tee(sys.stderr, fh)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test", help="check credentials and connection")
    for name, h in (("pull", "download the reports"), ("refresh", "pull + build"), ("build", "build feed files from raw")):
        p = sub.add_parser(name, help=h)
        if name != "build":
            p.add_argument("--days", type=int, default=90, help="days of order history (default 90)")
            p.add_argument("--only", default="", help="comma list: planning,myi,listings,orders")
            p.add_argument("--skip-orders", action="store_true")
            p.add_argument("--skip-pricing", action="store_true", help="do not read the live Buy Box prices (saves ~5 minutes)")
        if name != "pull":
            p.add_argument("--skip-fees", action="store_true", help="do not call the fee-estimate API")
    a = ap.parse_args()
    start_log(a.cmd)
    creds = load_credentials()
    try:
        if a.cmd == "test":
            cmd_test(creds); return 0
        if a.cmd == "build":
            return cmd_build(creds, a.skip_fees)
        only = [x.strip() for x in a.only.split(",") if x.strip()]
        rc = cmd_pull(creds, a.days, only, a.skip_orders, a.skip_pricing)
        if a.cmd == "refresh":
            rc2 = cmd_build(creds, a.skip_fees)
            return rc or rc2
        return rc
    except SpApiError as e:
        print("\nERROR: " + str(e))
        if "403" in str(e) or "Unauthorized" in str(e):
            print("Hint: a 403/Unauthorized usually means the app is missing a role, or the app was not authorized for this seller account.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
