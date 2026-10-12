"""
melaleuca_offers_map.py - turns the scan results (melaleuca_offers.json) into rows for your Melaleuca tab.

Input : melaleuca_offers.json   (from melaleuca_scan.py)
        feed/mel_rows.tsv        (written by Excel: row, ASIN, product name, Mela ID)        -> see --rows
        offer_map.tsv            (optional, you can edit it: offer SKU -> ASINs / "ignore")  -> kept between runs
Output: account_offers.tsv       (read by Excel: one line per account + product)

For every offer the store shows:
   "Save $X on <product> 2-Pack"        -> the set is N units; each single row gets  units = N, unit price = pack price / N
   "Buy one <product>, get one for $Y"  -> 2 units
   "Buy two <product>, get one free"    -> 3 units
   "Deal of the Month / outlet"         -> 1 unit at the shown price
Offers for several different products (bundles), or products that are not in your sheet, are left out and listed in the report.
"""
import json, re, sys, csv, os, difflib

STOP = set("save on the and with of a an for get one buy two free pack packs special offer monthly deal bundle by oz fl loads".split())
SYN = {"omega3": "omega 3", "omega-3": "omega 3", "&": "and", "tub & tile": "tub and tile", "solumel": "sol u mel", "sol-u-mel": "sol u mel",
       "solu": "sol u", "sol-u-guard": "sol u guard", "pain-a-trate": "pain a trate", "melamagic": "mela magic", "mela-magic": "mela magic",
       "prespot": "pre spot", "sei bella": "seibella", "seibella": "seibella"}


def norm(s):
    s = (s or "").lower().replace("®", " ").replace("™", " ").replace("’", "'")
    for a, b in SYN.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [t for t in s.split() if t not in STOP and not t.isdigit()]


def units_of(title):
    t = title.lower()
    m = re.search(r"(\d+)\s*[-–]?\s*pack", t)
    if m:
        return int(m.group(1))
    if re.search(r"buy two .* get one", t):
        return 3
    if re.search(r"buy one .* get one", t):
        return 2
    return 0


def product_phrase(title):
    t = title
    t = re.sub(r"^(Deal of the Month|Monthly Special)\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"^Save \$[\d.,]+( - \$[\d.,]+)? on ", "", t, flags=re.I)
    t = re.sub(r"^Buy (one|two) ", "", t, flags=re.I)
    t = re.sub(r",\s*get one.*$", "", t, flags=re.I)
    t = re.sub(r"\d+\s*[-–]?\s*pack.*$", "", t, flags=re.I)
    t = re.sub(r"!.*$", "", t)
    return t.strip()


def load_rows(path):
    """Reads feed/mel_rows.tsv written by Excel (header: row, asin, name, type, T, U, V, W, X, melid, family, ...)."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.rstrip("\r\n").split("\t") for ln in f if ln.strip()]
    if not lines:
        return rows
    head = [h.strip().lower() for h in lines[0]]
    if "asin" in head:
        ia, inm = head.index("asin"), head.index("name") if "name" in head else 2
        iid = head.index("melid") if "melid" in head else 9
        irow = head.index("row") if "row" in head else 0
        data = lines[1:]
    else:                                                     # old test format: row, asin, name, melid
        ia, inm, iid, irow, data = 1, 2, 3, 0, lines
    for p in data:
        if len(p) > max(ia, inm) and p[ia].strip():
            rows.append({"row": p[irow], "asin": p[ia].strip(), "name": p[inm].strip(), "id": (p[iid].strip() if len(p) > iid else "")})
    return rows


def load_map(path):
    m = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            p = ln.rstrip("\n").split("\t")
            if len(p) >= 2 and p[0] and not p[0].startswith("#"):
                m[p[0].strip()] = [x.strip() for x in p[1].split(",") if x.strip()]
    return m


DROP = {"life", "vitality", "targeted", "bathroom", "cleaner", "essential", "basic", "collection", "detergent", "concentrate", "instant"}


def match_offer(title, rows):
    phrase = product_phrase(title)
    if " and " in phrase.lower() and re.search(r"bundle|treatment and", title, re.I):
        return []                                             # several different products in one offer
    ot = [t for t in norm(phrase) if t not in DROP]
    if len(ot) < 2 and not (len(ot) == 1 and len(ot[0]) >= 7):
        return []
    out = []
    for r in rows:
        if re.search(r"\d\s*-?\s*pack|with (bottle|pump|brush)", r["name"], re.I):
            continue                                          # pack rows / bottle rows are separate products
        rt = set(norm(r["name"]))
        ok = True
        for t in ot:
            if t in rt or (len(t) >= 7 and difflib.get_close_matches(t, list(rt), n=1, cutoff=0.9)):
                continue
            ok = False
            break
        if ok:
            out.append(r)
    return out


def map_account(acct, rows, omap):
    res, skipped = [], []
    byid = {}
    for r in rows:
        byid.setdefault(r["id"], []).append(r)
    lists = [("Special Offers", acct.get("special_offers") or [])]
    lists.append(("Deal of the Month", [c for c in (acct.get("monthly_specials") or [])]))
    for typ, items in lists:
        for o in items:
            sku = str(o.get("sku") or (o.get("skus") or [""])[0] or "")
            title = o.get("title") or ""
            price = o.get("price")
            pts = o.get("points")
            if price is None:
                continue
            if sku in omap:
                if omap[sku] == ["ignore"]:
                    continue
                matched = [r for r in rows if r["asin"] in omap[sku]]
                how = "map"
            elif sku and sku in byid and typ != "Special Offers":
                matched = byid[sku]; how = "sku"
            else:
                matched = match_offer(title, rows); how = "name"
            if re.match(r"^\s*Monthly Special", title, re.I):
                skipped.append((sku, title, "bundle of several products")); continue
            n = units_of(title) if typ == "Special Offers" else (units_of(title) or 1)
            if how == "sku" and typ != "Special Offers":
                n = 1
            if not matched:
                skipped.append((sku, title, "no product of your sheet matches")); continue
            if how == "name" and n == 0:
                n = 1
            if n > 2:
                skipped.append((sku, title, "needs %d units - the order limit is 2 units of a discounted product" % n)); continue
            for r in matched:
                res.append({"asin": r["asin"], "type": typ if how != "sku" else "Deal of the Month", "units": n, "unit_price": round(float(price) / n, 4),
                            "points": pts, "offer_sku": sku, "title": title, "how": how, "row": r["row"], "name": r["name"]})
    return res, skipped


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    offers = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "melaleuca_offers.json")
    rows_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "feed", "mel_rows.tsv")
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(here, "account_offers.tsv")
    omap = load_map(os.path.join(here, "offer_map.tsv"))
    rows = load_rows(rows_path)
    data = json.load(open(offers, encoding="utf-8"))
    lines = ["Tab\tASIN\tType\tUnits\tUnitPrice\tSetPoints\tOfferSku\tOfferTitle\tHow\tScanned"]
    rep = []
    # Canadian tabs (kind 1 = orange / yellow) show prices in CAD: their offers are priced with the US price of the same offer
    # (same offer number) read from the blue (all-inventory, US) accounts. Points and set sizes are the same.
    kinds = {}
    tp = os.path.join(os.path.dirname(os.path.abspath(rows_path)), "mel_tabs.txt")
    if os.path.exists(tp):
        for ln in open(tp, encoding="utf-8-sig"):
            p = ln.rstrip("\r\n").split("\t")
            if len(p) >= 3:
                kinds[p[1]] = p[2].strip()

    def osku(o):
        return str(o.get("sku") or (o.get("skus") or [""])[0] or "")

    usd = {}
    for a in data["accounts"]:
        if a.get("ok") and kinds.get(a.get("tab")) == "2":
            for lst in ("special_offers", "monthly_specials"):
                for o in a.get(lst) or []:
                    if o.get("price") is not None and osku(o):
                        usd.setdefault((lst, osku(o)), (o.get("price"), o.get("points")))
    for a in data["accounts"]:
        if a.get("ok") and kinds.get(a.get("tab")) == "1":
            import copy
            a = copy.deepcopy(a)
            data["accounts"][data["accounts"].index(next(x for x in data["accounts"] if x.get("tab") == a.get("tab")))] = a
            for lst in ("special_offers", "monthly_specials"):
                keep = []
                for o in a.get(lst) or []:
                    u = usd.get((lst, osku(o)))
                    if u:
                        o["price"], o["points"] = u[0], (u[1] if u[1] is not None else o.get("points"))
                        keep.append(o)
                    else:
                        rep.append("%s: offer %s %s dropped (no US price from the blue accounts)" % (a["tab"], osku(o), (o.get("title") or "")[:50]))
                a[lst] = keep
    for a in data["accounts"]:
        if not a.get("ok"):
            rep.append("%s: NOT scanned (%s)" % (a.get("tab"), a.get("error") or a.get("note")))
            continue
        res, skipped = map_account(a, rows, omap)
        for r in res:
            lines.append("\t".join(str(x) for x in (a["tab"], r["asin"], r["type"], r["units"], r["unit_price"], r["points"], r["offer_sku"], r["title"], r["how"], a["scanned"])))
        lines.append("\t".join((a["tab"], "*", "SCANNED", "0", "0", "0", "", "", "", a["scanned"])))
        rep.append("%s: %d offers on your products, %d not used" % (a["tab"], len(res), len(skipped)))
        for sku, t, why in skipped:
            rep.append("     not used: %s %s (%s)" % (sku, t[:70], why))
    open(out, "w", encoding="utf-8", newline="").write("\n".join(lines) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
