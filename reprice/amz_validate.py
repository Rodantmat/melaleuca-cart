"""CHECK-ONLY validation of the AlphaDog Styles Amazon listings (putListingsItem mode=VALIDATION_PREVIEW ONLY).
Nothing is created or published: the mode is hard-coded below and there is no publish path in this file.
Feed: store/data/amazon_feed.json from the public Alphadog-Styles repo. Prints no credentials."""
import json, os, sys, urllib.request, collections
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
MP = spapi.MARKETPLACE
FEED = "https://raw.githubusercontent.com/Rodantmat/Alphadog-Styles/main/store/data/amazon_feed.json"
MODE = "VALIDATION_PREVIEW"      # never anything else in this file
LEAD_DAYS = 7                    # production 2-5 business days + hand-off; keep realistic so Amazon's late-shipment metric is safe
ORIGIN = {"tee": "HN", "hoodie": "HN", "wtank": "HN", "tank": "HN", "polo": "HN", "cap": "HN"}   # PLACEHOLDER for the check - must be verified per Printify print provider/blank before any publish
KEYWORDS = {"tee": ["fashion-t-shirts", "t-shirts"], "hoodie": ["fashion-hoodies"], "wtank": ["fashion-tank-tops", "tank-tops"], "tank": ["fashion-tank-tops", "tank-tops"],
            "polo": ["polo-shirts", "fashion-polos"], "cap": ["baseball-caps"]}
SIZE_NAMES = {"S": ["S", "Small"], "M": ["M", "Medium"], "L": ["L", "Large"], "XL": ["XL", "X-Large", "X Large"], "2XL": ["2XL", "XXL", "XX-Large", "2X-Large"],
              "One size": ["One Size", "OS", "One size"]}
SPEC = {  # per product: neck, collar, sleeve length, department, gender, fit
    "tee": dict(neck="Crew Neck", collar="Ribbed Collar", sleeve="short_sleeve", dept="Unisex", gender="unisex", fit="Regular"),
    "hoodie": dict(neck="Hooded Neck", collar=None, sleeve="long_sleeve", dept="Unisex Adult", gender="unisex", fit="Regular"),
    "wtank": dict(neck="Scoop Neck", collar="Collarless", sleeve="sleeveless", dept="Womens", gender="female", fit="Fitted"),
    "tank": dict(neck="Crew Neck", collar="Collarless", sleeve="sleeveless", dept="Unisex", gender="unisex", fit="Regular"),
    "polo": dict(neck="Collared Neck", collar="Polo Collar", sleeve="short_sleeve", dept="Unisex", gender="unisex", fit="Regular"),
    "cap": dict(neck=None, collar=None, sleeve=None, dept="Unisex", gender="unisex", fit="Adjustable")}
SIZEKEY = {"SHIRT": "shirt_size", "SWEATSHIRT": "apparel_size", "HAT": "headwear_size"}

def load_schema(c, ptype):
    r = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes/" + ptype, params={"marketplaceIds": MP, "requirements": "LISTING", "locale": "en_US", "productTypeVersion": "LATEST"})
    return json.loads(urllib.request.urlopen(r["schema"]["link"]["resource"], timeout=60).read().decode())
def enum_of(node):
    out = []
    def walk(x):
        if isinstance(x, dict):
            if "enum" in x: out.append((x["enum"], x.get("enumNames") or x["enum"]))
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(node); return out[0] if out else ([], [])

class Builder:
    def __init__(self, sch, ptype):
        self.p = sch["properties"]; self.ptype = ptype
        self.kw = None
        vals, names = enum_of(self.p["item_type_keyword"]) if "item_type_keyword" in self.p else ([], [])
        self.kwset = set(vals)
        sk = SIZEKEY[ptype]
        self.sizevals, self.sizenames = enum_of(self.p[sk]["items"]["properties"]["size"]) if sk in self.p else ([], [])
    def el(self, key, value=None, **extra):
        """one array element for attribute `key`, adding marketplace_id / language_tag only when that attribute's schema has them"""
        if key not in self.p: return None
        ip = self.p[key]["items"]["properties"]; d = {}
        if value is not None: d["value"] = value
        d.update(extra)
        if "marketplace_id" in ip: d["marketplace_id"] = MP
        if "language_tag" in ip: d["language_tag"] = "en_US"
        return [d]
    def add(self, a, key, value=None, **extra):
        e = self.el(key, value, **extra)
        if e is not None: a[key] = e
    def keyword(self, pk):
        for k in KEYWORDS[pk]:
            if k in self.kwset: return k
        sub = "tank" if "tank" in pk else "polo" if pk == "polo" else None
        for k in sorted(self.kwset):
            if sub and sub in k: return k
        return KEYWORDS[pk][0]
    def size(self, s):
        for cand in SIZE_NAMES[s]:
            for v, n in zip(self.sizevals, self.sizenames):
                if str(n).lower() == cand.lower() and not str(v).startswith(("jaspo", "numeric", "go_")) and not str(v)[:1].isdigit(): return v
        return None
    def pick(self, node, wants):
        vals, names = enum_of(node)
        for w in wants:
            for v, n in zip(vals, names):
                if str(v).lower() == w.lower() or str(n).lower() == w.lower(): return v
        return None
    def common(self, F, title):
        pk = F["prod"]; a = {}; sp = SPEC[pk]
        self.add(a, "item_name", title[:200]); self.add(a, "brand", "AlphaDog Styles")
        self.add(a, "product_description", F["desc"][:1900])
        a["bullet_point"] = [dict(self.el("bullet_point", b)[0]) for b in F["bullets"]]
        self.add(a, "country_of_origin", ORIGIN[pk])
        self.add(a, "fabric_type", F["fabric"])
        self.add(a, "supplier_declared_has_product_identifier_exemption", True)
        self.add(a, "supplier_declared_dg_hz_regulation", "not_applicable")
        self.add(a, "item_type_keyword", self.keyword(pk))
        self.add(a, "department", sp["dept"]); self.add(a, "age_range_description", "Adult")
        self.add(a, "target_gender", sp["gender"]); self.add(a, "fit_type", sp["fit"]); self.add(a, "style", "Casual")
        self.add(a, "care_instructions", "Machine Wash" if pk != "cap" else "Hand Wash Only")
        self.add(a, "import_designation", "Made in the USA and Imported")
        self.add(a, "material", F["material"]); self.add(a, "model_name", "Dog Breed Line Art " + F["noun"])
        self.add(a, "number_of_items", 1); self.add(a, "item_package_quantity", 1)
        self.add(a, "age_gender_category", "unisex-adult" if sp["gender"] == "unisex" else "adult-women")
        if pk == "cap": self.add(a, "seasons", "All")
        self.add(a, "special_size_type", "Standard")
        if "batteries_required" in self.p: a["batteries_required"] = [{"value": False, **({"marketplace_id": MP} if "marketplace_id" in self.p["batteries_required"]["items"]["properties"] else {})}]
        if sp["neck"] and "neck" in self.p:
            a["neck"] = [{**({"marketplace_id": MP} if "marketplace_id" in self.p["neck"]["items"]["properties"] else {}), "neck_style": [{"value": sp["neck"], "language_tag": "en_US"}]}]
        if sp["collar"]: self.add(a, "collar_style", sp["collar"])
        if sp["sleeve"] and "sleeve" in self.p:
            tp = self.p["sleeve"]["items"]["properties"].get("type")
            slv = {"short_sleeve": ["Short Sleeve"], "long_sleeve": ["Long Sleeve"], "sleeveless": ["Sleeveless", "No Sleeve", "Sleeveless Sleeve"]}[sp["sleeve"]]
            tv = self.pick(tp, slv) if tp else None
            a["sleeve"] = [{**({"marketplace_id": MP}), "length_description": [{"value": sp["sleeve"]}], **({"type": [{"value": tv, "language_tag": "en_US"}]} if tv else {})}]
            if not tv: print("NO SLEEVE TYPE for", pk, "enum:", enum_of(tp)[0][:60] if tp else None)
        return a
    def parent(self, F):
        a = self.common(F, F["title"])
        a["parentage_level"] = [{"value": "parent", "marketplace_id": MP}]
        a["variation_theme"] = [{"name": "COLOR" if F["prod"] == "cap" else "COLOR/SIZE"}]
        for i, h in enumerate(F["heroes"][:1]): a["main_product_image_locator"] = [{"media_location": h, "marketplace_id": MP}]
        return a
    def child(self, F, k):
        pr = k["color"].split(" · ")
        t = ("AlphaDog Styles Unisex %s for Adults - %s Art, %s" % (F["noun"], pr[0], ", ".join(pr[1:])))[:200]
        if F["prod"] == "wtank": t = t.replace("Unisex", "Women's", 1).replace("Women's Women's", "Women's")
        a = self.common(F, t)
        a["parentage_level"] = [{"value": "child", "marketplace_id": MP}]
        a["child_parent_sku_relationship"] = [{"child_relationship_type": "variation", "parent_sku": F["parent_sku"], "marketplace_id": MP}]
        self.add(a, "color", k["color"], standardized_values=[k["color_std"]])
        a["model_number"] = [{"value": k["sku"][:40], "marketplace_id": MP}]
        sk = SIZEKEY[F["ptype"]]
        if F["prod"] != "cap":
            tok = self.size(k["size"]); ip = self.p[sk]["items"]["properties"]
            el = {"size_system": "as1", "size_class": "alpha", "size": tok or k["size"]}
            if "marketplace_id" in ip: el["marketplace_id"] = MP
            for extra in ("body_type", "height_type"):
                if extra in ip:
                    v = self.pick(ip[extra], ["regular", "Regular"]) or (enum_of(ip[extra])[0] or [None])[0]
                    if v: el[extra] = v
            a[sk] = [el]
        else:
            tok = self.size("One size")
            if tok: a[sk] = [{"size_system": "as1", "size_class": "alpha", "size": tok, "marketplace_id": MP}]
        a["list_price"] = [{"currency": "USD", "value": k["price"], "marketplace_id": MP}]
        a["purchasable_offer"] = [{"marketplace_id": MP, "currency": "USD", "our_price": [{"schedule": [{"value_with_tax": k["price"]}]}]}]
        a["fulfillment_availability"] = [{"fulfillment_channel_code": "DEFAULT", "quantity": 999, "lead_time_to_ship_max_days": LEAD_DAYS}]
        a["condition_type"] = [{"value": "new_new", "marketplace_id": MP}]
        imgs = ["https://alphadogstyles.com/mk/" + k["img"]] if k.get("img") else []
        if imgs: a["main_product_image_locator"] = [{"media_location": imgs[0], "marketplace_id": MP}]
        for i, h in enumerate(F["heroes"][:3], 1):
            a["other_product_image_locator_%d" % i] = [{"media_location": h, "marketplace_id": MP}]
        return a, tok

def main():
    c = spapi.load_creds(HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
    feed = json.loads(urllib.request.urlopen(FEED, timeout=120).read().decode())
    print("feed:", len(feed), "parents,", sum(len(f["children"]) for f in feed), "children; mode", MODE)
    B = {}
    for pt in ("SHIRT", "SWEATSHIRT", "HAT"):
        B[pt] = Builder(load_schema(c, pt), pt)
        print("size tokens", pt, {s: B[pt].size(s) for s in ("S", "M", "L", "XL", "2XL", "One size")}, "| keyword for", pt, [B[pt].keyword(p) for p in KEYWORDS if {"SHIRT": ("tee", "wtank", "tank", "polo"), "SWEATSHIRT": ("hoodie",), "HAT": ("cap",)}[pt].count(p)])
    for pt in ("SHIRT", "SWEATSHIRT", "HAT"):
        pp = B[pt].p
        for ex_k in ("sleeve", SIZEKEY[pt]):
            if ex_k in pp:
                for kk, vv in pp[ex_k]["items"]["properties"].items():
                    if kk in ("type", "body_type", "height_type", "size_class"): print("ENUM", pt, ex_k, kk, enum_of(vv)[0][:40])
    def v(x): return [{"value": x, "marketplace_id": MP}]
    for ptype, nm in (("SHIRT", "AlphaDog Styles French Bulldog Line Art Tee"), ("SWEATSHIRT", "AlphaDog Styles French Bulldog Hoodie"), ("HAT", "AlphaDog Styles French Bulldog Dad Hat")):
        for variant in ("plain", "with_parentage_none"):
            at = {"item_name": v(nm), "brand": v("AlphaDog Styles"), "supplier_declared_has_product_identifier_exemption": v(True), "color": v("White"),
                  "country_of_origin": v("HN"), "bullet_point": v("Original dog breed line art"), "product_description": v("Original dog breed line-art design on a premium blank."),
                  "purchasable_offer": [{"marketplace_id": MP, "currency": "USD", "our_price": [{"schedule": [{"value_with_tax": 30.0}]}]}],
                  "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT", "quantity": 100}]}
            try:
                r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, "ALPHADOG-MINIPROBE-" + ptype), params={"marketplaceIds": MP, "issueLocale": "en_US", "mode": MODE},
                               body={"productType": ptype, "requirements": "LISTING", "attributes": at})
                codes = collections.Counter((i.get("severity"), i.get("code")) for i in r.get("issues", []))
                print("MINIPROBE", ptype, variant, r.get("status"), dict(codes))
                for i in r.get("issues", []):
                    if i.get("code") in ("5665", "8560"): print("   MINIPROBE_MSG", ptype, i.get("code"), (i.get("message") or "")[:400])
            except spapi.SpError as e:
                print("MINIPROBE", ptype, "ERROR", e)
            break
    stat = collections.Counter(); issues = collections.Counter(); ex = {}; shown = set()
    sample_n = int(os.environ.get("AMZ_SAMPLE", "2"))
    for F in feed:
        b = B[F["ptype"]]; kids = F["children"]
        picks = [kids[0], kids[-1]] if sample_n >= 2 else kids[:1]
        jobs = [("PARENT", F["parent_sku"], b.parent(F))] + [("CHILD", k["sku"], b.child(F, k)[0]) for k in picks]
        for role, sk, attrs in jobs:
            body = {"productType": F["ptype"], "requirements": "LISTING", "attributes": attrs}
            if role == "PARENT": pass
            try:
                r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, sk), params={"marketplaceIds": MP, "issueLocale": "en_US", "mode": MODE}, body=body)
            except spapi.SpError as e:
                stat[(role, "ERROR")] += 1; issues[("ERROR", str(e)[:200], "")] += 1; continue
            st = r.get("status"); stat[(role, st)] += 1
            for i in r.get("issues", []):
                key = (i.get("severity"), i.get("code"), (i.get("message") or "")[:(900 if i.get("code") in ("5665", "8560") else 170)], ",".join(i.get("attributeNames") or []), F["prod"] + "/" + role)
                issues[key] += 1; ex.setdefault(key, (F["id"], sk))
            tag = (F["prod"], role)
            if tag not in shown and os.environ.get("AMZ_SHOW", "1") == "1":
                shown.add(tag); print("EXAMPLE_PAYLOAD", F["prod"], role, sk, json.dumps(attrs)[:2600])
    print("\n=== STATUS (role, status): count")
    for k, v in sorted(stat.items(), key=str): print("  ", k, v)
    print("\n=== ISSUES (severity | code | message | attrs): count  [example listing, sku]")
    for k, v in sorted(issues.items(), key=lambda kv: (str(kv[0][0]), -kv[1])): print("  ", " | ".join(map(str, k)), ":", v, ex.get(k))
main()
