"""LAB (read only / validation preview only): what can the SP-API app do?  Nothing is changed in the seller account.
 - seller id (inferred from the offers, or SELLER_ID in credentials.env)
 - Listings Items: read own offer; PATCH with mode=VALIDATION_PREVIEW (validates, never applies)
 - Featured Offer Expected Price (what price wins the Buy Box)
 - how far back the order history / inventory ledger can be requested"""
import csv, json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amazon_feed as af
from lab_pricing import creds, OUT, HERE

c = creds()
env = {}
for ln in open(os.path.join(HERE, "credentials.env"), encoding="utf-8-sig"):
    if "=" in ln and not ln.startswith("#"):
        k, v = ln.rstrip("\r\n").split("=", 1); env[k.strip().upper()] = v.strip()
rows = list(csv.DictReader(open(os.path.join(OUT, "planning.tsv"), encoding="utf-8", errors="replace"), delimiter="\t"))
cs = json.load(open(os.path.join(OUT, "competitive_summary.json")))
seller = env.get("SELLER_ID", "").strip()
if not seller:
    votes = {}
    for r in rows:
        try:
            yp = float(r.get("your-price") or 0)
        except ValueError:
            continue
        b = (cs.get(r["asin"]) or {}).get("body") or {}
        for lo in b.get("lowestPricedOffers") or []:
            offs = [o for o in lo.get("offers") or [] if o.get("fulfillmentType") == "AFN"]
            if yp > 0 and len(offs) == 1 and abs(offs[0]["listingPrice"]["amount"] - yp) < 0.005:
                votes[offs[0]["sellerId"]] = votes.get(offs[0]["sellerId"], 0) + 1
    if votes:
        seller = max(votes, key=votes.get)
        print("seller id inferred from offers (votes):", {k: v for k, v in sorted(votes.items(), key=lambda x: -x[1])[:3]})
print("seller:", seller[:3] + "***" if seller else "UNKNOWN")
mk = af.MARKETPLACE
test_skus = [r["sku"] for r in rows if r["asin"] in ("B018C56968", "B017JIL4GY", "B00AA68KJC", "B0FKZKPLXK", "B018C5698G")]
print("test skus", test_skus)

def tryit(label, fn):
    try:
        r = fn(); print("OK  ", label); return r
    except Exception as e:
        print("FAIL", label, "->", str(e)[:300]); return None

ptype = None
for sku in test_skus[:1]:
    r = tryit("getListingsItem " + sku, lambda: af.api(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sku),
              params={"marketplaceIds": mk, "includedData": "summaries,offers,issues"}))
    if r:
        s0 = (r.get("summaries") or [{}])[0]
        ptype = s0.get("productType")
        print("   status", s0.get("status"), "productType", ptype, "offers", json.dumps(r.get("offers"))[:300], "issues", len(r.get("issues") or []))
        price = None
        for o in r.get("offers") or []:
            try: price = float((o.get("price") or {}).get("amount"))
            except Exception: pass
        if ptype and price:
            body = {"productType": ptype, "patches": [{"op": "replace", "path": "/attributes/purchasable_offer",
                    "value": [{"marketplace_id": mk, "currency": "USD", "our_price": [{"schedule": [{"value_with_tax": price}]}]}]}]}
            tryit("PATCH VALIDATION_PREVIEW same price %.2f" % price, lambda: print("   ->", json.dumps(
                af.api(c, "PATCH", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params={"marketplaceIds": mk, "mode": "VALIDATION_PREVIEW"}, body=body))[:500]))
body = {"requests": [{"uri": "/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", "method": "GET", "marketplaceId": mk, "sku": s} for s in test_skus]}
r = tryit("featuredOfferExpectedPrice batch", lambda: af.api(c, "POST", "/batches/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", body=body))
if r:
    for x in r.get("responses", []):
        print("   ", (x.get("request") or {}).get("sku"), (x.get("status") or {}).get("statusCode"), json.dumps(x.get("body"))[:400])
# history depth
end = dt.datetime.utcnow().replace(microsecond=0) - dt.timedelta(minutes=10)
def rep(rtype, days_back, span, opts=None):
    st = end - dt.timedelta(days=days_back)
    b = {"reportType": rtype, "marketplaceIds": [mk], "dataStartTime": st.isoformat() + "Z", "dataEndTime": (st + dt.timedelta(days=span)).isoformat() + "Z"}
    if opts: b["reportOptions"] = opts
    rid = af.api(c, "POST", "/reports/2021-06-30/reports", body=b)["reportId"]
    for _ in range(40):
        x = af.api(c, "GET", "/reports/2021-06-30/reports/" + rid)
        if x.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"):
            return x
        time.sleep(15)
    return {"processingStatus": "TIMEOUT"}
for back in (365, 700):
    x = tryit("orders report %d days ago" % back, lambda: rep(af.ORDERS_TYPE, back, 20))
    if x: print("   ", back, "days back ->", x.get("processingStatus"))
x = tryit("ledger summary (daily, by ASIN) 20 days", lambda: rep("GET_LEDGER_SUMMARY_VIEW_DATA", 40, 20, {"aggregateByLocation": "COUNTRY", "aggregatedByTimePeriod": "DAILY"}))
if x:
    print("   ledger ->", x.get("processingStatus"))
    if x.get("reportDocumentId"):
        txt = af.decode(af.download(c, x["reportDocumentId"])).splitlines()
        print("   ledger rows", len(txt), "|", txt[0][:300] if txt else "")
