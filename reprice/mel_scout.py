"""READ-ONLY scout: for every Melaleuca catalog card, find the Amazon listings we do not sell yet and read rank, offers, price, fees and restrictions. Prints one JSON line per ASIN."""
import os, sys, json, re, time, csv, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
cards = [x for x in json.load(open(os.path.join(HERE, "scout_cards.json"))) if not x["sup"]]
part, parts = int(sys.argv[1]), int(sys.argv[2])
cards = [x for i, x in enumerate(cards) if i % parts == part]
ours = {r["asin"] for r in csv.DictReader(open(os.path.join(HERE, "costs.tsv")), delimiter="\t") if r.get("asin")}
TOK = ["sei bella", "seibella", "ecosense", "renew", "sun valley", "koala", "affinia", "alloy", "riverbend", "mountain cabin", "sol-u", "mela", "t36", "pure", "revive", "clear defense", "sun shades", "exceed", "body satin", "dermatin", "dermacort", "clean & gleam", "rustic touch", "splash", "gold bar", "delectables", "r3"]
def clean(t): return re.sub(r"\s+", " ", re.sub(r"[®™:]", " ", t)).strip()
seen = {}
for cd in cards:
    t = clean(cd["title"]); tl = t.lower()
    toks = [k for k in TOK if k in tl]
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items", params={"marketplaceIds": MP, "keywords": ("" if "melaleuca" in tl else "Melaleuca ") + t, "includedData": "summaries,salesRanks", "pageSize": 20}, tries=6, quiet=True)
    except spapi.SpError as e:
        print("SCOUT_ERR search", cd["id"], str(e)[:120]); continue
    time.sleep(0.55); n = 0
    for it in r.get("items", []):
        s = (it.get("summaries") or [{}])[0]; nm = (s.get("itemName") or ""); nl = nm.lower()
        bm = ((s.get("brand") or "") + " " + (s.get("manufacturer") or "")).lower()
        if not ("melaleuca" in bm or "melaleuca" in nl or any(k in nl for k in toks) or any(k in bm for k in toks)): continue
        a = it["asin"]
        if a in seen: seen[a]["cards"].append(cd["id"]); continue
        rk = None; top = None
        for sr in it.get("salesRanks", []):
            for x in (sr.get("classificationRanks") or []):
                if rk is None or x.get("rank", 9e9) < rk[0]: rk = (x.get("rank"), x.get("title"))
            for x in (sr.get("displayGroupRanks") or []):
                if top is None or x.get("rank", 9e9) < top[0]: top = (x.get("rank"), x.get("title"))
        seen[a] = {"asin": a, "name": nm[:160], "brand": s.get("brand"), "mfr": s.get("manufacturer"), "rank": rk, "top": top, "cards": [cd["id"]], "ours": a in ours}
        n += 1
    print("SCOUT_CARD", json.dumps({"id": cd["id"], "title": cd["title"], "cost": cd["cost"], "hits": n, "total": r.get("numberOfResults")}))
    sys.stdout.flush()
OKB = ("melaleuca", "generic", "sei bella", "ecosense", "renew", "sun valley", "koala", "affinia", "alloy", "riverbend", "pure", "vitality", "sun shades", "exceed")
def relevant(d):
    b = (d.get("brand") or "").lower(); m = (d.get("mfr") or "").lower()
    return (not b) or any(k in b for k in OKB) or "melaleuca" in m
todo = [a for a, d in seen.items() if not d["ours"] and relevant(d)]
for a, d in seen.items():
    if d["ours"] or a not in todo: d["skip"] = "ours" if d["ours"] else "other-brand"; print("SCOUT_ASIN", json.dumps(d))
def take(d, o):
    sm = o.get("Summary", {})
    d["offers"] = sm.get("TotalOfferCount")
    d["by"] = {x.get("fulfillmentChannel"): x.get("OfferCount") for x in sm.get("NumberOfOffers", []) if x.get("condition", "").lower() == "new"}
    bb = [x for x in sm.get("BuyBoxPrices", []) if x.get("condition", "").lower() == "new"]
    lo = sorted(v for v in (x.get("LandedPrice", {}).get("Amount") for x in sm.get("LowestPrices", []) if x.get("condition", "").lower() == "new") if v)
    d["bb"] = bb[0].get("LandedPrice", {}).get("Amount") if bb else None
    d["low"] = lo[0] if lo else None
    d["list"] = (sm.get("ListPrice") or {}).get("Amount")
    d["sellers"] = [{"fba": x.get("IsFulfilledByAmazon"), "p": round((x.get("ListingPrice", {}).get("Amount") or 0) + (x.get("Shipping", {}).get("Amount") or 0), 2), "bb": x.get("IsBuyBoxWinner"), "fb": (x.get("SellerFeedbackRating") or {}).get("FeedbackCount")} for x in o.get("Offers", [])[:10]]
for i in range(0, len(todo), 20):
    chunk = todo[i:i + 20]
    try:
        r = spapi.call(c, "POST", "/batches/products/pricing/v0/itemOffers", body={"requests": [{"uri": "/products/pricing/v0/items/%s/offers" % a, "method": "GET", "MarketplaceId": MP, "ItemCondition": "New"} for a in chunk]}, tries=7, quiet=True)
        for x in r.get("responses", []):
            a = (x.get("request") or {}).get("Asin") or ((x.get("body") or {}).get("payload") or {}).get("ASIN")
            if a in seen and (x.get("status") or {}).get("statusCode") == 200: take(seen[a], (x.get("body") or {}).get("payload") or {})
            elif a in seen: seen[a]["offers_err"] = json.dumps(x.get("status"))[:80]
    except spapi.SpError as e:
        for a in chunk: seen[a]["offers_err"] = str(e)[:100]
    time.sleep(10.5)
    print("SCOUT_PROGRESS offers", i + len(chunk), len(todo)); sys.stdout.flush()
for n, a in enumerate(todo):
    d = seen[a]; price = d.get("bb") or d.get("low")
    if price:
        try:
            f = spapi.call(c, "POST", "/products/fees/v0/items/%s/feesEstimate" % a, body={"FeesEstimateRequest": {"MarketplaceId": MP, "IsAmazonFulfilled": True, "Identifier": a, "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": price}}}}, tries=5, quiet=True)
            fr = f.get("payload", {}).get("FeesEstimateResult", {})
            d["fees"] = (fr.get("FeesEstimate") or {}).get("TotalFeesEstimate", {}).get("Amount")
            if d["fees"] is None: d["fees_err"] = json.dumps(fr.get("Error"))[:120]
        except spapi.SpError as e: d["fees_err"] = str(e)[:100]
        time.sleep(1.05)
    try:
        rs = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params={"asin": a, "sellerId": seller, "marketplaceIds": MP, "conditionType": "new_new", "reasonLocale": "en_US"}, tries=5, quiet=True)
        d["restr"] = [x.get("reasonCode") for y in rs.get("restrictions", []) for x in y.get("reasons", [])]
    except spapi.SpError as e: d["restr_err"] = str(e)[:100]
    time.sleep(0.25)
    print("SCOUT_ASIN", json.dumps(d)); sys.stdout.flush()
print("SCOUT_DONE", part, len(cards), len(seen))
