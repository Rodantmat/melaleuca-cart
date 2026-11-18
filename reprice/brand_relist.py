"""Create a correctly branded copy of a listing. Default mode is a preview (Amazon validates, nothing is created)."""
import os, sys, json, urllib.request, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
src_sku, src_asin, new_sku, brand, mode = sys.argv[1:6]; upc = sys.argv[6] if len(sys.argv) > 6 else ""
try:
    own = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, src_sku), params={"marketplaceIds": MP, "includedData": "attributes,productTypes"}, tries=3, quiet=True)
    pt = own["productTypes"][0]["productType"]
    cat = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + src_asin, params={"marketplaceIds": MP, "includedData": "attributes"}, tries=3, quiet=True).get("attributes") or {}
    d = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes/%s" % pt, params={"marketplaceIds": MP, "requirements": "LISTING", "locale": "en_US"}, tries=3, quiet=True)
    sch = json.load(urllib.request.urlopen(d["schema"]["link"]["resource"], timeout=60)); props = sch.get("properties", {})
    print("RELIST required:", json.dumps(sch.get("required", []))[:1500])
    a = {k: v for k, v in cat.items() if k in props}; a.update({k: v for k, v in (own.get("attributes") or {}).items() if k in props})
    for k in ("merchant_suggested_asin", "skip_offer", "fulfillment_availability", "purchasable_offer", "externally_assigned_product_identifier", "supplier_declared_has_product_identifier_exemption"): a.pop(k, None)
    a["brand"] = [{"value": brand, "language_tag": "en_US", "marketplace_id": MP}]
    name = (a.get("item_name") or [{}])[0].get("value", "").replace("​", "").strip()
    if brand.lower() not in name.lower(): a["item_name"] = [{"value": brand + " " + name, "language_tag": "en_US", "marketplace_id": MP}]
    if upc: a["externally_assigned_product_identifier"] = [{"type": "upc", "value": upc, "marketplace_id": MP}]
    else: a["supplier_declared_has_product_identifier_exemption"] = [{"value": True, "marketplace_id": MP}]
    a["fulfillment_availability"] = [{"fulfillment_channel_code": "AMAZON_NA"}]
    po = (own.get("attributes") or {}).get("purchasable_offer")
    if po: a["purchasable_offer"] = po
    ex = json.load(open(os.path.join(HERE, "brand_relist_extra.json"))).get(new_sku, {})
    for k, v in ex.items():
        a[k] = [dict(x, marketplace_id=MP, **({"language_tag": "en_US"} if k == "bullet_point" else {})) for x in v]
    for d in a.get("item_package_dimensions", []):
        for k in ("height", "length", "width"):
            if isinstance(d.get(k), dict) and str(d[k].get("unit", "")).upper() == "IN": d[k]["unit"] = "inches"
    print("RELIST attrs:", json.dumps(sorted(a)))
    print("RELIST name:", a["item_name"][0]["value"])
    body = {"productType": pt, "requirements": "LISTING", "attributes": a}
    p = {"marketplaceIds": MP, "issueLocale": "en_US"}
    if mode != "apply": p["mode"] = "VALIDATION_PREVIEW"
    r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, new_sku), params=p, body=body, tries=2, quiet=True)
    print("RELIST result:", mode, r.get("status"), r.get("submissionId"), json.dumps(r.get("identifiers")))
    for i in r.get("issues", []): print("RELIST issue:", i.get("severity"), i.get("code"), json.dumps(i.get("attributeNames")), i.get("message", "")[:400])
except spapi.SpError as e:
    print("RELIST ERROR", str(e).replace("\n", " ")[:600])
