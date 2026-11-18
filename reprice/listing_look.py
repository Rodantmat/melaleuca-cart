"""READ-ONLY: print one listing's attributes, status and issues (no credentials printed)."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; sku = sys.argv[1]
try:
    r = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params={"marketplaceIds": spapi.MARKETPLACE, "issueLocale": "en_US",
                   "includedData": "summaries,attributes,issues,productTypes"}, tries=3, quiet=True)
    print("LOOK summaries:", json.dumps(r.get("summaries"))[:600])
    print("LOOK productTypes:", json.dumps(r.get("productTypes")))
    for i in r.get("issues", []): print("LOOK issue:", json.dumps(i)[:900])
    a = r.get("attributes") or {}
    for k in sorted(a):
        v = json.dumps([{x: y for x, y in d.items() if x not in ("marketplace_id", "language_tag")} for d in a[k]] if isinstance(a[k], list) else a[k])
        print("LOOK attr %s = %s" % (k, v[:700]))
    pt = (r.get("productTypes") or [{}])[0].get("productType")
    if pt:
        d = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes/%s" % pt, params={"marketplaceIds": spapi.MARKETPLACE, "requirements": "LISTING", "locale": "en_US"}, tries=3, quiet=True)
        import urllib.request
        sch = json.load(urllib.request.urlopen(d["schema"]["link"]["resource"], timeout=60))
        for k, v in sch.get("properties", {}).items():
            if "pesticide" in k or "fifra" in k or "epa" in k: print("LOOK schema %s = %s" % (k, json.dumps(v)[:2500]))
except spapi.SpError as e:
    print("LOOK ERROR", str(e).replace("\n", " ")[:400])
