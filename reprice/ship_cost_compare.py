"""READ-ONLY: estimate box weights of the latest Toronto/Vancouver inbound shipments from catalog weights, then get live UPS rates (rates only, NO label)."""
import json, os, re, math, urllib.request, urllib.error, csv
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE)
os.makedirs("/tmp/so", exist_ok=True)
SHIP = {"Toronto": ("FBA19TR55MSN", 132.02, dict(name="Amazon HGR6", company="Amazon", street1="55 W Oak Ridge Dr", city="Hagerstown", state="MD", zip="21740", country="US", phone="+13054092425", email="rodam00001@gmail.com")),
        "Vancouver": ("FBA19THVPCGY", 240.32, dict(name="Amazon HLI2", company="Amazon", street1="1 Amazon Way", city="Hollister", state="CA", zip="95023", country="US", phone="+13054092425", email="rodam00001@gmail.com"))}
FROM = {"Toronto": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="500 Murray Ross Pkwy", street2="Unit 207", city="North York", state="ON", zip="M3J 2Z3", country="CA", phone="+19544590398", email="rodam00001@gmail.com"),
        "Vancouver": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="1160 Haro St", street2="Unit 204", city="Vancouver", state="BC", zip="V6E 1G2", country="CA", phone="+19544590398", email="rodam00001@gmail.com")}
asin = {r["sku"]: r["asin"] for r in csv.DictReader(open(os.path.join(HERE, "..", "feedwork", "sku_asin.tsv")), delimiter="\t")}
cat = {}
def info(a):
    if a in cat: return cat[a]
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": spapi.MARKETPLACE, "includedData": "dimensions"}, quiet=True, tries=4)
    except spapi.SpError as e:
        cat[a] = None; return None
    d = (r.get("dimensions") or [{}])[0].get("package") or (r.get("dimensions") or [{}])[0].get("item") or {}
    def v(k, to):
        x = d.get(k) or {}
        if not x: return None
        u = (x.get("unit") or "").lower(); n = float(x["value"])
        return n * to.get(u, 1)
    W = {"pounds": 1, "ounces": 1/16, "grams": 0.00220462, "kilograms": 2.20462}; L = {"inches": 1, "centimeters": 0.393701, "feet": 12}
    cat[a] = (v("weight", W), v("length", L), v("width", L), v("height", L)); return cat[a]
res = {}
for city, (sid, paid, to) in SHIP.items():
    items = {i["SellerSKU"]: i.get("QuantityShipped") for i in (spapi.call(c, "GET", "/fba/inbound/v0/shipments/%s/items" % sid, quiet=True).get("payload") or {}).get("ItemData") or []}
    tw = tv = 0.0; miss = []; units = 0
    for sku, q in items.items():
        a = asin.get(sku); i = info(a) if a else None
        units += q or 0
        if not i or not i[0] or not i[1]: miss.append(sku); continue
        tw += i[0] * q; tv += i[1] * i[2] * i[3] * q
    print(f"{city} {sid}: skus {len(items)} units {units} | weight known for {len(items)-len(miss)} skus: {tw:.1f} lb, volume {tv/1728:.1f} ft3 | missing {len(miss)} {miss[:8]}")
    res[city] = dict(shipment=sid, units=units, weight_lb=tw, volume_in3=tv, missing=miss, paid_usd=paid)
json.dump(res, open("/tmp/so/estimate.json", "w"), indent=1)
# ---- rates
t = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip()
if not t.startswith("shippo_live_"): print("no live token, rates skipped"); raise SystemExit
def call(method, path, body=None):
    req = urllib.request.Request("https://api.goshippo.com" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "ShippoToken " + t, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}
fx = 0.72
try:
    fx = float(json.load(urllib.request.urlopen("https://api.frankfurter.dev/v1/latest?base=CAD&symbols=USD", timeout=20))["rates"]["USD"])
except Exception as e: print("fx fallback", e)
print("CAD->USD", fx)
c0, ca = call("GET", "/carrier_accounts/?results=100")
own = [a["object_id"] for a in ca.get("results", []) if a.get("carrier") == "ups" and a.get("active")]
print("active UPS accounts:", [o[:8] for o in own])
for city, (sid, paid, to) in SHIP.items():
    e = res[city]; W = e["weight_lb"]
    for n in range(max(2, math.ceil(W / 45)), math.ceil(W / 45) + 4):
        per = round(W / n, 1)
        side = max(12.0, round((e["volume_in3"] / n / 0.6) ** (1/3), 0))
        parcels = [dict(length=str(side * 1.4), width=str(side * 1.1), height=str(side * 0.8), distance_unit="in", weight=str(per), mass_unit="lb")] * n
        cust = {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products", "non_delivery_option": "RETURN",
                "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": "DDU", "invoice": "RATECHECK",
                "items": [dict(description="Household products", quantity=e["units"], net_weight=str(round(W * 0.95, 1)), mass_unit="lb", value_amount=str(round(e["units"] * 18.0, 2)), value_currency="USD", origin_country="US", tariff_number="3402.50")]}
        for uid in own:
            _, cd = call("POST", "/customs/declarations/", cust)
            _, sh = call("POST", "/shipments/", {"address_from": FROM[city], "address_to": to, "parcels": parcels, "customs_declaration": cd.get("object_id"), "carrier_accounts": [uid], "async": False})
            rs = {r["servicelevel"]["name"]: r for r in sh.get("rates", [])}
            std = rs.get("Standard®")
            msg = [m.get("text", "")[:120] for m in sh.get("messages", []) if "RatedShipmentAlert" not in (m.get("text") or "")]
            print(f"{city}: est {W:.0f} lb in {n} boxes ({per} lb, ~{side:.0f}in) | acct {uid[:8]} | UPS Standard " + (f"CA${float(std['amount']):.2f} = US${float(std['amount']) * fx:.2f}" if std else f"none {msg}") + f" | you paid US${paid}")
