"""Temu -> Amazon deal finder (read-only on Amazon: catalog search, offers, fee estimates, public product pages - nothing is listed or changed).
v2 (2026-11-11): market level - every matching Amazon listing per Temu item (photo or strong title), all their sellers (incl. one seller
running several listings), total market sales, Amazon retail presence; plus a deep hunt for ABANDONED listings (0 sellers) with reviews.

For every cheap Temu item:
  1. find the matching Amazon listings (SP-API catalog keyword search, title similarity)
  2. read the live Buy Box / offers (reprice/amazon_pricing.py parser) -> COMPETITIVE / ABANDONED (no offers at all)
  3. estimate Amazon fees (SP-API fees estimate, FBA; falls back to referral 15% + size-tier FBA guess)
  4. profit = Amazon price - fees - Temu cost x (1 + tax) - inbound;  ROI = profit / landed cost
     ABANDONED listings have no live price -> report the break-even and target (ROI_MIN) price + list price if Amazon has one
Inputs: --from-json (a temu_bridge.py output) and/or --search "kw1|kw2" (pulls Temu live, paced).
Output: CSV + JSON ranked (best ROI first), printed top table.
"""
import argparse, csv, json, math, os, re, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
sys.path.insert(0, HERE)
import spapi  # noqa: E402

MK = spapi.MARKETPLACE
TAX = float(os.environ.get("TEMU_TAX", "0.0775"))        # San Diego sales tax on the Temu order
INBOUND = float(os.environ.get("INBOUND_PER_UNIT", "0.75"))  # shipping the unit into FBA
ROI_MIN = float(os.environ.get("ROI_MIN", "0.30"))
MAX_TEMU = float(os.environ.get("MAX_TEMU_PRICE", "25"))
SIM_MIN = float(os.environ.get("SIM_MIN", "0.30"))
WHOLESALE_F = float(os.environ.get("WHOLESALE_FACTOR", "0.60"))    # Alibaba unit price ~ Temu price x this
WHOLESALE_F_ALI = float(os.environ.get("WHOLESALE_FACTOR_ALI", "0.85"))  # AliExpress is already near factory price
FREIGHT = float(os.environ.get("FREIGHT_PER_UNIT", "1.00"))         # Alibaba freight + duties per unit (estimate)
# generic products only: no printed apparel / POD-style items, no brands, characters or licences
EXCLUDE = re.compile(r"\b(t-?shirts?|tees?|hoodies?|sweatshirts?|jumpsuit|mugs?|tumblers?|posters?|canvas|wall art|metal sign|signs?|stickers?|"
                     r"keychains?|flag|banner|blanket with|print(ed)? (t|tee|shirt)|graphic|slogan|quote|funny|christmas|halloween|"
                     r"disney|marvel|pokemon|hello kitty|barbie|nfl|nba|mlb|harry potter|star wars|nike|adidas|apple|iphone|samsung|"
                     r"stanley|yeti|owala|lego|sanrio|minecraft|bluey|jesus|christian)\b", re.I)
# extra Amazon paperwork even with liability insurance: CPC (children's), hazmat review (lithium), ingestible/cosmetic rules
RISK = re.compile(r"\b(lithium|li-ion|batter(y|ies) included|baby|infant|toddler|kids?|children|toys?|"
                  r"supplement|edible|cosmetic|serum|cream|lotion|helmet|life jacket|smoke detector|carbon monoxide)\b", re.I)
PER_KW = int(os.environ.get("PER_KW", "20"))                       # first N Temu results per keyword (Temu's own ranking)


def keyword_chunk(spec):
    """'chunk:2/4' -> [(category, keyword)] from temu/keywords.txt"""
    rows = []
    for ln in open(os.path.join(HERE, "keywords.txt")):
        ln = ln.strip()
        if ln and not ln.startswith("#") and "|" in ln:
            c_, k_ = [x.strip() for x in ln.split("|", 1)]; rows.append((c_, k_))
    n, m = [int(x) for x in spec.split(":", 1)[1].split("/")]
    size = -(-len(rows) // m)
    return rows[(n - 1) * size:n * size]


_UNUSED_DEFAULT_KWS = ("kitchen gadgets|vegetable chopper|silicone kitchen utensils|drawer organizer|fridge organizer|spice rack organizer|"
               "under sink organizer|cable organizer|closet organizer|shoe rack|bathroom organizer|shower caddy|cleaning brush|"
               "lint remover|reusable food storage|oil sprayer|garlic press|measuring cups|can opener|ice cube tray|"
               "car organizer|phone stand|desk organizer|travel organizer|jewelry organizer|makeup organizer|storage bins|"
               "hangers|clothes drying rack|pet hair remover")
STOP = set("a an and the for with of in on to by from at as is it this that your you our pc pcs 1pc 2pcs piece pieces set pack "
           "new 2d flat not 3d style design gift gifts women's men's womens mens unisex suitable perfect ideal use".split())


def toks(s):
    s = (s or "").lower().replace("&#39;", "'")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [t for t in s.split() if t not in STOP and len(t) > 1 and not re.fullmatch(r"\d+(pc|pcs)?", t)]


def sim(a, b):
    A, B = set(toks(a)), set(toks(b))
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B)) ** 0.5 / float(min(len(A), len(B))) ** 0.5   # cosine-like overlap


BIG_BRANDS = re.compile(r"^(apple|samsung|google|amazon|amazon basics|anker|oxo|ninja|keurig|cuisinart|kitchenaid|hamilton beach|black\+decker|"
                        r"dyson|shark|bissell|rubbermaid|tupperware|pyrex|lodge|zojirushi|instant pot|instant|nespresso|breville|stanley|yeti|"
                        r"owala|simple modern|hydro flask|kong|petsafe|chewy|3m|command|scotch|sharpie|lego|disney|nike|adidas|under armour|"
                        r"otterbox|spigen|belkin|logitech|bose|sony|jbl|philips|braun|conair|revlon|dash|chefman|magic bullet|nutribullet)$", re.I)
IMG_OK = int(os.environ.get("IMG_MAX_DIST", "12"))      # perceptual-hash distance (0 = identical photo, <=12 = same product photo)
RATIO_MAX = float(os.environ.get("PRICE_RATIO_MAX", "8"))  # Amazon price above 8x Temu = probably a different product -> CHECK
_hash_cache = {}


def img_hash(url):
    if isinstance(url, dict):
        url = url.get("url")
    if not url:
        return None
    url = url.replace("\\u002F", "/")
    if url in _hash_cache:
        return _hash_cache[url]
    h = None
    try:
        import io, imagehash
        from PIL import Image
        from curl_cffi import requests as cr
        u = url if "kwcdn" not in url else url.split("?")[0] + "?imageView2/2/w/500/q/70/format/webp"
        r = cr.get(u, impersonate="chrome", timeout=25)
        if r.status_code == 200:
            h = imagehash.phash(Image.open(io.BytesIO(r.content)).convert("RGB"))
    except Exception as e:
        print("  img ERR %s" % str(e)[:80])
    _hash_cache[url] = h
    return h


def img_dist(a, b):
    ha, hb = img_hash(a), img_hash(b)
    return int(ha - hb) if (ha is not None and hb is not None) else None


def query_for(title):
    return " ".join(toks(title)[:7])


def _parse_item(it):
    sm = (it.get("summaries") or [{}])[0]
    rank, sub = None, None
    for sr in it.get("salesRanks") or []:
        for d in sr.get("displayGroupRanks") or []:
            if d.get("rank") and (rank is None or d["rank"] < rank[0]):
                rank = (d["rank"], d.get("title"))
        for d in sr.get("classificationRanks") or []:
            if d.get("rank") and (sub is None or d["rank"] < sub[0]):
                sub = (d["rank"], d.get("title"))
    lp = None
    for x in ((it.get("attributes") or {}).get("list_price") or []):
        try:
            lp = float(x.get("value_with_tax") or x.get("value")); break
        except Exception:
            pass
    img = None
    for grp in it.get("images") or []:
        cand = [x for x in grp.get("images") or [] if x.get("variant") == "MAIN"]
        cand.sort(key=lambda x: abs((x.get("width") or 0) - 500))
        if cand:
            img = cand[0].get("link"); break
    return {"asin": it.get("asin"), "image": img, "title": sm.get("itemName") or "", "brand": sm.get("brand") or sm.get("brandName"),
            "rank": rank[0] if rank else None, "rank_cat": rank[1] if rank else None,
            "sub_rank": sub[0] if sub else None, "sub_cat": sub[1] if sub else None, "list_price": lp}


def catalog_search(c, q, size=10, pages=1):
    out, tok = [], None
    for _ in range(pages):
        prm = {"keywords": q, "marketplaceIds": MK, "includedData": "summaries,salesRanks,attributes,images", "pageSize": size}
        if tok:
            prm["pageToken"] = tok
        try:
            r = spapi.call(c, "GET", "/catalog/2022-04-01/items", params=prm, quiet=True, tries=4)
        except Exception as e:
            print("  catalog ERR %s" % str(e)[:120]); break
        out += [_parse_item(it) for it in r.get("items") or []]
        tok = (r.get("pagination") or {}).get("nextToken")
        time.sleep(0.6)
        if not tok:
            break
    return out


def fees_batch(c, pairs):
    """pairs [(asin, price)] -> {asin: total fees} via getMyFeesEstimates (batch of 20)."""
    res = {}
    for i in range(0, len(pairs), 20):
        chunk = pairs[i:i + 20]
        body = [{"FeesEstimateRequest": {"MarketplaceId": MK, "IsAmazonFulfilled": True, "Identifier": "%s@%.2f" % (a, p),
                                         "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": round(p, 2)}}},
                 "IdType": "ASIN", "IdValue": a} for a, p in chunk]
        try:
            r = spapi.call(c, "POST", "/products/fees/v0/feesEstimate", body=body, quiet=True, tries=4)
            for x in (r if isinstance(r, list) else r.get("payload") or []):
                fr = x.get("FeesEstimateResult") or x
                ident = ((fr.get("FeesEstimateIdentifier") or {}).get("IdValue"))
                tot = (((fr.get("FeesEstimate") or {}).get("TotalFeesEstimate") or {}).get("Amount"))
                if ident and tot is not None:
                    res[ident] = float(tot)
        except Exception as e:
            print("  fees ERR %s" % str(e)[:160])
        time.sleep(2.2)
    return res


# Monthly units from top-level Best Sellers Rank: log-interpolated bands (NovaData amazon.com band table, 2026, rounded, +/-50%).
# Categories without published bands use the conservative "other" curve. Calibrate later against the store's own real sales.
SALES_BANDS = {
    "home & kitchen":         [(50, 20000), (550, 8000), (3000, 2500), (15000, 600), (62500, 120), (250000, 15), (1000000, 2)],
    "health & household":     [(50, 18000), (550, 6500), (3000, 2000), (15000, 500), (62500, 100), (250000, 15), (1000000, 2)],
    "beauty & personal care": [(50, 15000), (550, 5500), (3000, 1800), (15000, 450), (62500, 90), (250000, 12), (1000000, 2)],
    "other":                  [(50, 12000), (550, 4500), (3000, 1500), (15000, 350), (62500, 70), (250000, 12), (1000000, 2)],
}
SHARE_HAIRCUT = float(os.environ.get("SHARE_HAIRCUT", "0.8"))      # you rarely get a full equal Buy Box share at first
YEAR_FACTOR = float(os.environ.get("YEAR_FACTOR", "0.75"))
NEW_LISTING_SHARE = float(os.environ.get("NEW_LISTING_SHARE", "0.10"))  # own new listing vs a 1-seller (brand) listing: ~10% of its sales after launch
PPC_PCT = float(os.environ.get("PPC_PCT", "0.15"))                      # ad spend per unit on an own listing, as share of price        # 12-month = 12 x monthly x this (price erosion, new rivals, seasonality)


def est_monthly_sales(rank, cat):
    if not rank:
        return None
    pts = SALES_BANDS.get((cat or "").lower().strip(), SALES_BANDS["other"])
    if rank <= pts[0][0]:
        return pts[0][1]
    for (r1, s1), (r2, s2) in zip(pts, pts[1:]):
        if rank <= r2:
            f = (math.log(rank) - math.log(r1)) / (math.log(r2) - math.log(r1))
            return int(round(math.exp(math.log(s1) + f * (math.log(s2) - math.log(s1)))))
    return 1


def offers_batch(c, asins):
    """getItemOffersBatch (20 ASINs per call, ~0.1 call/s): total sellers, FBA sellers, Amazon retail, Buy Box + lowest price, seller ids."""
    out = {}
    asins = sorted(set(a for a in asins if a))
    for i in range(0, len(asins), 20):
        chunk = asins[i:i + 20]
        body = {"requests": [{"uri": "/products/pricing/v0/items/%s/offers" % a, "method": "GET", "MarketplaceId": MK,
                              "ItemCondition": "New", "CustomerType": "Consumer"} for a in chunk]}
        try:
            r = spapi.call(c, "POST", "/batches/products/pricing/v0/itemOffers", body=body, quiet=True, tries=5)
            for x in r.get("responses") or []:
                b = x.get("body") or {}
                pl = b.get("payload") or {}
                a = pl.get("ASIN") or ((x.get("request") or {}).get("uri") or "").split("/items/")[-1].split("/")[0]
                if (x.get("status") or {}).get("statusCode") != 200 or not a:
                    continue
                sm = pl.get("Summary") or {}
                tot = sm.get("TotalOfferCount")
                if tot is None:
                    tot = sum(int(y.get("OfferCount") or 0) for y in sm.get("NumberOfOffers") or [] if (y.get("condition") or "new").lower() == "new")
                fba = sum(int(y.get("OfferCount") or 0) for y in sm.get("NumberOfOffers") or []
                          if y.get("fulfillmentChannel") == "Amazon" and (y.get("condition") or "new").lower() == "new")
                bb = None
                for y in sm.get("BuyBoxPrices") or []:
                    if (y.get("condition") or "New").lower() == "new":
                        bb = float(((y.get("LandedPrice") or y.get("ListingPrice") or {}).get("Amount")) or 0) or None
                low = None
                for y in sm.get("LowestPrices") or []:
                    if (y.get("condition") or "new").lower() == "new":
                        v = float(((y.get("LandedPrice") or y.get("ListingPrice") or {}).get("Amount")) or 0)
                        if v and (low is None or v < low):
                            low = v
                sellers = sorted({o.get("SellerId") for o in pl.get("Offers") or [] if o.get("SellerId")})
                out[a] = {"total": int(tot or 0), "fba": fba, "amazon_sells": "ATVPDKIKX0DER" in sellers, "bb": bb, "low": low, "sellers": sellers}
        except Exception as e:
            print("  offers ERR %s" % str(e)[:160])
        if (i // 20) % 10 == 9:
            print("  offers read: %d/%d listings" % (min(i + 20, len(asins)), len(asins)))
        time.sleep(10.5)
    return out


DP_MAX = int(os.environ.get("DP_MAX", "15"))        # public product pages per run (reviews, 'bought in past month'); ~2 MB each
REV_MIN = int(os.environ.get("REV_MIN", "5"))


def page_details(asins):
    """Public product page -> reviews, rating, 'bought in past month', availability (reprice/bb_web.parse_dp).
    Free GitHub runner IP first; the paid proxy (own port) only if Amazon answers with a captcha."""
    import bb_web, urllib.parse as up
    from curl_cffi import requests as cr
    out, mb, use_proxy, px = {}, 0.0, False, None
    raw = os.environ.get("PROXY_URL", "").strip()
    if raw:
        u = up.urlparse(raw); login = up.unquote(u.username or "")
        if "__" not in login:
            login += "__cr.us"
        px = "http://%s:%s@%s:%s" % (up.quote(login, safe=""), up.quote(up.unquote(u.password or ""), safe=""), u.hostname, os.environ.get("DP_PROXY_PORT", "10160"))
    for a in asins[:DP_MAX]:
        for attempt in (0, 1):
            prox = {"http": px, "https": px} if (use_proxy and px) else None
            try:
                r = cr.get("https://www.amazon.com/dp/%s" % a, impersonate="chrome", timeout=40, proxies=prox, headers={"Accept-Language": "en-US,en;q=0.9"})
                if use_proxy:
                    mb += len(r.content) / 1048576.0
                d = bb_web.parse_dp(r.text)
                inter = ("productTitle" not in r.text) and not d.get("captcha")
                if inter and attempt == 0:
                    print("  amazon page %s: no product body (%d KB, title %r)" % (a, len(r.content) // 1024, (re.search(r"<title>(.*?)</title>", r.text, re.S) or [None, ""])[1][:60]))
                    if not use_proxy and px:
                        use_proxy = True
                    time.sleep(4)
                    continue
                if d.get("captcha") or r.status_code != 200:
                    if not use_proxy and px:
                        use_proxy = True
                        print("  amazon page: runner IP got a captcha -> proxy for product pages")
                        continue
                    out[a] = {"err": "captcha/%s" % r.status_code}
                    break
                out[a] = {k: d.get(k) for k in ("reviews", "rating", "bought_month", "unavailable", "offers_n", "bb_price")}
                out[a]["page_kb"] = len(r.content) // 1024
                break
            except Exception as e:
                out[a] = {"err": str(e)[:80]}
                break
        time.sleep(3)
    print("  product pages read: %d (proxy MB: %.1f)" % (len(out), mb))
    return out


def fee_guess(price):
    return round(max(0.30, 0.15 * price) + (3.22 if price < 10 else 3.86), 2)   # referral + small/large-standard FBA guess


KW_PAGES = int(os.environ.get("KW_PAGES", "2"))          # Amazon catalog pages (20 each) per keyword - abandoned listings sit deep
STRONG_SIM = float(os.environ.get("STRONG_SIM", "0.55"))
SHARE_CAP = float(os.environ.get("SHARE_CAP", "0.15"))     # a new own listing never assumed above 15% of the market


def median(v):
    v = sorted(x for x in v if x)
    return v[len(v) // 2] if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", default="")
    ap.add_argument("--search", default="")
    ap.add_argument("--out", default="/tmp/deals")
    ap.add_argument("--source", default=os.environ.get("DEAL_SOURCE", "ali"), help="ali = AliExpress via Apify (no cooldowns), temu = paced Temu bridge, both")
    a = ap.parse_args()
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    temu, kws = [], []
    if a.from_json:
        d = json.load(open(a.from_json))
        for q, its in (d.get("searches") or {}).items():
            kws.append(("-", q))
            for it in its:
                it["kw"] = q; temu.append(it)
    if a.search and a.source in ("ali", "both"):
        import apify_source
        pairs = keyword_chunk(a.search) if a.search.startswith("chunk:") else [("-", x.strip()) for x in a.search.split("|") if x.strip()]
        cats = {q: cat for cat, q in pairs}
        print("AliExpress keywords (Apify): %d" % len(pairs))
        rows, _run = apify_source.ali_search([q for _, q in pairs], PER_KW)
        per = {}
        for it in rows:
            q = it.get("kw") or "-"
            per[q] = per.get(q, 0) + 1
            if per[q] > PER_KW:
                continue
            it["cat"] = cats.get(q, "-"); temu.append(it)
        kws += pairs
    if a.search and a.source in ("temu", "both"):
        import temu_bridge
        pairs = keyword_chunk(a.search) if a.search.startswith("chunk:") else [("-", x.strip()) for x in a.search.split("|") if x.strip()]
        print("Temu keywords: %d (%s)" % (len(pairs), ", ".join(k for _, k in pairs)))
        for cat, q in pairs:
            got = temu_bridge.search(q)[:PER_KW]
            for it in got:
                it["kw"] = q; it["cat"] = cat; temu.append(it)
            if (cat, q) not in kws:
                kws.append((cat, q))
            if temu_bridge.STATS.get("closed"):
                print("Temu blocked (%s) - continuing with what was pulled" % temu_bridge.STATS["closed"]); break
    seen, items = set(), []
    for it in temu:
        if it["goods_id"] in seen or not it.get("price") or it["price"] < 1.0 or it["price"] > MAX_TEMU or EXCLUDE.search(it.get("title") or ""):
            continue
        seen.add(it["goods_id"]); items.append(it)
    print("Temu items to check: %d generic (price <= $%.0f), keywords: %d" % (len(items), MAX_TEMU, len(kws)))

    # 1. Amazon catalog: every keyword (deep, for abandoned listings) + every Temu item (its own title search)
    pool, kw_asins, item_asins = {}, {}, {}
    for cat, q in kws:
        res = catalog_search(c, q, size=20, pages=KW_PAGES)
        kw_asins[q] = [x["asin"] for x in res]
        for x in res:
            pool.setdefault(x["asin"], x)
    for n, it in enumerate(items, 1):
        res = catalog_search(c, query_for(it["title"]), size=10, pages=1)
        item_asins[it["goods_id"]] = [x["asin"] for x in res]
        for x in res:
            pool.setdefault(x["asin"], x)
        if n % 50 == 0:
            print("  Amazon search: %d/%d Temu items, %d listings in pool" % (n, len(items), len(pool)))
    print("Amazon listings found: %d" % len(pool))

    # 2. live sellers for every listing in the pool
    offers = offers_batch(c, list(pool))
    for a_, x in pool.items():
        o = offers.get(a_) or {}
        x.update({"offers": o.get("total"), "fba_offers": o.get("fba"), "amazon_sells": o.get("amazon_sells"), "bb": o.get("bb"), "low": o.get("low"),
                  "sellers": o.get("sellers") or [], "est_sales": est_monthly_sales(x.get("rank"), x.get("rank_cat"))})

    # 3. per Temu item: the whole competing market (every matching listing, all their sellers)
    markets = []
    for it in items:
        cand = {a_ for a_ in item_asins.get(it["goods_id"], []) + kw_asins.get(it.get("kw"), [])}
        scored = []
        for a_ in cand:
            x = pool[a_]
            if BIG_BRANDS.match((x.get("brand") or "").strip()):
                continue
            sv = sim(it["title"], x["title"])
            if sv < SIM_MIN:
                continue
            scored.append([sv, a_])
        scored.sort(reverse=True)
        matches = []
        for sv, a_ in scored[:12]:                   # photo check on the 12 closest titles
            dist = img_dist(it.get("image"), pool[a_].get("image"))
            photo = dist is not None and dist <= IMG_OK
            if photo or sv >= STRONG_SIM:
                matches.append({"asin": a_, "sim": round(sv, 2), "img_dist": dist, "photo": photo})
        if not matches:
            continue
        act = [m for m in matches if (pool[m["asin"]].get("offers") or 0) > 0]
        aband = [m for m in matches if (pool[m["asin"]].get("offers") or 0) == 0 and pool[m["asin"]].get("offers") is not None]
        seller_listings = {}
        for m in act:
            for sid in pool[m["asin"]]["sellers"]:
                seller_listings[sid] = seller_listings.get(sid, 0) + 1
        price = median([pool[m["asin"]].get("bb") or pool[m["asin"]].get("low") for m in act]) or median([pool[m["asin"]].get("list_price") for m in matches])
        ref = max(act or matches, key=lambda m: pool[m["asin"]].get("est_sales") or 0)
        markets.append({"it": it, "matches": matches, "act": act, "aband": aband, "price": price, "ref": ref["asin"],
                        "listings": len(act), "sellers": len(seller_listings), "multi_listing_sellers": sum(1 for v in seller_listings.values() if v > 1),
                        "max_listings_one_seller": max(seller_listings.values()) if seller_listings else 0,
                        "market_sales": sum(pool[m["asin"]].get("est_sales") or 0 for m in act),
                        "amazon_sells": any(pool[m["asin"]].get("amazon_sells") for m in act),
                        "photo_matches": sum(1 for m in matches if m["photo"])})
    print("Temu items with a real Amazon market (photo or strong title match): %d" % len(markets))

    # 4. abandoned listings with demand: 0 sellers, has a sales rank -> product page for reviews / 'bought in past month'
    ab_all = [x for x in pool.values() if x.get("offers") == 0 and x.get("rank") and not BIG_BRANDS.match((x.get("brand") or "").strip())]
    ab_all.sort(key=lambda x: x["rank"])
    pages = page_details([x["asin"] for x in ab_all])
    for x in ab_all:
        x.update(pages.get(x["asin"]) or {})

    # 4b. reverse direction: abandoned listings with demand -> search Temu for their twin (paced, stops if Temu blocks)
    AB_TEMU_MAX = int(os.environ.get("AB_TEMU_MAX", "12"))
    hunt = [x for x in ab_all if (x.get("reviews") or 0) >= REV_MIN or (x.get("bought_month") or 0) > 0][:AB_TEMU_MAX]
    if hunt and os.environ.get("TEMU_REVERSE", "1") == "1" and a.source in ("temu", "both"):
        import temu_bridge
        for x in hunt:
            if temu_bridge.STATS.get("closed"):
                break
            res = [r for r in temu_bridge.search(query_for(x["title"])) if r.get("price")]
            best = None
            for r in res[:15]:
                sv = sim(r["title"], x["title"])
                if sv < 0.35:
                    continue
                dist = img_dist(r.get("image"), x.get("image"))
                ok = (dist is not None and dist <= IMG_OK) or sv >= STRONG_SIM
                if ok and (best is None or r["price"] < best[0]["price"]):
                    best = (r, sv, dist)
            if best:
                r, sv, dist = best
                r["kw"] = "reverse: " + x["asin"]
                items.append(r)                       # becomes the twin candidate below
                x["reverse_twin"] = {"title": r["title"][:90], "price": r["price"], "sim": round(sv, 2), "img_dist": dist, "url": r["url"]}
        print("  reverse search: %d abandoned listings searched on Temu, %d twins found" % (len(hunt), sum(1 for x in hunt if x.get("reverse_twin"))))

    # 5. fees (SP-API) at the market price / abandoned target price
    pairs = [(m["ref"], round(m["price"], 2)) for m in markets if m["price"]]
    for x in ab_all:
        x["fee_price"] = round(x.get("list_price") or x.get("bb_price") or 19.99, 2)
        pairs.append((x["asin"], x["fee_price"]))
    fees = fees_batch(c, sorted(set(pairs)))

    rows = []
    for m in markets:
        it, x = m["it"], pool[m["ref"]]
        cost = round(it["price"] * (1 + TAX) + INBOUND, 2)
        wf = WHOLESALE_F_ALI if it.get("source") == "aliexpress" else WHOLESALE_F
        wcost = round(it["price"] * wf + FREIGHT + INBOUND, 2)
        rec = {"kind": "MARKET", "source": it.get("source", "temu"), "source_sold": it.get("sold"), "source_rating": it.get("rating"), "cat": it.get("cat"), "kw": it.get("kw"), "risk_flag": (RISK.search(it["title"]) or [None])[0],
               "temu_title": it["title"][:120], "temu_price": it["price"], "landed_cost": cost, "wholesale_cost_est": wcost, "temu_url": it["url"], "temu_id": it["goods_id"],
               "match_conf": "PHOTO MATCH" if m["photo_matches"] else "TITLE MATCH", "photo_matches": m["photo_matches"],
               "listings": m["listings"], "abandoned_listings": len(m["aband"]), "sellers": m["sellers"], "multi_listing_sellers": m["multi_listing_sellers"],
               "max_listings_one_seller": m["max_listings_one_seller"], "amazon_sells": m["amazon_sells"], "market_sales_month": m["market_sales"],
               "amz_price": m["price"], "ref_asin": m["ref"], "ref_title": x["title"][:120], "ref_rank": x.get("rank"), "rank_cat": x.get("rank_cat"),
               "ref_url": "https://www.amazon.com/dp/" + m["ref"], "asins": " ".join(z["asin"] for z in m["matches"])}
        if m["price"]:
            fee = fees.get("%s@%.2f" % (m["ref"], round(m["price"], 2)))
            rec["fees_src"] = "spapi" if fee is not None else "guess"
            fee = fee if fee is not None else fee_guess(m["price"])
            rec["fees"] = round(fee, 2)
            pw, p = m["price"] - fee - wcost, m["price"] - fee - cost
            ppc = PPC_PCT * m["price"]
            share = min(SHARE_CAP, SHARE_HAIRCUT / (m["listings"] + 1)) if m["listings"] else 0
            if m["amazon_sells"]:
                share *= 0.5
            units = round(m["market_sales"] * share, 1)
            rec.update({"profit_wholesale": round(pw, 2), "roi_wholesale": round(pw / wcost, 2), "profit_temu": round(p, 2), "roi_temu": round(p / cost, 2),
                        "ppc_per_unit": round(ppc, 2), "profit_unit_after_ads": round(pw - ppc, 2), "your_share": round(share, 3), "your_units_month": units,
                        "profit_month": round(units * (pw - ppc), 0), "profit_12m": round(units * (pw - ppc) * 12 * YEAR_FACTOR, 0),
                        "capital_2months": round(units * 2 * wcost, 0)})
        rows.append(rec)
    abrows = []
    for x in ab_all:
        fee = fees.get("%s@%.2f" % (x["asin"], x["fee_price"]))
        fee = fee if fee is not None else fee_guess(x["fee_price"])
        best, bsv = None, 0.0               # cheapest Temu twin for the cost side
        if x.get("reverse_twin"):
            rt = x["reverse_twin"]
            best, bsv = {"title": rt["title"], "price": rt["price"], "image": None}, max(rt["sim"], STRONG_SIM)
        for it in ([] if best else items):
            sv = sim(it["title"], x["title"])
            if sv > bsv:
                best, bsv = it, sv
        rec = {"kind": "ABANDONED", "asin": x["asin"], "amz_title": x["title"][:120], "brand": x.get("brand"), "rank": x.get("rank"), "rank_cat": x.get("rank_cat"),
               "est_sales_month": x.get("est_sales"), "reviews": x.get("reviews"), "rating": x.get("rating"), "bought_month": x.get("bought_month"),
               "list_price": x.get("list_price"), "price_used": x["fee_price"], "fees": round(fee, 2), "url": "https://www.amazon.com/dp/" + x["asin"]}
        if best and bsv >= 0.45 and not x.get("reverse_twin"):
            dist = img_dist(best.get("image"), x.get("image"))
            if not ((dist is not None and dist <= IMG_OK) or bsv >= STRONG_SIM):
                best = None
        if best and bsv >= 0.45:
            wcost = round(best["price"] * WHOLESALE_F + FREIGHT + INBOUND, 2)
            pw = x["fee_price"] - fee - wcost
            units = x.get("bought_month") or x.get("est_sales") or 0
            if x.get("reverse_twin"):
                rec["temu_twin_url"] = x["reverse_twin"]["url"]; rec["temu_twin_photo_dist"] = x["reverse_twin"]["img_dist"]
            rec.update({"temu_twin": best["title"][:90], "temu_twin_price": best["price"], "temu_twin_sim": round(bsv, 2), "wholesale_cost_est": wcost,
                        "profit_unit": round(pw, 2), "roi_wholesale": round(pw / wcost, 2), "profit_month": round(units * pw, 0)})
        abrows.append(rec)

    rows.sort(key=lambda r: (-(r.get("profit_month") if r.get("profit_month") is not None else -1e9), -(r.get("roi_wholesale") or -9)))
    abrows.sort(key=lambda r: (-(r.get("reviews") or 0), r.get("rank") or 9e9))
    os.makedirs(a.out, exist_ok=True)
    tag = a.search.replace(":", "").replace("/", "of") if a.search.startswith("chunk:") else "latest"
    json.dump({"run_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ"), "markets": rows, "abandoned": abrows},
              open(os.path.join(a.out, "deals_%s.json" % tag), "w"), indent=1)
    for name, data in (("deals_%s.csv" % tag, rows), ("abandoned_%s.csv" % tag, abrows)):
        cols = []
        for r in data:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with open(os.path.join(a.out, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols or ["none"]); w.writeheader(); w.writerows(data)

    pos = [r for r in rows if (r.get("roi_wholesale") or -1) > 0]
    print("\nRESULT: %d generic Temu items -> %d with a real Amazon market, %d with positive ROI at est. wholesale; %d abandoned listings with a sales rank (%d with %d+ reviews)" % (
        len(items), len(rows), len(pos), len(abrows), sum(1 for r in abrows if (r.get("reviews") or 0) >= REV_MIN), REV_MIN))
    print("Assumptions: wholesale = Temu x %.2f + $%.2f freight/duties + $%.2f inbound; sales from BSR bands (+/-50%%); new own listing gets %.0f%% of an equal split of the market (max %.0f%%, half if Amazon sells); ads %.0f%% of price; 12 m = 12 x month x %.2f" % (
        WHOLESALE_F, FREIGHT, INBOUND, SHARE_HAIRCUT * 100, SHARE_CAP * 100, PPC_PCT * 100, YEAR_FACTOR))
    hdr = "  %-5s %7s %8s %7s %5s %4s %5s %-3s %6s %6s %6s %6s  %s"
    print("\nALL POSITIVE-ROI PRODUCTS (best projected monthly profit first):")
    print(hdr % ("match", "$/month", "$/12m", "mkt/m", "lists", "sell", "multi", "AMZ", "ROIw", "+$/u", "temu", "amz", "Temu item | best-selling Amazon listing"))
    for r in pos:
        print(hdr % (r["match_conf"][:5], r.get("profit_month"), r.get("profit_12m"), r["market_sales_month"], r["listings"], r["sellers"],
                     r["max_listings_one_seller"], "Y" if r["amazon_sells"] else "-", "%.0f%%" % (r["roi_wholesale"] * 100), r["profit_unit_after_ads"],
                     r["temu_price"], r["amz_price"], ("[%s] " % r["risk_flag"] if r.get("risk_flag") else "") + r["temu_title"][:38] + " | " + r["ref_title"][:38]))
    print("\nABANDONED LISTINGS (0 sellers) - most reviews first:")
    for r in abrows[:40]:
        print("  reviews %-6s rating %-4s bought/m %-6s rank %-8s est/m %-5s list $%-6s %s %s" % (
            r.get("reviews") if r.get("reviews") is not None else "?", r.get("rating") or "-", r.get("bought_month") or "-", r.get("rank"), r.get("est_sales_month") or "-",
            r.get("list_price") or "-", r["amz_title"][:60],
            ("| Temu twin $%s ROIw %.0f%% $%s/m" % (r["temu_twin_price"], r["roi_wholesale"] * 100, r["profit_month"])) if r.get("temu_twin") else ""))


if __name__ == "__main__":
    main()
