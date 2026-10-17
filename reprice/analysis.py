"""Capital valuation + rotation/buy signals from stored state.  usage: python analysis.py -> state/signals.tsv and prints totals"""
import csv, json, os, datetime as dt, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(HERE, "state")
today = dt.date.today() if len(sys.argv) < 2 else dt.date.fromisoformat(sys.argv[1])
def f(x):
    try: return float(str(x).replace("$", "").replace(",", ""))
    except Exception: return 0.0
costs = {r["sku"]: r for r in csv.DictReader(open(os.path.join(HERE, "costs.tsv")), delimiter="\t")}
plan = {r["sku"]: r for r in csv.DictReader(open(os.path.join(S, "planning_latest.tsv"), encoding="utf-8", errors="replace"), delimiter="\t")}
dec = {}
for l in open(os.path.join(S, "decisions.jsonl")):
    j = json.loads(l); dec[j["sku"]] = j
sales = {}
for fn in sorted(os.listdir(S)):
    if fn.startswith("orders_"):
        for r in csv.DictReader(open(os.path.join(S, fn)), delimiter="\t"):
            q, p = f(r["quantity"]), f(r["item-price"])
            if q > 0 and not r["order-status"].startswith("Cancel"):
                sales.setdefault(r["sku"], []).append((r["purchase-date"][:10], q, p / q if p else None))
D = lambda k: (today - dt.timedelta(days=k)).isoformat()
rows, tot = [], dict(units=0, cost=0.0, cons=0.0, base=0.0, listed=0.0)
for sku, p in plan.items():
    c = costs.get(sku)
    known = c is not None
    if not c:
        c = {"cost": 0, "inv_fees": 0, "inv_price": 0, "group": "(not in sheet) " + p.get("product-name", "")}
    cost = f(c["cost"]); fees_t, invp = f(c["inv_fees"]), f(c["inv_price"])
    fba = max(0.0, fees_t - 0.15 * invp) if fees_t and invp else (3.5 if not known else 0.0)
    own = f(p.get("your-price")); d = dec.get(sku, {}); bb = d.get("bb") or 0
    h = sales.get(sku, [])
    def units(k): return sum(q for dd, q, _ in h if dd >= D(k))
    u30, u90, u120, u365 = units(30), units(90), units(120), units(365)
    sold180 = sorted(pp for dd, q, pp in h if dd >= D(180) and pp for _ in range(int(min(q, 5))))
    price_base = min([x for x in (bb, own) if x] or [0])
    if sold180 and len(sold180) >= 5:
        p25 = sold180[len(sold180) // 4]
        # base: market price, but not above what really sold (median); conservative: lower quartile of real sales
        price_base = min(price_base or 9e9, st.median(sold180)) if price_base else st.median(sold180)
        price_cons = min(price_base, p25)
    else:
        price_cons = price_base * 0.85
    avail = f(p.get("available")); resv = f(p.get("Total Reserved Quantity")); inb = f(p.get("inbound-quantity")); unf = f(p.get("unfulfillable-quantity"))
    sellable = avail + resv + inb
    vel = max(u90 / 90.0, u30 / 30.0 * 0.5 + u90 / 90.0 * 0.5) if (u90 or u30) else 0.0     # units/day, blended
    cover = sellable / vel if vel > 0 else (999 if sellable else 0)
    def net(pr): return max(0.0, pr - 0.15 * pr - fba) if pr else 0.0
    # liquidation haircut: stock beyond 120 days of cover is valued at 85% (needs discounting), beyond 270 days at 65%, no sales in 6 months at 50%
    n_norm = min(sellable, vel * 120) if vel > 0 else 0.0
    n_mid = min(max(sellable - n_norm, 0), vel * 150) if vel > 0 else 0.0
    n_old = max(sellable - n_norm - n_mid, 0) if vel > 0 else sellable
    old_f = 0.65 if vel > 0 else 0.50
    cons = net(price_cons) * (n_norm + 0.85 * n_mid + old_f * n_old)
    base = net(price_base) * sellable
    prof_unit = net(price_cons) - cost
    # buy signal: target cover 45-75 days at the real velocity
    monthly = vel * 30
    if sellable == 0 and vel > 0: sig = "BUY (out of stock, sells %.1f/mo)" % monthly
    elif vel == 0 and sellable > 0: sig = "STOP buying - no sales 90d"
    elif cover > 150: sig = "STOP buying (%.0f d cover)" % cover
    elif cover > 90: sig = "BUY LESS (%.0f d cover)" % cover
    elif cover < 30 and prof_unit > 1: sig = "BUY MORE (%.0f d cover)" % cover
    else: sig = "OK (%.0f d cover)" % cover
    rows.append([sku, c["group"][:40], int(sellable), round(vel * 30, 1), round(cover), cost, round(price_base, 2), round(price_cons, 2), round(prof_unit, 2), round(cons, 2), round(base, 2), sig, int(unf)])
    tot["units"] += sellable; tot["cost"] += cost * sellable; tot["cons"] += cons; tot["base"] += base; tot["listed"] += own * sellable
rows.sort(key=lambda r: -r[9])
with open(os.path.join(S, "signals.tsv"), "w", newline="") as fh:
    w = csv.writer(fh, delimiter="\t"); w.writerow("sku group sellable_units sold_per_month days_cover cost price_base price_cons profit_unit_cons value_cons value_base signal unfulfillable".split()); w.writerows(rows)
print("units to sell %d | cost paid %.0f | at your listed prices %.0f | net payout base %.0f | net payout conservative %.0f" % (tot["units"], tot["cost"], tot["listed"], tot["base"], tot["cons"]))
import collections
print(collections.Counter(r[11].split(" (")[0] for r in rows))
