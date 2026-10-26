"""Shippo LIVE, READ-ONLY: list carrier accounts and get rates. NEVER buys a label (no /transactions call exists in this file)."""
import os, sys, json, re, urllib.request, urllib.error
t = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip()
if not t:
    for line in os.environ.get("CREDENTIALS_ENV", "").splitlines():
        m = re.match(r"\s*SHIPPO_LIVE_TOKEN\s*=\s*(\S+)", line)
        if m: t = m.group(1).strip().strip('"\'')
if not t or t.startswith("shippo_test_"): print("no LIVE token -> abort"); sys.exit(1)
print("live token present, prefix ok:", t.startswith("shippo_live_"))
def call(method, path, body=None):
    req = urllib.request.Request("https://api.goshippo.com" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "ShippoToken " + t, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {"error": "unparseable"}
FROM = {"Toronto": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="500 Murray Ross Pkwy", street2="Unit 207",
            city="North York", state="ON", zip="M3J 2Z3", country="CA", phone="+19544590398", email="rodam00001@gmail.com"),
        "Vancouver": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="1160 Haro St", street2="Unit 204",
            city="Vancouver", state="BC", zip="V6E 1G2", country="CA", phone="+19544590398", email="rodam00001@gmail.com")}
TO = dict(name="Amazon Fulfillment", company="Amazon", street1="13961 Campo Rd", street2="Unit 57", city="Jamul", state="CA", zip="91935",
          country="US", phone="+13054092425", email="rodam00001@gmail.com")
BOXES = [(18, 14, 12, 30), (16, 12, 10, 20), (12, 10, 8, 10)]
PARCELS = [dict(length=str(l), width=str(w), height=str(h), distance_unit="in", weight=str(g), mass_unit="lb") for l, w, h, g in BOXES]
ITEMS = [("Surface cleaner", 30, 27, "36.00", "3402.50"), ("Lotion", 20, 18, "48.00", "3304.99"), ("Bar", 10, 9, "22.00", "3401.11")]
CUSTOMS = {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products",
    "non_delivery_option": "RETURN", "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": "DDU", "invoice": "RATE-CHECK",
    "items": [dict(description=d, quantity=q, net_weight=str(w), mass_unit="lb", value_amount=v, value_currency="USD",
                   origin_country="US", tariff_number=tn) for d, q, w, v, tn in ITEMS]}
c, ca = call("GET", "/carrier_accounts/?results=100")
print("carrier accounts http", c)
accts = ca.get("results", [])
for a in accts:
    p = a.get("parameters") or {}
    print(f"  {a.get('carrier'):<12} id {a['object_id'][:8]} active={a.get('active')} test={a.get('test')} "
          f"account_id={str(a.get('account_id'))[:3]}*** country={p.get('account_country') or p.get('country') or '-'} shippo_managed={a.get('is_shippo_account')}")
for origin, frm in FROM.items():
    for a in accts:
        if not a.get("active") or a.get("test"): continue
        c, cd = call("POST", "/customs/declarations/", CUSTOMS)
        c, sh = call("POST", "/shipments/", {"address_from": frm, "address_to": TO, "parcels": PARCELS,
                     "customs_declaration": cd.get("object_id"), "carrier_accounts": [a["object_id"]], "async": False})
        rates = sorted(sh.get("rates", []), key=lambda r: float(r["amount"]))
        print(f"\n=== {origin} -> US | 3 boxes 60 lb | DDU | {a.get('carrier')} {a['object_id'][:8]} | http {c} | {len(rates)} rates")
        for m in sh.get("messages", []):
            tx = m.get("text") or ""
            if "RatedShipmentAlert" not in tx: print("   msg:", tx[:200])
        for r in rates: print(f"   {r['servicelevel']['name']:<34}{r['amount']:>9} {r['currency']}  {r.get('estimated_days')}d  provider {r.get('provider')}")
