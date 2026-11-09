"""One listing: show its status, every issue and its attributes (read-only); with FIX=preview only asks Amazon to VALIDATE a fix (writes nothing);
with FIX=apply writes the validated fix.  usage: python listing_fix.py SKU     env FIX=none|preview|apply"""
import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__)); MK = "ATVPDKIKX0DER"


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
