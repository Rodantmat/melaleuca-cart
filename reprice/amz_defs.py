"""READ-ONLY: dump Amazon product-type definitions (required attributes + allowed values) for AlphaDog Styles. Creates nothing. Prints no credentials."""
import json, os, urllib.request
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
MP = spapi.MARKETPLACE
def vals(p):
    """find enum/enumNames for an attribute schema"""
    out = None
    def walk(x):
        nonlocal out
        if isinstance(x, dict):
            if "enum" in x and out is None: out = (x["enum"], x.get("enumNames"))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(p); return out
def main():
    c = spapi.load_creds(HERE)
    os.makedirs("defs", exist_ok=True)
    for ptype in ("SHIRT", "SWEATSHIRT", "HAT"):
        r = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes/" + ptype,
                       params={"marketplaceIds": MP, "requirements": "LISTING", "locale": "en_US", "productTypeVersion": "LATEST"})
        link = r["schema"]["link"]["resource"]
        sch = json.loads(urllib.request.urlopen(link, timeout=60).read().decode())
        json.dump(sch, open("defs/%s.json" % ptype, "w"))
        req = sch.get("required", [])
        props = sch.get("properties", {})
        print("=== %s  version=%s  required=%d" % (ptype, r.get("productTypeVersion", {}).get("version"), len(req)))
        for k in req:
            e = vals(props.get(k, {}))
            print("  REQ", k, ("ENUM(%d): %s" % (len(e[0]), e[0][:14])) if e else "")
        # conditional requirements (allOf/if-then) summary
        for a in sch.get("allOf", [])[:40]:
            th = a.get("then", {}).get("required")
            if th: print("  COND", json.dumps(a.get("if", {}))[:160], "->", th)
        print("  variation attrs:", [k for k in props if k in ("variation_theme", "parentage_level", "child_parent_sku_relationship")])
        vt = vals(props.get("variation_theme", {}))
        print("  variation_theme enum:", vt[0] if vt else None)
        for k in ("color", "size", "fit_type", "target_gender", "department", "style", "material", "neck", "sleeve", "age_range_description", "item_type_keyword", "headwear_size", "special_size_type", "model_name"):
            if k in props:
                e = vals(props[k]); print("  attr", k, ("ENUM(%d) %s" % (len(e[0]), e[0][:25])) if e else "(free)", "| groups:", props[k].get("propertyGroup"))
main()
