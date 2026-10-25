"""Shippo TEST: full flow with the UPS Canada account only: 3 boxes, 3-category invoice, DDU/DDP, test label."""
import os, sys, json, re, urllib.request, urllib.error
t = os.environ.get("SHIPPO_API_KEY", "").strip()
if not t:
    for line in os.environ.get("CREDENTIALS_ENV", "").splitlines():
        m = re.match(r"\s*SHIPPO_(?:TEST_TOKEN|API_KEY|TOKEN)\s*=\s*(\S+)", line)
        if m: t = m.group(1).strip().strip('"\'')
if not t.startswith("shippo_test_"): print("no TEST token -> abort"); sys.exit(1)
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
TO = dict(name="Jessica Mejia", street1="13961 Campo Rd", street2="Unit 57", city="Jamul", state="CA", zip="91935",
          country="US", phone="+13054092425", email="rodam00001@gmail.com")
BOXES = [(18, 14, 12, 30), (16, 12, 10, 20), (12, 10, 8, 10)]
PARCELS = [dict(length=str(l), width=str(w), height=str(h), distance_unit="in", weight=str(g), mass_unit="lb") for l, w, h, g in BOXES]
ITEMS = [("Surface cleaner", 30, 27, "36.00", "3402.50"), ("Lotion", 20, 18, "48.00", "3304.99"), ("Bar", 10, 9, "22.00", "3401.11")]
def customs(inc):
    return {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products",
        "non_delivery_option": "RETURN", "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": inc, "invoice": "TEST-" + inc,
        "items": [dict(description=d, quantity=q, net_weight=str(w), mass_unit="lb", value_amount=v, value_currency="USD",
                       origin_country="US", tariff_number=tn) for d, q, w, v, tn in ITEMS]}
c, ca = call("GET", "/carrier_accounts/?results=100")
ups = [a["object_id"] for a in ca.get("results", []) if a.get("carrier") == "ups"]
print("UPS accounts:", [u[:8] for u in ups])
for origin, frm in FROM.items():
    for inc in ("DDU", "DDP"):
        for uid in ups:
            c, cd = call("POST", "/customs/declarations/", customs(inc))
            c, sh = call("POST", "/shipments/", {"address_from": frm, "address_to": TO, "parcels": PARCELS,
                         "customs_declaration": cd["object_id"], "carrier_accounts": [uid], "async": False})
            rates = sorted(sh.get("rates", []), key=lambda r: float(r["amount"]))
            print(f"\n=== {origin} -> Jamul | 3 boxes 60 lb | {inc} | UPS acct {uid[:8]} | http {c} | {len(rates)} rates")
            for m in sh.get("messages", []):
                tx = (m.get("text") or "")
                if "RatedShipmentAlert" not in tx: print("   msg:", tx[:200])
            for r in rates: print(f"   {r['servicelevel']['name']:<34}{r['amount']:>9} {r['currency']}  {r.get('estimated_days')}d")
            if rates and origin == "Toronto":
                c, tr = call("POST", "/transactions/", {"rate": rates[0]["object_id"], "label_file_type": "PDF", "async": False})
                print("   TEST LABEL:", c, tr.get("status"), "tracking", tr.get("tracking_number"), "label", bool(tr.get("label_url")),
                      "| commercial_invoice_url", bool(tr.get("commercial_invoice_url")),
                      "| msgs", [m.get("text", "")[:150] for m in tr.get("messages", [])][:4])
                if tr.get("commercial_invoice_url"):
                    try:
                        import urllib.request as u
                        os.makedirs("/tmp/so", exist_ok=True)
                        open(f"/tmp/so/invoice_{origin}_{inc}.pdf", "wb").write(u.urlopen(tr["commercial_invoice_url"], timeout=60).read())
                        print("   saved invoice pdf")
                    except Exception as e: print("   invoice download failed:", e)
