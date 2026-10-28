#!/usr/bin/env python3
"""
fba_ship.py - Stage 1 of the Toronto / Vancouver shipment pipeline (READ ONLY toward money: it buys nothing).

  python fba_ship.py prepare  send.tsv  [--test]
      1. creates the Amazon inbound plan from the workbook's send file (same file as sd_tools.py inbound)
      2. picks the placement option by REGION (Vancouver -> West, Toronto -> East, otherwise Central; never "cheapest")
      3. reads, per Amazon shipment: destination warehouse + address, boxes (weight/size), units
      4. asks Shippo (UPS Canada account) for rates for exactly those boxes, takes the cheapest, converts CAD -> USD
      5. writes  <name>_stage1.json  (everything Stage 2 needs) and prints the message-box text
      --test : cancel the Amazon plan afterwards and use made-up categories for products without a CAT line

send.tsv is the usual file (NAME / CITY / BOX / ITEM lines) plus, written by the workbook:
      CAT <TAB> sku <TAB> Cleaner|Bar|Lotion        (one line per product; every product that ships needs one)
"""
import json, os, re, sys, time, urllib.request, urllib.error
import sd_tools as S

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- configuration (edit here, nothing else needs to change)
TARGET_REGION = {"vancouver": "WEST", "toronto": "EAST"}      # the rule you gave; fallback is always CENTRAL
EAST = set("ME NH VT MA RI CT NY NJ PA DE MD DC VA WV NC SC GA FL OH".split())
CENTRAL = set("AL MS TN KY IN IL WI MI MN IA MO AR LA OK KS NE SD ND TX".split())
# every other US state (CA AZ NV OR WA UT ID MT WY CO NM AK HI) is WEST
DECLARED = {"Cleaner": 1.79, "Bar": 1.63, "Lotion": 2.19}      # USD per unit, the lowest values you use
SHIPPO_UPS_CANADA_ACCOUNT_PREFIX = ""                           # "" = try every active UPS account and keep the ones that return rates
FALLBACK_USDCAD = 1.40                                          # only used if the Bank of Canada rate cannot be fetched
MAX_OVER_AVERAGE = 0.50                                         # warn when the UPS cost is >50% above the average of past shipments
AMAZON_PHONE = "+13054092425"


def region_of(state):
    s = (state or "").upper()
    return "EAST" if s in EAST else "CENTRAL" if s in CENTRAL else "WEST"


# ---------------------------------------------------------------- placement option choice
def choose_option(origin, options):
    """options: [{id, fee, shipments:[{state, warehouse, ...}]}].  Returns (chosen_or_None, tier, ranking_notes)."""
    target = TARGET_REGION.get(origin.strip().lower())
    if not target:
        raise RuntimeError("unknown origin '%s' (expected Toronto or Vancouver)" % origin)
    tiers = []
    for o in options:
        regs = [region_of(s["state"]) for s in o["shipments"]]
        if regs and all(r == target for r in regs): t = 1
        elif regs and all(r == "CENTRAL" for r in regs): t = 2
        elif regs and all(r in (target, "CENTRAL") for r in regs): t = 3
        else: t = 9
        tiers.append((t, o["fee"], o, regs))
    tiers.sort(key=lambda x: (x[0], x[1]))
    notes = ["%s fee %.2f  %s  -> %s" % (o["id"][:8], o["fee"], "+".join("%s(%s)" % (s["warehouse"], r) for s, r in zip(o["shipments"], regs)),
                                         {1: "all %s" % target, 2: "all CENTRAL (fallback)", 3: "mixed %s/CENTRAL" % target, 9: "not acceptable"}[t])
             for t, _, o, regs in tiers]
    best = tiers[0]
    if best[0] == 9:
        return None, 9, notes
    return best[2], best[0], notes


# ---------------------------------------------------------------- Amazon side
def amazon_options(c, pid):
    opts = S._paged(c, S.INB + "/inboundPlans/%s/placementOptions" % pid, "placementOptions")
    out = []
    for o in opts:
        fee = sum(float(f["value"]["amount"]) for f in (o.get("fees") or []) if f.get("value"))
        ships = []
        for sid in o.get("shipmentIds") or []:
            sh = S._api(c, "GET", S.INB + "/inboundPlans/%s/shipments/%s" % (pid, sid))
            a = (sh.get("destination") or {}).get("address") or {}
            boxes = S._paged(c, S.INB + "/inboundPlans/%s/shipments/%s/boxes" % (pid, sid), "boxes")
            items = S._paged(c, S.INB + "/inboundPlans/%s/shipments/%s/items" % (pid, sid), "items")
            ships.append({"shipmentId": sid, "warehouse": (sh.get("destination") or {}).get("warehouseId") or a.get("name"),
                          "address": a, "state": a.get("stateOrProvinceCode"), "boxes": boxes, "items": items})
        out.append({"id": o["placementOptionId"], "fee": fee, "currency": "USD", "expires": o.get("expiration"), "shipments": ships})
    return out


# ---------------------------------------------------------------- categories / customs
def read_categories(path):
    cats = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            p = line.rstrip("\r\n").split("\t")
            if len(p) >= 3 and p[0].upper() == "CAT" and p[1].strip():
                cats[p[1].strip()] = p[2].strip().title()
    return cats


def customs_items(shipment, cats, test):
    counts = {}
    missing = []
    for it in shipment["items"]:
        cat = cats.get(it["msku"])
        if not cat:
            if test: cat = ["Cleaner", "Bar", "Lotion"][sum(map(ord, it["msku"])) % 3]
            else: missing.append(it["msku"]); continue
        if cat not in DECLARED:
            raise RuntimeError("category '%s' for %s is not one of %s" % (cat, it["msku"], "/".join(DECLARED)))
        counts[cat] = counts.get(cat, 0) + int(it["quantity"])
    if missing:
        raise RuntimeError("these products have no category (Cleaner/Bar/Lotion) in the send file: " + ", ".join(sorted(set(missing))))
    return counts


HTS = {"Cleaner": ("Liquid household surface cleaner, non-edible cleaning preparation", "3402.20"),
       "Bar": ("Toilet soap bar, non-medicated, non-edible, retail packaged", "3401.11"),
       "Lotion": ("Liquid personal soap for skin cleansing and conditioning, non-medicated, non-edible, retail packaged", "3304.99")}


# ---------------------------------------------------------------- Shippo
class Shippo:
    def __init__(self):
        t = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip()
        if not t:
            blob = os.environ.get("CREDENTIALS_ENV", "")
            for folder in (HERE, "C:\\AmazonFeed"):
                for fn in ("credentials.txt", "credentials.env"):
                    fp = os.path.join(folder, fn)
                    if os.path.exists(fp): blob += "\n" + open(fp, encoding="utf-8-sig").read()
            for line in blob.splitlines():
                m = re.match(r"\s*SHIPPO_\w*\s*=\s*[\"']?(shippo_live_\S+?)[\"']?\s*$", line)
                if m: t = m.group(1)
        if not t.startswith("shippo_live_"):
            raise RuntimeError("no live Shippo token found (add SHIPPO_LIVE_TOKEN=shippo_live_... to credentials.txt)")
        self.t = t

    def call(self, method, path, body=None):
        req = urllib.request.Request("https://api.goshippo.com" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "ShippoToken " + self.t, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError("Shippo answered HTTP %s on %s: %s" % (e.code, path, e.read().decode(errors="replace")[:500]))

    def ups_accounts(self):
        r = self.call("GET", "/carrier_accounts/?results=100&carrier=ups")
        return [a for a in r.get("results", []) if a.get("active") and not a.get("test")
                and a["object_id"].startswith(SHIPPO_UPS_CANADA_ACCOUNT_PREFIX)]

    def rates(self, frm, to, parcels, customs, accounts):
        decl = self.call("POST", "/customs/declarations/", customs)
        best = None
        for a in accounts:
            sh = self.call("POST", "/shipments/", {"address_from": frm, "address_to": to, "parcels": parcels,
                                                   "customs_declaration": decl["object_id"], "carrier_accounts": [a["object_id"]], "async": False})
            for r in sh.get("rates", []):
                r["_shipment"] = sh["object_id"]; r["_account"] = a["object_id"]
                if best is None or float(r["amount"]) < float(best["amount"]): best = r
        return best


def fx_usd_per_cad():
    try:
        with urllib.request.urlopen("https://www.bankofcanada.ca/valet/observations/FXCADUSD/json?recent=1", timeout=20) as r:
            j = json.loads(r.read())
        return float(j["observations"][-1]["FXCADUSD"]["v"]), "Bank of Canada " + j["observations"][-1]["d"]
    except Exception:
        fp = os.path.join(HERE, "fx_cache.json")
        if os.path.exists(fp):
            d = json.load(open(fp)); return d["usd_per_cad"], "saved rate " + d.get("date", "?")
        return 1.0 / FALLBACK_USDCAD, "built-in fallback %.2f" % FALLBACK_USDCAD


def ship_from_addr(origin):
    a = S.ship_from(origin)
    return {"name": "Rodolfo Antunes", "company": "Flipping Magic LLC", "street1": a["addressLine1"], "street2": a.get("addressLine2", ""),
            "city": a["city"], "state": a["stateOrProvinceCode"], "zip": a["postalCode"], "country": a["countryCode"],
            "phone": "+1" + re.sub(r"\D", "", a["phoneNumber"])[-10:], "email": "flippingmagic.sales@gmail.com"}


def history_average(origin):
    fp = os.path.join(HERE, "ship_history.json")
    if not os.path.exists(fp): return None, 0
    rows = [r for r in json.load(open(fp)) if r.get("origin", "").lower() == origin.lower()]
    if not rows: return None, 0
    return sum(r["usd_total"] for r in rows) / len(rows), len(rows)


# ---------------------------------------------------------------- stage 1
def prepare(path, test=False, say=print):
    name, origin, boxes, cells, exp = S.read_send_file(path)
    cats = read_categories(path)
    c = S._credentials()
    r = S.send_to_amazon(path, say=say, cancel_after=False, placement=True)
    pid = r["inboundPlanId"]
    try:
        options = amazon_options(c, pid)
        if not options: raise RuntimeError("Amazon returned no placement option")
        chosen, tier, notes = choose_option(origin, options)
        for n in notes: say("   option " + n)
        if not chosen:
            raise RuntimeError("no placement option is in the %s / Central region. Options Amazon gave:\n   %s" % (TARGET_REGION[origin.lower()].title(), "\n   ".join(notes)))
        sp = Shippo(); accounts = sp.ups_accounts()
        if not accounts: raise RuntimeError("no active UPS account in Shippo")
        frm = ship_from_addr(origin)
        usd_per_cad, fx_src = fx_usd_per_cad()
        legs = []
        for sh in chosen["shipments"]:
            a = sh["address"]
            to = {"name": "Amazon Receiving", "company": "Amazon.com Services LLC - " + str(sh["warehouse"]), "street1": a.get("addressLine1", ""),
                  "street2": a.get("addressLine2", ""), "city": a.get("city", ""), "state": a.get("stateOrProvinceCode", ""),
                  "zip": a.get("postalCode", ""), "country": a.get("countryCode", "US"), "phone": AMAZON_PHONE, "email": "flippingmagic.sales@gmail.com"}
            parcels = [{"length": str(b["dimensions"]["length"]), "width": str(b["dimensions"]["width"]), "height": str(b["dimensions"]["height"]), "distance_unit": "in",
                        "weight": str(b["weight"]["value"]), "mass_unit": "lb"} for b in sh["boxes"] for _ in range(int(b.get("quantity", 1)))]
            counts = customs_items(sh, cats, test)
            total_lb = sum(float(p["weight"]) for p in parcels); units = sum(counts.values())
            items = []
            for cat, q in counts.items():
                desc, tn = HTS[cat]
                items.append({"description": desc, "quantity": q, "net_weight": "%.2f" % max(0.01, total_lb * 0.9 * q / units), "mass_unit": "lb",
                              "value_amount": "%.2f" % (DECLARED[cat] * q), "value_currency": "USD", "origin_country": "US", "tariff_number": tn})
            customs = {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products", "non_delivery_option": "RETURN",
                       "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": "DDU", "items": items}
            rate = sp.rates(frm, to, parcels, customs, accounts)
            if not rate: raise RuntimeError("Shippo returned no UPS rate for %s (%s)" % (sh["warehouse"], to["zip"]))
            cad_or_usd = float(rate["amount"]); cur = rate["currency"]
            usd = cad_or_usd * (usd_per_cad if cur == "CAD" else 1.0)
            legs.append({"shipmentId": sh["shipmentId"], "warehouse": sh["warehouse"], "address": a, "boxes": len(parcels), "lb": total_lb,
                         "units": units, "counts": counts, "service": rate["servicelevel"]["name"], "rate_id": rate["object_id"],
                         "shippo_shipment": rate["_shipment"], "shippo_account": rate["_account"],
                         "amount": cad_or_usd, "currency": cur, "usd": round(usd, 2), "estimated_days": rate.get("estimated_days")})
        fee = chosen["fee"]; ups_usd = round(sum(l["usd"] for l in legs), 2)
        avg, n = history_average(origin)
        warn = ""
        if avg and n >= 3 and ups_usd > avg * (1 + MAX_OVER_AVERAGE):
            warn = "UPS cost is %.0f%% above the average of your last %d %s shipments ($%.2f)" % ((ups_usd / avg - 1) * 100, n, origin, avg)
        state = {"origin": origin, "name": name, "planId": pid, "placementOptionId": chosen["id"], "tier": tier, "feeUSD": fee,
                 "legs": legs, "upsUSD": ups_usd, "fx": {"usd_per_cad": usd_per_cad, "source": fx_src}, "warning": warn,
                 "expires": chosen["expires"], "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        out = os.path.splitext(path)[0] + "_stage1.json"
        json.dump(state, open(out, "w"), indent=1)
        msg = "Amazon FBA Placement Fees: $%.2f\nUPS Shipment Cost: $%.2f  (approx. USD; Shippo quotes %s)\n" % (
            fee, ups_usd, " + ".join("%.2f %s" % (l["amount"], l["currency"]) for l in legs))
        msg += "Ships to: " + ", ".join("%s (%s, %s)" % (l["warehouse"], l["address"].get("city"), l["address"].get("stateOrProvinceCode")) for l in legs)
        if warn: msg += "\nNOTE: " + warn
        msg += "\n\nComplete Shipment?"
        say("\n" + msg)
        say("(state saved: %s; FX %s %.4f)" % (out, fx_src, usd_per_cad))
        return state
    finally:
        if test:
            try: S._api(c, "PUT", S.INB + "/inboundPlans/%s/cancellation" % pid); say("test plan cancelled: " + pid)
            except Exception as e: say("CANCEL FAILED %s %s" % (pid, str(e)[:200]))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) == 2 and a[0] == "prepare":
        try:
            prepare(a[1], test="--test" in sys.argv)
        except Exception as e:
            print("ERROR: " + str(e)); sys.exit(1)
    else:
        print(__doc__)
