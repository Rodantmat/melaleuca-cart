"""READ-ONLY: full listing-restriction reasons (with Amazon's message and links) for ASINs."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
for a in sys.argv[1].split(","):
    for cond in ("new_new", None):
        p = {"asin": a, "sellerId": seller, "marketplaceIds": MP, "reasonLocale": "en_US"}
        if cond: p["conditionType"] = cond
        try:
            r = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params=p, tries=4, quiet=True)
            print("RESTR", a, cond, json.dumps(r.get("restrictions"))[:1500])
        except spapi.SpError as e: print("RESTR", a, cond, "ERROR", str(e)[:200])
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": MP, "includedData": "summaries,productTypes,classifications"}, tries=3, quiet=True)
        s = (r.get("summaries") or [{}])[0]
        print("RESTR_ITEM", a, json.dumps({"name": s.get("itemName"), "brand": s.get("brand"), "pt": r.get("productTypes"), "cls": [x.get("classifications") for x in r.get("classifications", [])]})[:900])
    except spapi.SpError as e: print("RESTR_ITEM", a, "ERROR", str(e)[:200])
