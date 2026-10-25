"""Shippo TEST-mode probe: Canada -> US rates (UPS / Canada Post / others), customs invoice, DDU vs DDP, test label.
Uses only the test token (aborts on anything else). Never prints the token."""
import os, sys, json, urllib.request, urllib.error, re

def token():
    t = os.environ.get("SHIPPO_API_KEY", "").strip()
    if not t:
        for line in os.environ.get("CREDENTIALS_ENV", "").splitlines():
            m = re.match(r"\s*SHIPPO_(?:TEST_TOKEN|API_KEY|TOKEN)\s*=\s*(\S+)", line)
            if m: t = m.group(1).strip().strip('"\'')
    return t

TOK = token()
if not TOK:
    print("NO TOKEN FOUND (env SHIPPO_API_KEY or CREDENTIALS_ENV SHIPPO_*)"); sys.exit(1)
if not TOK.startswith("shippo_test_"):
    print("token is not a TEST token -> aborting (this probe never uses a live token)"); sys.exit(1)

def call(method, path, body=None):
    req = urllib.request.Request("https://api.goshippo.com" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "ShippoToken " + TOK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {"error": "unparseable"}

FROM = {
 "Toronto": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="500 Murray Ross Pkwy", street2="#207",
     city="North York", state="ON", zip="M3J 2Z3", country="CA", phone="9544590398", email="rodam00001@gmail.com"),
 "Vancouver": dict(name="Rodolfo Antunes", company="Flipping Magic LLC", street1="1160 Haro St", street2="#204",
     city="Vancouver", state="BC", zip="V6E 1G2", country="CA", phone="9544590398", email="rodam00001@gmail.com"),
}
TO = dict(name="Jessica Mejia", street1="13961 Campo Rd", street2="Unit 57", city="Jamul", state="CA", zip="91935",
          country="US", phone="3054092425")
PARCELS = [dict(length="18", width="14", height="12", distance_unit="in", weight="30", mass_unit="lb"),
           dict(length="16", width="12", height="10", distance_unit="in", weight="20", mass_unit="lb"),
           dict(length="12", width="10", height="8", distance_unit="in", weight="10", mass_unit="lb")]
ITEMS = [("Surface cleaner", 30, 30, "36.00"), ("Lotion", 20, 20, "48.00"), ("Bar", 10, 10, "22.00")]

def customs(inc):
    return {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products",
        "non_delivery_option": "RETURN", "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": inc,
        "invoice": "TEST-" + inc,
        "items": [dict(description=d, quantity=q, net_weight=str(w), mass_unit="lb", value_amount=v,
                       value_currency="USD", origin_country="US") for d, q, w, v in ITEMS]}

out = {"runs": []}
print("== carrier accounts on this account ==")
c, ca = call("GET", "/carrier_accounts/?results=100")
for a in ca.get("results", []):
    print(f"  {a.get('carrier'):<22}{str(a.get('account_id'))[:34]:<36}active={a.get('active')} test={a.get('test')}")
for a in ca.get("results", []): pass

def show(x): print(json.dumps(x, indent=1)[:3000])
for pname, PARCELS_V in (("1 box", PARCELS[:1]), ("3 boxes", PARCELS)):
  for origin, frm in FROM.items():
    for inc in ("DDU", "DDP"):
          print(f"\n===== {origin} -> Jamul CA | {pname} | incoterm {inc} =====")
          c, cd = call("POST", "/customs/declarations/", customs(inc))
          print("customs declaration:", c, cd.get("object_state"), [m.get("text") for m in cd.get("messages", [])][:3])
          if c >= 300: out["runs"].append(dict(origin=origin, inc=inc, customs_error=cd)); show(cd); continue
          c, sh = call("POST", "/shipments/", {"address_from": frm, "address_to": TO, "parcels": PARCELS_V,
                                                "customs_declaration": cd["object_id"], "async": False})
          print("shipment:", c, sh.get("status"))
          rates = sh.get("rates", [])
          for m in [m for m in sh.get("messages", []) if "Carrier account" not in (m.get("text") or "") or "canada" in (m.get("text") or "").lower()]: print("  msg:", m.get("source"), "|", (m.get("text") or "")[:160])
          rows = []
          for r in sorted(rates, key=lambda r: float(r["amount"])):
              row = dict(provider=r["provider"], service=r["servicelevel"]["name"], amount=r["amount"], cur=r["currency"],
                         days=r.get("estimated_days"), id=r["object_id"])
              rows.append(row); print(f"  {row['provider']:<14}{row['service']:<38}{row['amount']:>9} {row['cur']}  {row['days']}d")
          rec = dict(origin=origin, inc=inc, status=sh.get("status"), rates=rows,
                     messages=[m.get("text") for m in sh.get("messages", [])])
          ups = [r for r in rows if r["provider"] == "UPS"]
          if ups and origin == "Toronto":
              c, t = call("POST", "/transactions/", {"rate": ups[0]["id"], "label_file_type": "PDF", "async": False})
              rec["label"] = dict(http=c, status=t.get("status"), tracking=t.get("tracking_number"),
                                  has_label=bool(t.get("label_url")), invoice_url=t.get("commercial_invoice_url"),
                                  msgs=[m.get("text") for m in t.get("messages", [])][:5])
              print("  test label:", rec["label"])
          out["runs"].append(rec)
os.makedirs("/tmp/so", exist_ok=True)
json.dump(out, open("/tmp/so/result.json", "w"), indent=1)
