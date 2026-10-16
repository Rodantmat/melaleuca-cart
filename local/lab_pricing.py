"""LAB (read only): which Amazon pricing source gives the real Buy Box ("featured offer") price?
 1. getCompetitiveSummary (live featured offer + lowest offers + reference prices) for every ASIN of the planning report
 2. getFeaturedOfferExpectedPriceBatch for every SKU (price needed to win the Buy Box)
 3. compares them with the planning report (featuredoffer-price / your-price) and prints the gap
Nothing is changed in the seller account."""
import csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amazon_feed as af

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "feed", "amz"); os.makedirs(OUT, exist_ok=True)


def creds():
    d = {}
    for ln in open(os.path.join(HERE, "credentials.env"), encoding="utf-8-sig"):
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.rstrip("\r\n").split("=", 1); d[k.strip().upper()] = v.strip().strip('"').strip("'")
    return {k: d[k] for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN")}


def money(x):
    try:
        return float((x or {}).get("amount"))
    except Exception:
        return None


def main():
    c = creds()
    rows = list(csv.DictReader(open(os.path.join(OUT, "planning.tsv"), encoding="utf-8", errors="replace"), delimiter="\t"))
    only = [a for a in sys.argv[1:] if a.startswith("B0")]
    asins = sorted({r["asin"] for r in rows if r["asin"]})
    if only:
        asins = [a for a in asins if a in only]
    print("ASINs:", len(asins), "| SKUs:", len(rows))
    mk = af.MARKETPLACE
    cs = {}
    for i in range(0, len(asins), 20):
        chunk = asins[i:i + 20]
        body = {"requests": [{"asin": a, "marketplaceId": mk, "includedData": ["featuredBuyingOptions", "lowestPricedOffers", "referencePrices"],
                              "lowestPricedOffersInputs": [{"itemCondition": "New", "offerType": "Consumer"}],
                              "method": "GET", "uri": "/products/pricing/2022-05-01/items/competitiveSummary"} for a in chunk]}
        try:
            r = af.api(c, "POST", "/batches/products/pricing/2022-05-01/items/competitiveSummary", body=body)
        except Exception as e:
            print("competitiveSummary FAILED:", str(e)[:400]); break
        for x in r.get("responses", []):
            b = x.get("body") or {}
            a = b.get("asin") or ((x.get("request") or {}).get("asin"))
            cs[a] = {"status": (x.get("status") or {}).get("statusCode"), "body": b}
        print("  batch %d/%d done" % (i // 20 + 1, (len(asins) + 19) // 20)); sys.stdout.flush()
        time.sleep(31)
    json.dump(cs, open(os.path.join(OUT, "competitive_summary.json"), "w"))
    foep = {}
    skus = [r["sku"] for r in rows if r["sku"]]
    for i in range(0, len(skus), 40):
        chunk = skus[i:i + 40]
        body = {"requests": [{"uri": "/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", "method": "POST", "marketplaceId": mk, "sku": s} for s in chunk]}
        try:
            r = af.api(c, "POST", "/batches/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", body=body)
        except Exception as e:
            print("FOEP FAILED:", str(e)[:400]); break
        for x in r.get("responses", []):
            req = x.get("request") or {}
            foep[req.get("sku") or (x.get("body") or {}).get("sku")] = x
        print("  foep batch done"); sys.stdout.flush()
        time.sleep(31)
    json.dump(foep, open(os.path.join(OUT, "foep.json"), "w"))
    # ---- compare
    by_asin = {}
    for r in rows:
        by_asin.setdefault(r["asin"], []).append(r)
    print("\nASIN | name | planning featured | your-price | LIVE buy box | lowest new | FOEP | units30")
    big = 0; nobb = 0
    for a in asins:
        rs = by_asin[a]; r0 = rs[0]
        b = (cs.get(a) or {}).get("body") or {}
        bb = None; seller = ""
        for fo in b.get("featuredBuyingOptions") or []:
            for seg in fo.get("segmentedFeaturedOffers") or []:
                p = money(seg.get("listingPrice"))
                ship = sum(money(s.get("price")) or 0 for s in (seg.get("shippingOptions") or []) if s.get("shippingOptionType") == "DEFAULT")
                if p is not None and bb is None:
                    bb = p + ship; seller = seg.get("sellerId")
        low = None
        for lo in b.get("lowestPricedOffers") or []:
            for o in lo.get("offers") or []:
                p = money(o.get("listingPrice"))
                if p is not None and (low is None or p < low):
                    low = p
        fp = None
        for r in rs:
            x = foep.get(r["sku"]) or {}
            fb = x.get("body") or {}
            for res in fb.get("featuredOfferExpectedPriceResults") or []:
                v = money((res.get("featuredOfferExpectedPrice") or {}).get("listingPrice"))
                if v is not None: fp = v
        pf = float(r0.get("featuredoffer-price") or 0) or None
        yp = float(r0.get("your-price") or 0) or None
        if bb is None: nobb += 1
        if bb and pf and abs(bb - pf) / pf > 0.05: big += 1
        print("%s | %s | %s | %s | %s | %s | %s | %s" % (a, r0["product-name"][:32], pf, yp, bb, low, fp, r0.get("units-shipped-t30")))
    print("\nASINs with no live buy box:", nobb, "| live buy box differs >5%% from planning report: %d of %d" % (big, len(asins)))


if __name__ == "__main__":
    main()
