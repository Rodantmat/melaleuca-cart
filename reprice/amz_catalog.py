"""READ-ONLY: how Amazon's CATALOG sees given ASINs (Catalog Items API). Prints classification, relationships, variation attributes."""
import json, os, collections
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE)
asins = [a.strip() for a in os.environ.get("AMZ_ASINS", "").split(",") if a.strip()]
agg = collections.Counter()
for a in asins:
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": spapi.MARKETPLACE, "includedData": "summaries,relationships,classifications,attributes,productTypes,salesRanks"})
        s = (r.get("summaries") or [{}])[0]
        cl = [(x.get("displayName"), x.get("classificationId")) for m in r.get("classifications", []) for x in m.get("classifications", [])]
        rel = [x for m in r.get("relationships", []) for x in m.get("relationships", [])]
        relsum = [(x.get("type"), len(x.get("childAsins") or []), x.get("parentAsins"), (x.get("variationTheme") or {})) for x in rel]
        at = r.get("attributes") or {}
        pick = {k: [ (v.get("value") if isinstance(v, dict) else v) for v in at.get(k, [])][:2] for k in ("style", "color", "size", "department", "target_gender", "item_type_keyword", "variation_theme", "parentage_level", "child_parent_sku_relationship") if k in at}
        if "size" in at: pick["size"] = [{kk: vv for kk, vv in v.items() if kk in ("size", "size_class", "size_system")} for v in at["size"]][:1]
        bc = s.get("browseClassification"); ic = s.get("itemClassification")
        print(a, "| itemClass", ic, "| browse", bc, "| ptype", [p.get("productType") for p in r.get("productTypes", [])], "| class", cl[:3])
        print("    rel", json.dumps(relsum)[:400]); print("    attrs", json.dumps(pick)[:500])
        agg[(ic, json.dumps(bc), json.dumps([x[:1]+x[2:] for x in relsum])[:200])] += 1
    except spapi.SpError as e: print(a, "ERR", str(e)[:200])
print("SUMMARY"); 
for k, n in agg.most_common(): print("  ", n, k)
