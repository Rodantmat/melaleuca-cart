"""Stricter checks on deal_finder output: product-match grade (photo + attribute/pack agreement), competition reality (top listings' reviews, Amazon retail, seller count),
listing restrictions (gated / approval) and a verdict per row: GO / WATCH / SKIP (markets) and GO / WATCH / NO TWIN / SKIP (abandoned). Read-only everywhere."""
import os, re, time
import spapi

ROI_GO = float(os.environ.get("ROI_GO", "0.50"))          # min ROI at estimated wholesale for GO
PROFIT_GO = float(os.environ.get("PROFIT_GO", "300"))     # min projected $/month after ads for GO
PROFIT_WATCH = float(os.environ.get("PROFIT_WATCH", "150"))
SELLERS_MAX = int(os.environ.get("SELLERS_MAX", "8"))
REV_CEIL = int(os.environ.get("REV_CEIL", "3000"))        # a top competitor above this many reviews is entrenched
AB_RANK_MAX = int(os.environ.get("AB_RANK_MAX", "60000"))
REV_MIN = int(os.environ.get("REV_MIN", "5"))
DP_CAND = int(os.environ.get("DP_CAND", "30"))

_UNITS = {"oz": "oz", "ounce": "oz", "ml": "ml", "l": "l", "liter": "l", "litre": "l", "inch": "in", "in": "in", "cm": "cm", "mm": "mm", "ft": "ft",
          "w": "w", "v": "v", "mah": "mah", "qt": "qt", "gal": "gal", "lb": "lb", "lbs": "lb", "kg": "kg", "g": "g"}
_ATTR = re.compile(r"(\d+(?:\.\d+)?)\s*(oz|ounces?|ml|liters?|litres?|l|inch(?:es)?|in|cm|mm|ft|w|v|mah|qt|gal|lbs?|kg|g)\b", re.I)


def attrs(t):
    d = {}
    for n, u in _ATTR.findall(t or ""):
        u = _UNITS.get(u.lower().rstrip("s") if u.lower() not in _UNITS else u.lower(), None) or _UNITS.get(u.lower())
        if u:
            d.setdefault(u, set()).add(float(n))
    return d


_MAT = ("glass", "plastic", "stainless", "silicone", "bamboo", "wood", "ceramic", "aluminum", "metal", "cotton", "velvet", "leather")


def mat_conflict(t1, t2):
    a = {m for m in _MAT if m in (t1 or "").lower()}
    b = {m for m in _MAT if m in (t2 or "").lower()}
    return ["material %s vs %s" % (sorted(a), sorted(b))] if a and b and not (a & b) else []


def attr_conflict(t1, t2):
    """Units both titles state (e.g. 16oz vs 32oz, 90L vs 60L) whose values never come within 15% of each other."""
    a, b = attrs(t1), attrs(t2)
    bad = []
    for u in set(a) & set(b):
        if not any(abs(x - y) <= 0.15 * max(x, y) for x in a[u] for y in b[u]):
            bad.append("%s %s vs %s" % (u, sorted(a[u])[:2], sorted(b[u])[:2]))
    return bad


def grade_market(r):
    why = []
    conf = attr_conflict(r.get("temu_title"), r.get("ref_title")) + mat_conflict(r.get("temu_title"), r.get("ref_title"))
    if conf:
        why.append("attribute mismatch: " + "; ".join(conf))
    ratio = r.get("pack_ratio") or 1.0
    if ratio > 4 or ratio < 0.25:
        why.append("pack size differs x%.1f" % ratio)
    amz, src = r.get("amz_price") or 0, (r.get("temu_price") or 0) * ratio
    if src and amz / src > 8:
        why.append("price gap x%.0f (likely different product)" % (amz / src))
    if why:
        return "C", why
    return ("A" if r.get("match_conf") == "PHOTO MATCH" else "B"), why


AMZ_MAX = int(os.environ.get("APIFY_AMZ_MAX", "10"))     # paid Apify lookups per run (~$0.007 each; the free plan has $5/month) - results cached 7 days


def _seller_id(c):
    if c.get("SELLER_ID"):
        return c["SELLER_ID"]
    try:
        m = re.search(r'ME\s*=\s*"(A[0-9A-Z]{10,})"', open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reprice", "bb_intel.py")).read())
        return m.group(1) if m else None
    except Exception:
        return None


def review_info(asins):
    """{asin: {rating, reviews}} from the 7-day cache in Postgres, then Apify for up to AMZ_MAX missing ones (priority order of `asins`)."""
    out, miss = {}, []
    url = os.environ.get("DATABASE_URL", "")
    cx = None
    try:
        import psycopg
        cx = psycopg.connect(url) if url else None
        if cx:
            cx.execute("create table if not exists deals.asin_cache (asin text primary key, fetched_at timestamptz default now(), rating numeric, reviews int)")
            for a, r, n in cx.execute("select asin, rating, reviews from deals.asin_cache where asin = any(%s) and fetched_at > now() - interval '7 days'", (list(asins),)).fetchall():
                out[a] = {"rating": float(r) if r is not None else None, "reviews": n}
    except Exception as e:
        print("  review cache unavailable:", str(e)[:80])
    miss = [a for a in asins if a not in out][:AMZ_MAX]
    if miss and os.environ.get("APIFY_TOKEN"):
        try:
            import apify_source
            got = apify_source.amazon_info(miss)
            for a, d in got.items():
                out[a] = d
                if cx:
                    cx.execute("insert into deals.asin_cache(asin, rating, reviews) values (%s,%s,%s) on conflict (asin) do update set fetched_at=now(), rating=excluded.rating, reviews=excluded.reviews", (a, d.get("rating"), d.get("reviews")))
            if cx:
                cx.commit()
        except Exception as e:
            print("  apify amazon lookup failed:", str(e)[:100])
    print("  reviews: %d cached/fetched of %d wanted (paid lookups capped at %d)" % (len(out), len(asins), AMZ_MAX))
    return out


def restricted(c, asin):
    """True = gated / approval needed, False = can list as new, None = could not check."""
    sid = _seller_id(c)
    if not sid:
        return None
    try:
        j = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params={"asin": asin, "sellerId": sid, "marketplaceIds": spapi.MARKETPLACE,
                                                                           "conditionType": "new_new", "reasonLocale": "en_US"}, quiet=True, tries=3)
        return bool(j.get("restrictions"))
    except Exception as e:
        ERR[str(e)[:60].split(":")[0]] = ERR.get(str(e)[:60].split(":")[0], 0) + 1
        return None


ERR = {}


def run(c, rows, abrows, pool, page_details):
    for r in rows:
        r["grade"], r["why_not"] = grade_market(r)
    cand = sorted([r for r in rows if r["grade"] in ("A", "B") and (r.get("roi_wholesale") or 0) >= 0.3 and (r.get("profit_month") or 0) >= PROFIT_WATCH],
                  key=lambda r: -(r.get("profit_month") or 0))[:DP_CAND]
    asins = []
    for r in cand:
        top = sorted((a for a in (r.get("asins") or "").split() if a in pool), key=lambda a: -(pool[a].get("est_sales") or 0))[:2]
        asins += [r["ref_asin"]] + top
    asins = list(dict.fromkeys(asins))
    pages = review_info(asins) if asins else {}
    errs = {}
    for d in pages.values():
        k = "ok" if d.get("reviews") is not None else "no reviews field"
        errs[k] = errs.get(k, 0) + 1
    print("  validation: %d candidates, %d asins with review data: %s" % (len(cand), len(pages), errs))
    for r in cand:
        tops = sorted((a for a in (r.get("asins") or "").split() if a in pool), key=lambda a: -(pool[a].get("est_sales") or 0))[:2]
        ds = [pages.get(a) or {} for a in dict.fromkeys([r["ref_asin"]] + tops)]
        revs = [d.get("reviews") for d in ds if d.get("reviews") is not None]
        r["top_reviews"] = max(revs) if revs else None
        r["top_rating"] = next((d.get("rating") for d in ds if d.get("rating")), None)
        r["ref_bought_month"] = (pages.get(r["ref_asin"]) or {}).get("bought_month")
        r["gated"] = restricted(c, r["ref_asin"])
        time.sleep(0.4)
    print("  validation: restriction check errors: %s, seller id present: %s" % (ERR or "none", bool(_seller_id(c))))
    for r in rows:
        why = list(r.get("why_not") or [])
        if r["grade"] != "C":
            if r.get("fees_src") != "spapi":
                why.append("fees are a guess")
            if (r.get("roi_wholesale") or 0) < ROI_GO:
                why.append("ROI under %d%%" % (ROI_GO * 100))
            if (r.get("profit_month") or 0) < PROFIT_GO:
                why.append("profit under $%d/month" % PROFIT_GO)
            if r.get("amazon_sells"):
                why.append("Amazon sells it")
            if (r.get("sellers") or 0) > SELLERS_MAX:
                why.append("%d sellers" % r["sellers"])
            if r.get("risk_flag"):
                why.append("risk: %s" % r["risk_flag"])
            if "top_reviews" not in r:
                why.append("not checked in detail")
            else:
                if r["top_reviews"] is None:
                    why.append("competitor reviews unknown")
                elif r["top_reviews"] > REV_CEIL:
                    why.append("entrenched competitor (%d reviews)" % r["top_reviews"])
                # a gated competitor ASIN only blocks *joining* that listing; Rodo sells generic on his own new listing, so it is information, not a blocker
                r["path"] = "own listing only (that ASIN needs brand approval)" if r.get("gated") else "own listing or join"
                if r.get("ref_bought_month") is not None and r["ref_bought_month"] < 0.4 * (r.get("market_sales_month") or 0) and r["ref_bought_month"] < 100:
                    why.append("Amazon shows only %s bought/month" % r["ref_bought_month"])
        r["why_not"] = why
        if r["grade"] == "C" or (r.get("roi_wholesale") or 0) < 0.3 or (r.get("profit_month") or 0) < PROFIT_WATCH:
            r["verdict"] = "SKIP"
        elif not why:
            r["verdict"] = "GO"
        else:
            r["verdict"] = "WATCH"
    need = [x["asin"] for x in sorted((y for y in abrows if y.get("temu_twin") and (y.get("roi_wholesale") or 0) >= 0.3 and (y.get("rank") or 9e9) <= AB_RANK_MAX
                                       and y.get("reviews") is None), key=lambda y: y.get("rank") or 9e9)][:max(3, AMZ_MAX // 3)]
    if need:
        for a, d in review_info(need).items():
            for x in abrows:
                if x["asin"] == a:
                    x["reviews"], x["rating"] = d.get("reviews"), d.get("rating")
    for x in abrows:
        why = []
        if (x.get("reviews") or 0) < REV_MIN:
            why.append("reviews %s" % (x.get("reviews") if x.get("reviews") is not None else "unknown"))
        if x.get("rating") and float(str(x["rating"]).replace(",", ".").split()[0]) < 4.0:
            why.append("rating under 4.0")
        if (x.get("rank") or 9e9) > AB_RANK_MAX:
            why.append("rank too low for real demand")
        if not x.get("temu_twin"):
            why.append("no cheap twin found")
        elif (x.get("roi_wholesale") or 0) < ROI_GO:
            why.append("ROI under %d%%" % (ROI_GO * 100))
        x["why_not"] = why
        if "reviews" not in " ".join(why) and "rank" not in " ".join(why) and x.get("temu_twin") and (x.get("roi_wholesale") or 0) >= 0.3:
            x["gated"] = restricted(c, x["asin"])
            if x["gated"]:
                x["why_not"].append("gated / approval needed")
            x["verdict"] = "GO" if not x["why_not"] else "WATCH"
        else:
            x["verdict"] = "NO TWIN" if not x.get("temu_twin") and not why[:-1] else "SKIP"
    return rows, abrows
