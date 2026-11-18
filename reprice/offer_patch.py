"""Add/replace the offer (price + FBA channel) on one existing listing. Default mode is a preview."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
sku, price, mode = sys.argv[1], float(sys.argv[2]), (sys.argv[3] if len(sys.argv) > 3 else "preview")
try:
    cur = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params={"marketplaceIds": MP, "includedData": "productTypes"}, tries=3, quiet=True)
    pt = cur["productTypes"][0]["productType"]
    body = {"productType": pt, "patches": [
        {"op": "replace", "path": "/attributes/purchasable_offer", "value": [{"currency": "USD", "audience": "ALL", "marketplace_id": MP, "our_price": [{"schedule": [{"value_with_tax": price}]}]}]},
        {"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{"fulfillment_channel_code": "AMAZON_NA", "marketplace_id": MP}]},
        {"op": "replace", "path": "/attributes/condition_type", "value": [{"value": "new_new", "marketplace_id": MP}]}]}
    p = {"marketplaceIds": MP, "issueLocale": "en_US"}
    if mode != "apply": p["mode"] = "VALIDATION_PREVIEW"
    r = spapi.call(c, "PATCH", "/listings/2021-08-01/items/%s/%s" % (seller, sku), params=p, body=body, tries=2, quiet=True)
    print("OFFER result:", mode, pt, r.get("status"), r.get("submissionId"))
    for i in r.get("issues", []): print("OFFER issue:", i.get("severity"), i.get("code"), json.dumps(i.get("attributeNames")), i.get("message", "")[:300])
except spapi.SpError as e:
    print("OFFER ERROR", str(e).replace("\n", " ")[:500])
