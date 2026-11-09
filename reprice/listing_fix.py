"""One listing: show its status, every issue and its attributes (read-only); with FIX=preview only asks Amazon to VALIDATE a fix (writes nothing);
with FIX=apply writes the validated fix.  usage: python listing_fix.py SKU     env FIX=none|preview|apply"""
import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__)); MK = "ATVPDKIKX0DER"


def pesticide_patches(at):
    """Remove pesticide-type wording (disinfectant / deodorizing) from the text-type attributes."""
    def t(v, lang=True):
        d = {"value": v, "marketplace_id": MK}
        if lang: d["language_tag"] = "en_US"
        return [d]
    desc = (at.get("product_description") or [{}])[0].get("value", "")
    desc = desc.replace("Toilet Bowl Cleaning & Deodorizing", "Toilet Bowl Cleaning")
    P = [("cleaning_agent_formulation", t("descaler", False)),
         ("liquid_contents_description", t("Toilet bowl cleaning gel", False)),
         ("recommended_uses_for_product", t("Toilet bowl cleaner")),
         ("product_description", t(desc))]
    return [{"op": "replace", "path": "/attributes/" + k, "value": v} for k, v in P]


def main():
    sku = sys.argv[1]; mode = os.environ.get("FIX", "none")
    c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or open(os.path.join(HERE, "state", "seller.txt")).read().strip()
    path = "/listings/2021-08-01/items/%s/%s" % (seller, sku)
    it = spapi.call(c, "GET", path, params={"marketplaceIds": MK, "includedData": "summaries,attributes,issues,offers"}, quiet=True)
    print("SUMMARY", json.dumps(it.get("summaries"), indent=1)[:900])
    print("ISSUES", json.dumps(it.get("issues"), indent=1)[:3500])
    print("OFFERS", json.dumps(it.get("offers"))[:500])
    try:
        asin = ((it.get("summaries") or [{}])[0]).get("asin")
        rs = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params={"asin": asin, "conditionType": "new_new", "sellerId": seller, "marketplaceIds": MK, "reasonLocale": "en_US"}, quiet=True)
        print("RESTRICTIONS", json.dumps(rs, indent=1)[:2500])
    except Exception as e:
        print("RESTRICTIONS call failed:", str(e)[:300])
    at = it.get("attributes") or {}
    print("ATTRIBUTE NAMES", sorted(at))
    print("ALL_ATTRIBUTES", json.dumps(at, ensure_ascii=False)[:20000])
    gk = at.get("generic_keyword")
    print("GENERIC_KEYWORD", json.dumps(gk, indent=1)[:2500])
    if mode == "schema":
        d = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes/CLEANING_AGENT", params={"marketplaceIds": MK, "requirements": "LISTING", "locale": "en_US"}, quiet=True)
        link = ((d.get("schema") or {}).get("link") or {}).get("resource")
        print("SCHEMA LINK", link)
        import urllib.request
        sc = json.loads(urllib.request.urlopen(link, timeout=60).read().decode())
        prop = sc.get("properties", {}).get("cleaning_agent_formulation", {})
        print("FORMULATION_SCHEMA", json.dumps(prop)[:3000])
        return
    if mode in ("pest_preview", "pest_apply"):
        ptype = ((it.get("summaries") or [{}])[0]).get("productType") or "PRODUCT"
        body = {"productType": ptype, "patches": pesticide_patches(at)}
        print("PROPOSED PATCH", json.dumps(body, ensure_ascii=False)[:3000])
        v = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK, "mode": "VALIDATION_PREVIEW"}, body=body)
        print("VALIDATION", json.dumps(v)[:3000])
        if mode == "pest_apply" and v.get("status") == "VALID" and not any(i.get("severity") == "ERROR" for i in v.get("issues", [])):
            r = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK}, body=body)
            print("APPLIED", json.dumps(r)[:1500])
    if mode in ("preview", "apply") and isinstance(gk, list) and len(gk) > 1:
        ptype = ((it.get("summaries") or [{}])[0]).get("productType") or "PRODUCT"
        keep = [x for x in gk if x.get("marketplace_id") == MK][:1] or gk[:1]
        body = {"productType": ptype, "patches": [{"op": "replace", "path": "/attributes/generic_keyword", "value": keep}]}
        print("PROPOSED PATCH", json.dumps(body)[:1200])
        v = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK, "mode": "VALIDATION_PREVIEW"}, body=body)
        print("VALIDATION", json.dumps(v)[:1500])
        if mode == "apply" and v.get("status") == "VALID" and not any(i.get("severity") == "ERROR" for i in v.get("issues", [])):
            r = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK}, body=body)
            print("APPLIED", json.dumps(r)[:1500])


if __name__ == "__main__":
    main()
