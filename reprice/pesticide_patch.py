"""Set (or preview) the Pesticide Marking registration status of one SKU. Default = VALIDATION_PREVIEW (changes nothing)."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
sku, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "preview")
MP = spapi.MARKETPLACE
if mode == "apply": sys.exit("apply is switched off in this version")
for label, val in (("EPA reg type + not-a-pesticide", [{"marking_type": "epa_registration_number", "registration_status": "fifra_not_considered_pesticide", "marketplace_id": MP}]),
                   ("EPA est type + not-a-pesticide", [{"marking_type": "epa_establishment_number", "registration_status": "fifra_not_considered_pesticide", "marketplace_id": MP}])):
    body = {"productType": "CLEANING_AGENT", "patches": [{"op": "replace", "path": "/attributes/pesticide_marking", "value": val}]}
    p = {"marketplaceIds": MP, "issueLocale": "en_US"}
    if mode != "apply": p["mode"] = "VALIDATION_PREVIEW"
    try:
        r = spapi.call(c, "PATCH", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params=p, body=body, tries=2, quiet=True)
        print("PATCH %s [%s] status=%s submission=%s" % (mode, label, r.get("status"), r.get("submissionId")))
        for i in r.get("issues", []): print("PATCH issue:", json.dumps(i)[:600])
    except spapi.SpError as e:
        print("PATCH ERROR", str(e).replace("\n", " ")[:500])
