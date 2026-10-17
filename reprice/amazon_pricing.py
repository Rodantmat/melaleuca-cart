"""
Live Buy Box ("featured offer") prices for the Amazon feed.

Why: the profit of a product is what it REALLY sells for, which is the Buy Box price - not the price you typed on your own offer.
(Your own offer can be $13.39 while the Buy Box is $8.95: the profit on the $13.39 is a false profit - nobody buys at it.)

Source: Selling Partner API  Product Pricing v2022-05-01  getCompetitiveSummary (batch of 20 ASINs, 1 call per 30 s):
    featuredBuyingOptions -> who owns the Buy Box, at what price, for which customer segment and how much of the product-page traffic that segment is
    lowestPricedOffers    -> the cheapest new offers (price, fulfilment FBA/FBM)
Pure functions (no network) are at the top so they can be tested offline.
"""
import json, os, time

MARKETPLACE = "ATVPDKIKX0DER"


def _amt(x):
    try:
        return float((x or {}).get("amount"))
    except (TypeError, ValueError):
        return None


def _landed(offer):
    p = _amt(offer.get("listingPrice"))
    if p is None:
        return None
    ship = 0.0
    for s in offer.get("shippingOptions") or []:
        if s.get("shippingOptionType") == "DEFAULT":
            ship += _amt(s.get("price")) or 0.0
    return p + ship


def summarize(body):
    """body of one getCompetitiveSummary response -> dict of the numbers the planner needs"""
    out = {"bb": None, "bb_top": None, "bb_fba": None, "low_new": None, "low_afn": None, "n_offers": 0, "n_afn": 0}
    sw = w = 0.0
    top_w = -1.0
    for fo in (body or {}).get("featuredBuyingOptions") or []:
        if fo.get("buyingOptionType") not in (None, "New"):
            continue
        for seg in fo.get("segmentedFeaturedOffers") or []:
            p = _landed(seg)
            if p is None:
                continue
            wt = sum(float((s.get("segmentDetails") or {}).get("glanceViewWeightPercentage") or 0) for s in seg.get("featuredOfferSegments") or [])
            if wt <= 0:
                wt = 1.0
            sw += p * wt
            w += wt
            if wt > top_w:
                top_w, out["bb_top"] = wt, p
            if seg.get("fulfillmentType") == "AFN" and (out["bb_fba"] is None or p < out["bb_fba"]):
                out["bb_fba"] = p
    if w > 0:
        out["bb"] = round(sw / w, 2)           # Buy Box price weighted by how much of the traffic each featured offer gets
    for lo in (body or {}).get("lowestPricedOffers") or []:
        for o in lo.get("offers") or []:
            if o.get("condition") not in (None, "New"):
                continue
            p = _landed(o)
            if p is None:
                continue
            out["n_offers"] += 1
            if out["low_new"] is None or p < out["low_new"]:
                out["low_new"] = p
            if o.get("fulfillmentType") == "AFN":
                out["n_afn"] += 1
                if out["low_afn"] is None or p < out["low_afn"]:
                    out["low_afn"] = p
    return out


def effective_price(live, plan_fo, real30, own, undercut_pct=3.0, sold_haircut=0.97, q30=0):
    """The price the profit is calculated on.   Returns (price or None, source, flag)
        1. live Buy Box (weighted)            -> 'live'
        2. Buy Box of the planning report     -> 'planning'   (used when the live call has nothing for the ASIN / is not available)
        3. what it really sold for last 30 d  -> 'sold'       (x0.97)
        4. nothing                            -> None, 'none' (no price evidence: the product gets no profit, it is not bought)
       Then: if an FBA competitor sells cheaper than that price by more than undercut_pct %, the price used is halfway between
       (the Buy Box will move to them: price erosion), flag 'undercut'.   If your own offer is cheaper than the price, your price is used."""
    base, src = None, "none"
    if live and live.get("bb"):
        base, src = live["bb"], "live"
    elif plan_fo:
        base, src = plan_fo, "planning"
    elif real30:
        base, src = round(real30 * sold_haircut, 2), "sold"
    if base is None:
        return None, "none", "no price"
    flag = ""
    # your own recent sales are proof that customers also pay more than the Buy Box (your own offer wins part of the time):
    # blend toward the price you really sold at, with a weight that grows with the units sold in 30 days (3 units 18%, 10+ units 60%, never above 60%)
    if src != "sold" and real30 and q30 >= 3 and real30 > base:
        w = min(0.6, 0.06 * q30)
        base = round(base + w * (min(real30, own or real30) - base), 2)
        flag = "sold-blend %d%%" % round(w * 100)
    low_afn = (live or {}).get("low_afn")
    if low_afn and low_afn < base * (1 - undercut_pct / 100.0):
        base, flag = round((base + low_afn) / 2.0, 2), (flag + " undercut").strip()
    if own and 0 < own < base:
        base, flag = round(own, 2), (flag + " own price lower").strip()
    if plan_fo and live and live.get("bb") and abs(live["bb"] - plan_fo) / plan_fo > 0.05:
        flag = (flag + " live vs report >5%").strip()
    return base, src, flag


def fetch(api, creds, asins, log=print, pause=31):
    """api = amazon_feed.api.  Returns {asin: summary}.  One batch of 20 per ~31 s (the API allows 0.033 requests / second)."""
    out = {}
    asins = sorted({a for a in asins if a})
    for i in range(0, len(asins), 20):
        chunk = asins[i:i + 20]
        body = {"requests": [{"asin": a, "marketplaceId": MARKETPLACE,
                              "includedData": ["featuredBuyingOptions", "lowestPricedOffers"],
                              "lowestPricedOffersInputs": [{"itemCondition": "New", "offerType": "Consumer"}],
                              "method": "GET", "uri": "/products/pricing/2022-05-01/items/competitiveSummary"} for a in chunk]}
        r = api(creds, "POST", "/batches/products/pricing/2022-05-01/items/competitiveSummary", body=body)
        for x in r.get("responses", []):
            b = x.get("body") or {}
            a = b.get("asin") or (x.get("request") or {}).get("asin")
            if a and (x.get("status") or {}).get("statusCode") == 200:
                out[a] = summarize(b)
        log("  live Buy Box prices: %d of %d ASINs read" % (min(i + 20, len(asins)), len(asins)))
        if i + 20 < len(asins):
            time.sleep(pause)
    return out


def save(path, data):
    json.dump({"ts": time.time(), "asins": data}, open(path, "w"))


def load(path, max_age_hours=36):
    try:
        j = json.load(open(path))
    except Exception:
        return None, None
    age = (time.time() - j.get("ts", 0)) / 3600.0
    return (j.get("asins") if age <= max_age_hours else None), age
