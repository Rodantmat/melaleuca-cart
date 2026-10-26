"""Shippo LIVE read-only: rates for the two real past shipments (exact boxes from the UPS labels). NO label purchase."""
import os, json, urllib.request, urllib.error
t = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip()
assert t.startswith("shippo_live_"), "no live token"
def call(method, path, body=None):
    req = urllib.request.Request("https://api.goshippo.com" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "ShippoToken " + t, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {}
fx = 0.7128
try: fx = float(json.load(urllib.request.urlopen("https://api.frankfurter.dev/v1/latest?base=CAD&symbols=USD", timeout=20))["rates"]["USD"])
except Exception: pass
print("CAD->USD", fx)
_, ca = call("GET", "/carrier_accounts/?results=100")
accts = [(a["object_id"], a.get("is_shippo_account")) for a in ca.get("results", []) if a.get("carrier") == "ups"]
print("UPS accounts:", [(o[:8], s) for o, s in accts])
FROM = {"Toronto": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="500 Murray Ross Pkwy", street2="Unit 207", city="North York", state="ON", zip="M3J 2Z3", country="CA", phone="+19544590398", email="rodam00001@gmail.com"),
        "Vancouver": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="1160 Haro St", street2="Unit 204", city="Vancouver", state="BC", zip="V6E 1G2", country="CA", phone="+19544590398", email="rodam00001@gmail.com")}
TO = {"Toronto": dict(name="Flipping Magic LLC/Rodolfo Antunes", company="Amazon Services LLC", street1="55 West Oak Ridge Drive", city="Hagerstown", state="MD", zip="21740", country="US", phone="+19544590398", email="rodam00001@gmail.com"),
      "Vancouver": dict(name="Flipping Magic LLC/Rodolfo Antunes", company="Amazon Services LLC", street1="8410 Pardee Dr", city="Oakland", state="CA", zip="94621", country="US", phone="+19544590398", email="rodam00001@gmail.com")}
BOXES = {"Toronto": [(18,12,10,39),(18,12,10,35),(16,10,9,45)], "Vancouver": [(18,12,10,47),(18,12,10,38),(18,12,10,41),(15,10,9,26)]}
PAID = {"Toronto": 132.02, "Vancouver": 240.32}
UNITS = {"Toronto": 108, "Vancouver": 151}
for city in FROM:
    bx = BOXES[city]; W = sum(b[3] for b in bx)
    parcels = [dict(length=str(l), width=str(w), height=str(h), distance_unit="in", weight=str(g), mass_unit="lb") for l, w, h, g in bx]
    for uid, shippo in accts:
        cust = {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products", "non_delivery_option": "RETURN", "certify": True,
                "certify_signer": "Rodolfo Antunes", "incoterm": "DDU", "invoice": "RATECHECK",
                "items": [dict(description="Household products", quantity=UNITS[city], net_weight=str(round(W * 0.93, 1)), mass_unit="lb", value_amount=str(UNITS[city] * 18), value_currency="USD", origin_country="US", tariff_number="3402.50")]}
        _, cd = call("POST", "/customs/declarations/", cust)
        c, sh = call("POST", "/shipments/", {"address_from": FROM[city], "address_to": TO[city], "parcels": parcels, "customs_declaration": cd.get("object_id"), "carrier_accounts": [uid], "async": False})
        rs = sh.get("rates", [])
        print(f"\n{city}: {len(bx)} boxes {W} lb | acct {uid[:8]} shippo_managed={shippo} | http {c} | {len(rs)} rates | you paid US${PAID[city]}")
        for m in sh.get("messages", []):
            tx = m.get("text") or ""
            if "RatedShipmentAlert" not in tx: print("   msg:", tx[:200])
        for r in sorted(rs, key=lambda r: float(r["amount"])):
            a = float(r["amount"]); usd = a * fx if r["currency"] == "CAD" else a
            print(f"   {r['servicelevel']['name']:<30}{a:>9.2f} {r['currency']}  = US${usd:.2f}   diff vs paid {usd - PAID[city]:+.2f}   {r.get('estimated_days')}d")
