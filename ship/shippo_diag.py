"""Shippo TEST diagnostics: per-carrier-account rate attempts, exact messages, E.164 phones, consistent customs weights, US control."""
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
TOR = dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="500 Murray Ross Pkwy", street2="Unit 207",
    city="North York", state="ON", zip="M3J 2Z3", country="CA", phone="+19544590398", email="rodam00001@gmail.com")
JAM = dict(name="Jessica Mejia", street1="13961 Campo Rd", street2="Unit 57", city="Jamul", state="CA", zip="91935",
    country="US", phone="+13054092425", email="rodam00001@gmail.com")
def parcel(w): return dict(length="18", width="14", height="12", distance_unit="in", weight=str(w), mass_unit="lb")
def customs(inc, w):
    return {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning products", "non_delivery_option": "RETURN",
        "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": inc,
        "items": [dict(description="Surface cleaner", quantity=10, net_weight=str(w), mass_unit="lb", value_amount="60.00",
                       value_currency="USD", origin_country="US", tariff_number="3402.50")]}
c, ca = call("GET", "/carrier_accounts/?results=100")
accts = ca.get("results", [])
print("== carrier accounts ==")
for a in accts:
    print(" ", a.get("carrier"), a.get("object_id"), "active", a.get("active"), "test", a.get("test"), json.dumps(a.get("parameters", {}))[:200])
def attempt(label, frm, to, accts_ids, w=20, inc="DDU", cur=None):
    cc, cd = call("POST", "/customs/declarations/", customs(inc, w)) if frm["country"] != to["country"] else (0, {})
    body = {"address_from": frm, "address_to": to, "parcels": [parcel(w)], "async": False}
    if cd.get("object_id"): body["customs_declaration"] = cd["object_id"]
    if accts_ids: body["carrier_accounts"] = accts_ids
    c, sh = call("POST", "/shipments/", body)
    print(f"\n--- {label} | http {c} | customs {cc} {cd.get('object_state','')}")
    if c >= 300: print("   ERROR BODY:", json.dumps(sh)[:700]); return
    for m in sh.get("messages", []): print("   msg:", m.get("source"), "|", (m.get("text") or "")[:220])
    for r in sorted(sh.get("rates", []), key=lambda r: float(r["amount"])):
        print(f"   RATE {r['provider']:<12}{r['servicelevel']['name']:<36}{r['amount']:>8} {r['currency']} {r.get('estimated_days')}d")
    if cur and sh.get("object_id"):
        c2, rr = call("GET", f"/shipments/{sh['object_id']}/rates/{cur}")
        for r in rr.get("results", [])[:8]: print(f"   RATE[{cur}] {r['provider']:<12}{r['servicelevel']['name']:<36}{r['amount']:>8} {r['currency']}")
print("\n##### CONTROL: US -> US")
US_FROM = dict(JAM, name="Rodolfo Antunes", company="Flipping Magic LLC", phone="+19544590398")
US_TO = dict(name="Test Receiver", street1="215 Clayton St", city="San Francisco", state="CA", zip="94117", country="US", phone="+14155550123")
attempt("US->US all accounts", US_FROM, US_TO, None, 20)
print("\n##### Canada -> US, each carrier account alone")
for a in accts:
    if a.get("carrier") in ("ups", "canada_post", "fedex", "dhl_express", "usps"):
        attempt(f"Toronto->Jamul via {a['carrier']} {a['object_id'][:8]}", TOR, JAM, [a["object_id"]], 20, "DDU", "CAD")
print("\n##### Canada -> Canada (domestic) control")
TO_CA = dict(name="Test Receiver", street1="100 Queen St W", city="Toronto", state="ON", zip="M5H 2N2", country="CA", phone="+14165550123")
attempt("Toronto->Toronto all accounts", TOR, TO_CA, None, 20)
