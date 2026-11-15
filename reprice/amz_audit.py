"""READ-ONLY audit of every child of a published pilot listing: status, issues, offer/quantity, image slots. Prints a summary + the failing SKUs. No credentials printed."""
import json, os, urllib.request, collections
from concurrent.futures import ThreadPoolExecutor
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
feed = json.loads(urllib.request.urlopen((os.environ.get("AMZ_FEED_URL") or V.FEED) + "?x=%d" % os.getpid(), timeout=120).read().decode())
F = [f for f in feed if f["id"] == os.environ.get("AMZ_ONLY", "pilot-tee-1")][0]
def chk(k):
    try:
        r = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, k["sku"]), params={"marketplaceIds": spapi.MARKETPLACE, "includedData": "summaries,issues,attributes,fulfillmentAvailability,offers"}, tries=5)
    except spapi.SpError as e: return k, ["HTTP " + str(e)[:60]], {}
    s = (r.get("summaries") or [{}])[0]; at = r.get("attributes") or {}; prob = []
    st = s.get("status") or []
    if "BUYABLE" not in st: prob.append("not-buyable")
    fa = r.get("fulfillmentAvailability") or []
    if not fa or not (fa[0].get("quantity") or 0) > 0: prob.append("qty0")
    if not r.get("offers"): prob.append("no-offer")
    errs = [i.get("code") for i in r.get("issues", []) if i.get("severity") == "ERROR"]
    if errs: prob.append("issues:" + ",".join(sorted(set(errs))))
    oth = [kk for kk in at if kk.startswith("other_product_image_locator_")]
    if len(oth) < len(k.get("others") or []): prob.append("images %d/%d" % (len(oth), len(k.get("others") or [])))
    if "main_product_image_locator" not in at: prob.append("no-main")
    return k, prob, {"asin": s.get("asin")}
bad = collections.defaultdict(list); n = 0; kinds = collections.Counter()
with ThreadPoolExecutor(5) as ex:
    for k, prob, info in ex.map(chk, F["children"]):
        n += 1
        for p in prob: kinds[p.split(":")[0].split(" ")[0]] += 1
        if prob: bad[(k["breed"], k["cc"])].append((k["size"], prob))
print("AUDIT children", n, "with problems", sum(len(v) for v in bad.values()), "| breed-colors affected", len(bad), "| kinds", dict(kinds))
for (b, cc), v in sorted(bad.items())[:150]: print("AUDIT BAD", b, cc, "sizes", len(v), v[0][1])
