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
# state centroids (lat, lon) - only used to compare how far two options are from the shipping origin
CENT = {"AL": (32.8, -86.8), "AR": (34.9, -92.4), "AZ": (34.3, -111.7), "CA": (37.2, -119.5), "CO": (39.0, -105.5), "CT": (41.6, -72.7),
        "DC": (38.9, -77.0), "DE": (39.0, -75.5), "FL": (28.6, -82.4), "GA": (32.7, -83.4), "IA": (42.1, -93.5), "ID": (44.4, -114.6),
        "IL": (40.0, -89.2), "IN": (39.9, -86.3), "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.1, -92.0), "MA": (42.3, -71.8),
        "MD": (39.0, -76.8), "ME": (45.4, -69.2), "MI": (44.3, -85.4), "MN": (46.3, -94.3), "MO": (38.4, -92.5), "MS": (32.7, -89.7),
        "MT": (47.0, -109.6), "NC": (35.6, -79.4), "ND": (47.5, -100.5), "NE": (41.5, -99.8), "NH": (43.7, -71.6), "NJ": (40.2, -74.7),
        "NM": (34.4, -106.1), "NV": (39.3, -116.6), "NY": (42.9, -75.5), "OH": (40.3, -82.8), "OK": (35.6, -97.5), "OR": (43.9, -120.6),
        "PA": (40.9, -77.8), "RI": (41.7, -71.5), "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3),
        "UT": (39.3, -111.7), "VA": (37.5, -78.9), "VT": (44.1, -72.7), "WA": (47.4, -120.6), "WI": (44.6, -89.9), "WV": (38.6, -80.6),
        "WY": (43.0, -107.5), "AK": (64.0, -152.0), "HI": (20.8, -156.3)}
ORIGIN_LL = {"toronto": (43.77, -79.41), "vancouver": (49.28, -123.12)}
CLOSER_MARGIN = 0.05            # Central must be at least 5% closer than the target region to count as "closer"


def _km(a, b):
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def distance_km(origin, option):
    """average distance origin -> destination states of an option, weighted by the weight of each shipment"""
    o = ORIGIN_LL[origin.strip().lower()]
    tot = w = 0.0
    for s in option["shipments"]:
        ll = CENT.get((s["state"] or "").upper())
        if not ll: raise RuntimeError("unknown destination state %r (%s)" % (s["state"], s.get("warehouse")))
        wt = sum(float(b["weight"]["value"]) * int(b.get("quantity", 1)) for b in s.get("boxes", [])) or 1.0
        tot += _km(o, ll) * wt; w += wt
    return tot / w


def candidates(origin, options):
    """Returns (region_option, central_option, notes).  region_option = cheapest-fee option made only of the target region
    (or target+Central if none is pure); central_option = cheapest-fee option made only of Central.  Either can be None."""
    target = TARGET_REGION.get(origin.strip().lower())
    if not target:
        raise RuntimeError("unknown origin '%s' (expected Toronto or Vancouver)" % origin)
    pure, mixed, central, notes = [], [], [], []
    for o in options:
        regs = [region_of(s["state"]) for s in o["shipments"]]
        kind = ("pure" if regs and all(r == target for r in regs) else "central" if regs and all(r == "CENTRAL" for r in regs)
                else "mixed" if regs and all(r in (target, "CENTRAL") for r in regs) else "no")
        {"pure": pure, "central": central, "mixed": mixed}.get(kind, []).append(o)
        notes.append("%s fee %.2f  %s  -> %s" % (o["id"][:8], o["fee"], "+".join("%s(%s)" % (s["warehouse"], r) for s, r in zip(o["shipments"], regs)),
                                                  {"pure": "all " + target, "central": "all CENTRAL", "mixed": "mixed " + target + "/CENTRAL", "no": "outside region"}[kind]))
    cheapest = lambda l: min(l, key=lambda o: o["fee"]) if l else None
    return (cheapest(pure) or cheapest(mixed)), cheapest(central), notes


def decide(origin, region_opt, region_total, central_opt, central_total):
    """your rule: ship to the closest location; if Central is not closer than the target region, take Central only when it is cheaper
    (placement fee + UPS).  Returns (option, reason)."""
    if region_opt and not central_opt: return region_opt, "only the target region is available"
    if central_opt and not region_opt: return central_opt, "target region not available, Central used"
    if not region_opt: return None, "no option in the target region or Central"
    dr, dc = distance_km(origin, region_opt), distance_km(origin, central_opt)
    if dc < dr * (1 - CLOSER_MARGIN):
        return central_opt, "Central is closer (%.0f km vs %.0f km)" % (dc, dr)
    if central_total < region_total:
        return central_opt, "Central is not closer (%.0f km vs %.0f km) but cheaper ($%.2f vs $%.2f)" % (dc, dr, central_total, region_total)
    return region_opt, "target region is as close or closer (%.0f km vs %.0f km) and Central is not cheaper ($%.2f vs $%.2f)" % (dr, dc, region_total, central_total)


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
def to_address(sh):
    a = sh["address"]
    return {"name": "Amazon Receiving", "company": "Amazon.com Services LLC - " + str(sh["warehouse"]), "street1": a.get("addressLine1", ""),
            "street2": a.get("addressLine2", ""), "city": a.get("city", ""), "state": a.get("stateOrProvinceCode", ""),
            "zip": a.get("postalCode", ""), "country": a.get("countryCode", "US"), "phone": AMAZON_PHONE, "email": "flippingmagic.sales@gmail.com"}


def customs_for(sh, cats, test, parcels):
    counts = customs_items(sh, cats, test)
    total_lb = sum(float(p["weight"]) for p in parcels); units = sum(counts.values())
    items = []
    for cat, q in counts.items():
        desc, tn = HTS[cat]
        items.append({"description": desc, "quantity": q, "net_weight": "%.2f" % max(0.01, total_lb * 0.9 * q / units), "mass_unit": "lb",
                      "value_amount": "%.2f" % (DECLARED[cat] * q), "value_currency": "USD", "origin_country": "US", "tariff_number": tn})
    return {"contents_type": "MERCHANDISE", "contents_explanation": "Household cleaning and personal care products", "non_delivery_option": "RETURN",
            "certify": True, "certify_signer": "Rodolfo Antunes", "incoterm": "DDU", "items": items}, counts, total_lb, units


def parcels_of(sh):
    return [{"length": str(b["dimensions"]["length"]), "width": str(b["dimensions"]["width"]), "height": str(b["dimensions"]["height"]), "distance_unit": "in",
             "weight": str(b["weight"]["value"]), "mass_unit": "lb"} for b in sh["boxes"] for _ in range(int(b.get("quantity", 1)))]


def rate_option(sp, accounts, frm, option, cats, test, usd_per_cad):
    """Shippo quote (no purchase) for every Amazon shipment of an option"""
    legs = []
    for sh in option["shipments"]:
        to = to_address(sh); parcels = parcels_of(sh)
        customs, counts, total_lb, units = customs_for(sh, cats, test, parcels)
        rate = sp.rates(frm, to, parcels, customs, accounts)
        if not rate: raise RuntimeError("Shippo returned no UPS rate for %s (%s)" % (sh["warehouse"], to["zip"]))
        amt = float(rate["amount"]); cur = rate["currency"]
        legs.append({"shipmentId": sh["shipmentId"], "warehouse": sh["warehouse"], "address": sh["address"], "boxes": len(parcels), "lb": total_lb,
                     "units": units, "counts": counts, "service": rate["servicelevel"]["name"], "rate_id": rate["object_id"],
                     "shippo_shipment": rate["_shipment"], "shippo_account": rate["_account"], "amount": amt, "currency": cur,
                     "usd": round(amt * (usd_per_cad if cur == "CAD" else 1.0), 2), "estimated_days": rate.get("estimated_days")})
    return legs


def prepare(path, test=False, say=print):
    name, origin, boxes, cells, exp = S.read_send_file(path)
    cats = read_categories(path)
    c = S._credentials()
    r = S.send_to_amazon(path, say=say, cancel_after=False, placement=True)
    pid = r["inboundPlanId"]
    keep = False
    try:
        options = amazon_options(c, pid)
        if not options: raise RuntimeError("Amazon returned no placement option")
        reg, cen, notes = candidates(origin, options)
        for n in notes: say("   option " + n)
        fallback = False
        if not reg and not cen:
            # Amazon offered nothing in the target region or Central: do not stop - take the option that is closest to the origin
            # (fee as tie-break) and say so clearly in the message; the YES / NO box is still the decision of the owner.
            reg = min(options, key=lambda o: (round(distance_km(origin, o)), o["fee"]))
            fallback = True
        sp = Shippo(); accounts = sp.ups_accounts()
        if not accounts: raise RuntimeError("no active UPS account in Shippo")
        frm = ship_from_addr(origin)
        usd_per_cad, fx_src = fx_usd_per_cad()
        quotes = {}
        for key, opt in (("region", reg), ("central", cen)):
            if opt: quotes[key] = rate_option(sp, accounts, frm, opt, cats, test, usd_per_cad)
        tot = lambda k: quotes[k] and (reg if k == "region" else cen)["fee"] + sum(l["usd"] for l in quotes[k])
        chosen, why = decide(origin, reg, tot("region") if reg else None, cen, tot("central") if cen else None)
        if fallback:
            why = ("Amazon offered NO %s or Central option for this plan; the closest one it offered is used (%.0f km) - check the destinations before saying YES"
                   % (TARGET_REGION[origin.lower()].title(), distance_km(origin, reg)))
        legs = quotes["region" if chosen is reg else "central"]
        say("   decision: " + why)
        fee = chosen["fee"]; ups_usd = round(sum(l["usd"] for l in legs), 2)
        avg, n = history_average(origin)
        warn = ""
        if avg and n >= 3 and ups_usd > avg * (1 + MAX_OVER_AVERAGE):
            warn = "UPS cost is %.0f%% above the average of your last %d %s shipments ($%.2f)" % ((ups_usd / avg - 1) * 100, n, origin, avg)
        state = {"origin": origin, "name": name, "planId": pid, "placementOptionId": chosen["id"], "why": why, "feeUSD": fee,
                 "legs": legs, "upsUSD": ups_usd, "fx": {"usd_per_cad": usd_per_cad, "source": fx_src}, "warning": warn,
                 "expires": chosen["expires"], "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "sendFile": os.path.abspath(path), "test": bool(test)}
        out = os.path.splitext(path)[0] + "_stage1.json"
        json.dump(state, open(out, "w"), indent=1)
        msg = "Amazon FBA Placement Fees: $%.2f\nUPS Shipment Cost: $%.2f  (approx. USD; Shippo quotes %s)\n" % (
            fee, ups_usd, " + ".join("%.2f %s" % (l["amount"], l["currency"]) for l in legs))
        msg += "Ships to: " + ", ".join("%s (%s, %s)" % (l["warehouse"], l["address"].get("city"), l["address"].get("stateOrProvinceCode")) for l in legs)
        msg += "\nWhy: " + why
        if warn: msg += "\nNOTE: " + warn
        msg += "\n\nComplete Shipment?"
        open(os.path.splitext(path)[0] + "_message.txt", "w", encoding="utf-8").write(msg)
        say("\n" + msg)
        say("(state saved: %s; FX %s %.4f)" % (out, fx_src, usd_per_cad))
        keep = not test
        return state
    finally:
        if test or not keep:      # a test run, or any failure: never leave an open plan behind
            try: S._api(c, "PUT", S.INB + "/inboundPlans/%s/cancellation" % pid); say("plan cancelled: " + pid)
            except Exception as e: say("CANCEL FAILED %s %s" % (pid, str(e)[:200]))


def cancel(state_path, say=print):
    """No: cancel the Amazon plan, nothing was bought"""
    st = json.load(open(state_path)); c = S._credentials()
    S._api(c, "PUT", S.INB + "/inboundPlans/%s/cancellation" % st["planId"])
    say("Amazon plan %s cancelled. Nothing was bought." % st["planId"])
    os.replace(state_path, state_path + ".cancelled")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) == 2 and a[0] == "prepare":
        try:
            prepare(a[1], test="--test" in sys.argv)
        except Exception as e:
            print("ERROR: " + str(e)); sys.exit(1)
    else:
        print(__doc__)
