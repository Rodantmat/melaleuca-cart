"""Read-only probe: what can Amazon tell us about WHO owns the Buy Box and how much traffic/conversion we get?"""
import json, os, sys, datetime as dt
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE)
MK = spapi.MARKETPLACE
OUT = "/tmp/so"; os.makedirs(OUT, exist_ok=True)
ASINS = "B01JKSBEKC,B001TNTWC4,B0030JJNBK,B00AOW2M3M,B07MWDCFRZ,B017RW4LTE".split(",")

print("== 1. competitiveSummary raw (featuredBuyingOptions)")
body = {"requests": [{"asin": a, "marketplaceId": MK, "includedData": ["featuredBuyingOptions", "lowestPricedOffers", "referencePrices"],
                      "lowestPricedOffersInputs": [{"itemCondition": "New", "offerType": "Consumer"}],
                      "method": "GET", "uri": "/products/pricing/2022-05-01/items/competitiveSummary"} for a in ASINS]}
try:
    r = spapi.call(c, "POST", "/batches/products/pricing/2022-05-01/items/competitiveSummary", body=body, quiet=True)
    json.dump(r, open(OUT + "/competitive_raw.json", "w"), indent=1)
    x = r["responses"][0]; print(json.dumps(x)[:2500])
except Exception as e:
    print("ERR", str(e)[:400])

print("== 2. getItemOffers v0 (IsBuyBoxWinner, feedback, shipping time)")
for a in ASINS[:3]:
    try:
        r = spapi.call(c, "GET", "/products/pricing/v0/items/%s/offers" % a, params={"MarketplaceId": MK, "ItemCondition": "New", "CustomerType": "Consumer"}, quiet=True, tries=3)
        json.dump(r, open(OUT + "/offers_v0_%s.json" % a, "w"), indent=1)
        offs = (r.get("payload") or {}).get("Offers") or []
        print(a, "offers", len(offs)); print(json.dumps(offs[:3])[:1500])
    except Exception as e:
        print("ERR", a, str(e)[:300])

print("== 3. Sales and Traffic report (Buy Box %, sessions, conversion) per child ASIN per day")
end = dt.date.today() - dt.timedelta(days=1)
start = end - dt.timedelta(days=59)
for rt, opts in (("GET_SALES_AND_TRAFFIC_REPORT", {"dateGranularity": "DAY", "asinGranularity": "CHILD"}),):
    st, txt = spapi.report(c, rt, start.isoformat() + "T00:00:00Z", end.isoformat() + "T23:59:59Z", opts, wait_minutes=20)
    print(rt, st, len(txt))
    if txt:
        open(OUT + "/sales_traffic.json", "w").write(txt)
        try:
            j = json.loads(txt)
            print("keys", list(j.keys()))
            sba = j.get("salesAndTrafficByAsin") or []
            print("asin rows", len(sba)); print(json.dumps(sba[:1])[:1500])
            print(json.dumps((j.get("salesAndTrafficByDate") or [])[:1])[:800])
        except Exception as e:
            print("parse", e, txt[:500])
