"""READ-ONLY: status of published AlphaDog listings (getListingsItem). Prints status/issue counts only."""
import json, os, urllib.request, collections
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
feed = json.loads(urllib.request.urlopen((os.environ.get("AMZ_FEED_URL") or V.FEED) + "?x=%d" % os.getpid(), timeout=120).read().decode())
F = [f for f in feed if f["id"] == os.environ.get("AMZ_ONLY", "amazon-tee-01")][0]
skus = os.environ["AMZ_SKUS"].split(",") if os.environ.get("AMZ_SKUS") else [F["parent_sku"]] + [F["children"][i]["sku"] for i in (0, 1, 5, 100, 330, -1) if abs(i) < len(F["children"])]
if os.environ.get("AMZ_PROBE"):
    import concurrent.futures as cf
    urls = sorted({u for k in F["children"] for u in [k["img"]] + list(k.get("others") or [])})
    def chk(u):
        try:
            r = urllib.request.urlopen(urllib.request.Request("https://alphadogstyles.com/mk/" + u, headers={"User-Agent": "Mozilla/5.0"}), timeout=40)
            return u, (r.status == 200 and "image" in r.headers.get("content-type", ""))
        except Exception as e: return u, False
    bad = [u for u, ok in cf.ThreadPoolExecutor(16).map(chk, urls) if not ok]
    print("PROBE urls", len(urls), "unreachable", len(bad))
    for u in bad[:40]: print("PROBE BAD", u)
for sk in skus:
    try:
        r = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sk), params={"marketplaceIds": spapi.MARKETPLACE, "includedData": "summaries,issues,attributes,fulfillmentAvailability,offers,relationships,productTypes"})
        s = (r.get("summaries") or [{}])[0]
        iss = collections.Counter((i.get("severity"), i.get("code")) for i in r.get("issues", []))
        print(sk, "| status", s.get("status"), "| asin", s.get("asin"), "| issues", dict(iss))
        print("    fulfillmentAvailability:", r.get("fulfillmentAvailability"), "| offers:", json.dumps(r.get("offers"))[:200], "| attr.fa:", json.dumps((r.get("attributes") or {}).get("fulfillment_availability"))[:200])
        print("    relationships:", json.dumps(r.get("relationships"))[:260], "| ptype:", json.dumps(r.get("productTypes"))[:80])
        at = r.get("attributes") or {}
        print("    purchasable_offer:", json.dumps(at.get("purchasable_offer"))[:300])
        print("    media:", [ (k, (v[0] or {}).get("media_location","")[-40:]) for k, v in at.items() if "image_locator" in k])
        if os.environ.get("AMZ_SKUS"):
            for k, v in sorted(at.items()):
                if "image_locator" in k: print("    IMG", k, (v[0] or {}).get("media_location",""))
        for i in r.get("issues", [])[:3]: print("    ", i.get("severity"), i.get("code"), (i.get("message") or "")[:160])
    except spapi.SpError as e: print(sk, "ERR", str(e)[:150])
