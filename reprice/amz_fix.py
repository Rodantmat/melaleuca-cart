"""PATCH AlphaDog pilot children (SKUs from the feed only): (a) delete leftover gallery slots other_product_image_locator_N that this feed does not set,
(b) optionally re-send fulfillment_availability. env AMZ_FEED_URL, AMZ_ONLY, AMZ_FIX_LIMIT (children, 0=all), AMZ_FIX_FA=1. Prints counts only."""
import json, os, re, urllib.request, collections
from concurrent.futures import ThreadPoolExecutor
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
feed = json.loads(urllib.request.urlopen(os.environ["AMZ_FEED_URL"] + "?x=%d" % os.getpid(), timeout=120).read().decode())
F = [f for f in feed if f["id"] == os.environ["AMZ_ONLY"]][0]
kids = F["children"][: int(os.environ.get("AMZ_FIX_LIMIT", "0")) or None]
FA = os.environ.get("AMZ_FIX_FA") == "1"
stat = collections.Counter(); msgs = collections.Counter()
def fix(k):
    sku = k["sku"]; assert re.match(r"^[A-Z]-[A-Z]{2}-\d-[A-Z]{2}(-\w+)?$", sku), sku     # AlphaDog SKUs only
    keep = 1 + len(k.get("others") or [])
    ops = [{"op": "delete", "path": "/attributes/other_product_image_locator_%d" % n, "value": [{"marketplace_id": MP}]} for n in range(keep, 9)]
    if FA: ops.append({"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": 999, "lead_time_to_ship_max_days": V.LEAD[F["prod"]]}]})
    try:
        r = spapi.call(c, "PATCH", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params={"marketplaceIds": MP, "issueLocale": "en_US"}, body={"productType": F["ptype"], "patches": ops})
        for i in r.get("issues", []): msgs[(i.get("severity"), i.get("code"), (i.get("message") or "")[:160])] += 1
        return r.get("status", "?")
    except spapi.SpError as e: return "ERR " + str(e)[:100]
with ThreadPoolExecutor(4) as ex: res = list(ex.map(fix, kids))
print("patched", len(kids), dict(collections.Counter(res)))
for k, v in msgs.most_common(8): print("  ", k, v)
