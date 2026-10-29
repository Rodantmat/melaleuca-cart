#!/usr/bin/env python3
"""
demand.py - the real sales speed of every product, corrected for the days it was OUT OF STOCK.

Why: units / 90 days is wrong for a product that was empty for part of that time (it could not sell), so the order planner
under-orders exactly the products that run out - and then they run out again.  Measured on October 2026: 80 of 150 products
had an outage and for those the real demand was ~38 % higher than the naive number.

  compute(state_dir, today, current)  ->  {sku: {...columns...}}
     state_dir : folder with orders_YYYY-MM.tsv and ledger_YYYY-MM.tsv (written by reprice/history.py)
     current   : optional {sku: sellable_units_now}  (to flag products that are empty today)

Columns produced (all go into the feed's planning_Z.tsv, the Excel reads them by name):
     dem_rate        units per in-stock day (blend of 30 and 90 days, shrunk towards the naive rate when the evidence is thin)
     dem_naive       the old number (units/day over the calendar days) for comparison
     dem_instock_90  days with stock in the last 90 days that the ledger covers
     dem_out_now     consecutive days (up to today) without sellable stock; 0 = in stock
     dem_urgent      2 = out of stock now and it sells, 1 = (stock + inbound) covers less than 14 days, 0 = fine
     dem_cover_days  (sellable + inbound) / dem_rate
"""
import csv, datetime as dt, glob, os, sys

SHRINK_DAYS = 6.0          # weight of the naive prior, in days: with 3 in-stock days the prior still counts for 2/3
MAX_UPLIFT = 2.5           # the corrected rate is never more than 2.5x the naive one
MIN_RATE = 0.03            # units/day (about 1 a month) below which a product is not 'selling'
URGENT_COVER_DAYS = 14


def _rd(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _num(x, d=0.0):
    try: return float(str(x).replace(",", ""))
    except Exception: return d


def load(state_dir):
    """-> (sold {sku: {date: units}}, stock {sku: {date: in_stock_bool}})"""
    sold, stock = {}, {}
    for fn in sorted(glob.glob(os.path.join(state_dir, "orders_*.tsv"))):
        for r in _rd(fn):
            if (r.get("order-status") or "").lower().startswith("cancel"): continue
            try: d = dt.date.fromisoformat(r["purchase-date"][:10]); q = int(float(r["quantity"]))
            except Exception: continue
            sold.setdefault(r["sku"], {}).setdefault(d, 0)
            sold[r["sku"]][d] += q
    for fn in sorted(glob.glob(os.path.join(state_dir, "ledger_*.tsv"))):
        for r in _rd(fn):
            if r.get("Disposition") != "SELLABLE": continue
            try: d = dt.datetime.strptime(r["Date"], "%m/%d/%Y").date()
            except Exception: continue
            ins = _num(r.get("Ending Warehouse Balance")) > 0 or _num(r.get("Starting Warehouse Balance")) > 0
            stock.setdefault(r["MSKU"], {})[d] = ins
    return sold, stock


def _window(sold_d, stock_d, today, days):
    """(units, in_stock_days, known_days) over the last `days` days before today (today excluded: incomplete)"""
    units = ins = known = 0
    for k in range(1, days + 1):
        d = today - dt.timedelta(days=k)
        units += sold_d.get(d, 0)
        s = stock_d.get(d)
        if s is None:
            ins += 1                      # a day the ledger does not cover counts as in stock (never invent an outage)
        else:
            known += 1
            ins += 1 if (s or sold_d.get(d, 0) > 0) else 0
    return units, ins, known


def rate_of(units, ins, days, prior):
    """shrunk units per in-stock day"""
    if ins <= 0: return 0.0
    r = (units + SHRINK_DAYS * prior) / (ins + SHRINK_DAYS)
    return min(r, prior * MAX_UPLIFT) if prior > 0 else r


def one(sold_d, stock_d, today, sellable_now=None, inbound=0.0):
    u30, i30, _ = _window(sold_d, stock_d, today, 30)
    u90, i90, k90 = _window(sold_d, stock_d, today, 90)
    n30, n90 = u30 / 30.0, u90 / 90.0
    c90 = rate_of(u90, i90, 90, n90)
    c30 = rate_of(u30, i30, 30, n30)
    rate = (c30 + c90) / 2.0 if (u30 > 6 and u30 > 0.5 * u90) else c90      # same rule the workbook used, now on in-stock days
    out_now = 0
    d = today - dt.timedelta(days=1)
    while stock_d.get(d) is False and sold_d.get(d, 0) == 0 and out_now < 400:
        out_now += 1; d -= dt.timedelta(days=1)
    if sellable_now is not None and sellable_now <= 0 and out_now == 0: out_now = 1
    urgent = 0
    cover = ""
    if rate >= MIN_RATE:
        if sellable_now is not None:
            cover = (sellable_now + inbound) / rate
            if sellable_now <= 0 and inbound <= 0: urgent = 2
            elif cover < URGENT_COVER_DAYS: urgent = 1
        elif out_now > 0: urgent = 2
    return {"dem_rate": round(rate, 4), "dem_naive": round(max(n90, (n30 + n90) / 2 if u30 > 6 and u30 > 0.5 * u90 else n90), 4),
            "dem_instock_90": i90, "dem_out_now": out_now, "dem_urgent": urgent, "dem_cover_days": round(cover, 1) if cover != "" else ""}


def compute(state_dir, today=None, current=None, inbound=None):
    today = today or dt.date.today()
    sold, stock = load(state_dir)
    out = {}
    for sku in set(sold) | set(stock):
        cur = None if current is None or sku not in current else current[sku]
        out[sku] = one(sold.get(sku, {}), stock.get(sku, {}), today, cur, (inbound or {}).get(sku, 0.0))
    return out


# ------------------------------------------------------------------ compact copy of the history (what the PC downloads)
def export_compact(state_dir, today=None, days=100):
    """-> dict with the last `days` days of sales and in/out-of-stock days per SKU (about 200 KB), written daily by the cloud feed so that
    the PC can compute the same demand columns without the big order / ledger files."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    sold, stock = load(state_dir)
    out = {"generated": today.isoformat(), "days": days, "sold": {}, "stock": {}}
    for sku, byd in sold.items():
        m = {d.isoformat(): q for d, q in byd.items() if d >= since}
        if m: out["sold"][sku] = m
    for sku, byd in stock.items():
        ins = sorted(d.isoformat() for d, v in byd.items() if v and d >= since)
        outs = sorted(d.isoformat() for d, v in byd.items() if (not v) and d >= since)
        if ins or outs: out["stock"][sku] = {"in": ins, "out": outs}
    return out


def load_compact(obj):
    """inverse of export_compact -> (sold {sku: {date: units}}, stock {sku: {date: bool}})"""
    if isinstance(obj, (str, bytes, os.PathLike)):
        import json
        with open(obj, encoding="utf-8") as f: obj = json.load(f)
    sold = {sku: {dt.date.fromisoformat(d): int(q) for d, q in m.items()} for sku, m in (obj.get("sold") or {}).items()}
    stock = {}
    for sku, e in (obj.get("stock") or {}).items():
        m = {}
        for d in e.get("in", []): m[dt.date.fromisoformat(d)] = True
        for d in e.get("out", []): m[dt.date.fromisoformat(d)] = False
        stock[sku] = m
    return sold, stock


COLS = ["dem_rate", "dem_naive", "dem_instock_90", "dem_out_now", "dem_urgent", "dem_cover_days"]

if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[1] == "export":          # python demand.py export <state dir> <out.json>
        import json
        o = export_compact(sys.argv[2])
        json.dump(o, open(sys.argv[3], "w", encoding="utf-8"), separators=(",", ":"))
        print("exported %d products with sales, %d with stock days -> %s" % (len(o["sold"]), len(o["stock"]), sys.argv[3]))
        sys.exit(0)
    st = sys.argv[1] if len(sys.argv) > 1 else "."
    res = compute(st)
    rows = sorted(res.items(), key=lambda kv: -(kv[1]["dem_rate"] - kv[1]["dem_naive"]))
    for sku, v in rows[:15]:
        print(sku, v)
