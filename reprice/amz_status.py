"""READ-ONLY: status of published AlphaDog listings (getListingsItem). Prints status/issue counts only."""
import json, os, urllib.request, collections
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
feed = json.loads(urllib.request.urlopen(V.FEED, timeout=120).read().decode())
F = [f for f in feed if f["id"] == os.environ.get("AMZ_ONLY", "amazon-tee-01")][0]
skus = [F["parent_sku"]] + [F["children"][i]["sku"] for i in (0, 1, 100, 300, -1)]
for sk in skus:
    try:
        r = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sk), params={"marketplaceIds": spapi.MARKETPLACE, "includedData": "summaries,issues,attributes,fulfillmentAvailability,offers"})
        s = (r.get("summaries") or [{}])[0]
        iss = collections.Counter((i.get("severity"), i.get("code")) for i in r.get("issues", []))
        print(sk, "| status", s.get("status"), "| asin", s.get("asin"), "| issues", dict(iss))
        print("    fulfillmentAvailability:", r.get("fulfillmentAvailability"), "| offers:", json.dumps(r.get("offers"))[:200], "| attr.fa:", json.dumps((r.get("attributes") or {}).get("fulfillment_availability"))[:200])
        at = r.get("attributes") or {}
        print("    media:", [ (k, (v[0] or {}).get("media_location","")[-40:]) for k, v in at.items() if "image_locator" in k])
        for i in r.get("issues", [])[:3]: print("    ", i.get("severity"), i.get("code"), (i.get("message") or "")[:160])
    except spapi.SpError as e: print(sk, "ERR", str(e)[:150])
