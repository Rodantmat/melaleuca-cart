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
def compact(x, d=0):
    """shrink a JSON-schema node: drop descriptions/titles/examples"""
    if isinstance(x, dict):
        return {k: compact(v, d+1) for k, v in x.items() if k not in ("description", "title", "examples", "$comment", "editable", "hidden", "selectors", "maxUniqueItems", "minUniqueItems")}
    if isinstance(x, list): return [compact(v, d+1) for v in x][:60]
    return x
def dump_keys():
    for ptype in ("SHIRT", "SWEATSHIRT", "HAT"):
        sch = json.load(open("defs/%s.json" % ptype)); props = sch.get("properties", {})
        keys = ("size", "color", "care_instructions", "import_designation", "fabric_type", "neck", "collar_style", "sleeve", "age_gender_category", "model_number", "model_name",
                "number_of_items", "item_package_quantity", "supplier_declared_dg_hz_regulation", "seasons", "headwear_size", "purchasable_offer", "list_price",
                "main_product_image_locator", "other_product_image_locator_1", "externally_assigned_product_identifier", "supplier_declared_has_product_identifier_exemption",
                "parentage_level", "child_parent_sku_relationship", "style", "special_size_type", "fit_type", "target_gender", "department", "item_type_keyword",
                "fulfillment_availability", "merchant_shipping_group", "condition_type", "material")
        keys = tuple(k for k in props if "size" in k) + ("seasons", "supplier_declared_dg_hz_regulation", "headwear_size")
        for k in keys:
            if k in props:
                print("SCHEMA", ptype, k, json.dumps(compact(props[k]), separators=(",", ":"))[:1400])
main()
dump_keys()
