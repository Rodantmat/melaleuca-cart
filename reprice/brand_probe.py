"""READ-ONLY: catalog brand/identifier lookup + listing restrictions (no credentials printed)."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
asins = [a for a in sys.argv[1].split(",") if a]; kw = sys.argv[2] if len(sys.argv) > 2 else ""
def item(a):
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": MP, "includedData": "summaries,identifiers,attributes,productTypes"}, tries=3, quiet=True)
        s = (r.get("summaries") or [{}])[0]; at = r.get("attributes") or {}
        print("PROBE item", a, json.dumps({"brand": s.get("brand"), "manufacturer": s.get("manufacturer"), "name": s.get("itemName"), "pt": r.get("productTypes"),
              "ids": [i for g in r.get("identifiers") or [] for i in g.get("identifiers", [])], "brand_attr": at.get("brand"), "ext": at.get("externally_assigned_product_identifier"),
              "exempt": at.get("supplier_declared_has_product_identifier_exemption")})[:900])
    except spapi.SpError as e: print("PROBE item", a, "ERROR", str(e).replace("\n", " ")[:300])
    try:
        r = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params={"asin": a, "sellerId": seller, "marketplaceIds": MP, "conditionType": "new_new", "reasonLocale": "en_US"}, tries=3, quiet=True)
        print("PROBE restrictions", a, json.dumps([{"reasons": [{k: v for k, v in x.items() if k != "links"} for x in y.get("reasons", [])]} for y in r.get("restrictions", [])])[:700] or "none")
    except spapi.SpError as e: print("PROBE restrictions", a, "ERROR", str(e).replace("\n", " ")[:300])
for a in asins: item(a)
if kw:
    for extra in ({"brandNames": "Melaleuca"}, {}):
        try:
            p = {"marketplaceIds": MP, "keywords": kw, "includedData": "summaries", "pageSize": 20}; p.update(extra)
            r = spapi.call(c, "GET", "/catalog/2022-04-01/items", params=p, tries=3, quiet=True)
            print("PROBE search", json.dumps(extra), "n=", r.get("numberOfResults"), "brands=", json.dumps((r.get("refinements") or {}).get("brands", [])[:8]))
            for it in r.get("items", []):
                s = (it.get("summaries") or [{}])[0]; print("PROBE  ", it.get("asin"), "|", s.get("brand"), "|", (s.get("itemName") or "")[:90])
        except spapi.SpError as e: print("PROBE search ERROR", str(e).replace("\n", " ")[:300])
