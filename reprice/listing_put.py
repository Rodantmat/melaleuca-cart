"""Create/replace one listing from reprice/listing_specs/<sku>.json. Default mode is a preview (nothing is created)."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
sku, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "preview")
spec = json.load(open(os.path.join(HERE, "listing_specs", sku + ".json")))
for k, v in spec["attributes"].items():
    for d in v: d.setdefault("marketplace_id", MP)
p = {"marketplaceIds": MP, "issueLocale": "en_US"}
if mode != "apply": p["mode"] = "VALIDATION_PREVIEW"
try:
    r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params=p, body=spec, tries=2, quiet=True)
    print("PUT result:", mode, r.get("status"), r.get("submissionId"), json.dumps(r.get("identifiers")))
    for i in r.get("issues", []): print("PUT issue:", i.get("severity"), i.get("code"), json.dumps(i.get("attributeNames")), i.get("message", "")[:400])
except spapi.SpError as e:
    print("PUT ERROR", str(e).replace("\n", " ")[:600])
