"""Read-only reports built from the saved state (never changes a price, no API calls).   python reports.py
  state/bb_stock.tsv      per product: Buy Box owner's stock ('Only N left'), how fast it falls, days until it runs out, and a WAIT / DROP-CANDIDATE / HOLD hint (hint only: not used by the repricer yet)
  state/restock_alert.tsv products that sell but are out of stock / about to be, ranked by profit at risk per month
  state/rival_alerts.tsv  new sellers on a product, rivals far below our price
  state/outcomes.tsv      every applied price change and what happened to the sales speed afterwards"""
import collections, csv, datetime as dt, glob, json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.environ.get("REPORT_STATE") or os.path.join(HERE, "state")
ME = "A3431QI59MY9RE"


def jl(name):
    out = []
    try:
        for l in open(os.path.join(S, name)):
            try: out.append(json.loads(l))
            except Exception: pass
    except Exception: pass
    return out


def tsv(path):
    try:
        L = open(path, encoding="utf-8", errors="replace").read().splitlines(); h = L[0].split("\t")
        return [dict(zip(h, l.split("\t"))) for l in L[1:]]
    except Exception:
        return []


def fl(x, d=None):
    try: return float(x)
    except Exception: return d


def tparse(t):
    return dt.datetime.strptime(t[:16].replace("T", " "), "%Y-%m-%d %H:%M")


def write(name, header, rows):
    with open(os.path.join(S, name), "w") as fh:
        fh.write("\t".join(header) + "\n")
        for r in rows: fh.write("\t".join("" if v is None else str(v) for v in r) + "\n")


def main():
    me = ME
    try: me = open(os.path.join(S, "seller.txt")).read().strip() or ME
    except Exception: pass
    web = jl("webbb.jsonl")
    sig = {r["sku"]: r for r in tsv(os.path.join(S, "signals.tsv"))}
    costs = tsv(os.path.join(os.path.dirname(S), "costs.tsv")) or tsv(os.path.join(HERE, "costs.tsv"))
    sku_of = {r["asin"]: r["sku"] for r in costs}
    snaps = {}
    for r in tsv(os.path.join(S, "snapshots.tsv")): snaps[r["asin"]] = r
    now = dt.datetime.utcnow()

    # ---------------------------------------------------------------- 1. rival stock
    series = collections.defaultdict(list)                                  # (asin, seller) -> [(t, left)]
    last_row = {}
    for r in web:
        if r.get("err"): continue
        last_row[r["asin"]] = r
        if r.get("left") is not None and r.get("left_seller"):
            series[(r["asin"], r["left_seller"])].append((tparse(r["t"]), r["left"]))
    rows = []
    for a, lr in last_row.items():
        if lr.get("we_win") or not lr.get("seller_id"): continue
        sku = sku_of.get(a, ""); sg = sig.get(sku, {})
        sn = snaps.get(a, {}); on_hand = fl(sn.get("on_hand"), 0.0); own = fl(sn.get("own_price")); sold_m = fl(sg.get("sold_per_month"), 0.0); cover = fl(sg.get("days_cover"))
        s = series.get((a, lr["seller_id"])) or []
        left = lr.get("left")
        rate = eta = None
        seg = []                                                            # the last stretch in which the rival's stock only fell (a rise = they restocked)
        for t, v in s:
            if seg and v > seg[-1][1]: seg = []
            seg.append((t, v))
        if len(seg) >= 2 and (seg[-1][0] - seg[0][0]).total_seconds() >= 20 * 3600:
            days = (seg[-1][0] - seg[0][0]).total_seconds() / 86400.0
            rate = (seg[0][1] - seg[-1][1]) / days
            if rate > 0.05 and seg[-1][1] > 0: eta = round(seg[-1][1] / rate, 1)
        gap = (own / lr["bb_price"] - 1) * 100 if own and lr.get("bb_price") else None
        # hints (proposal, not wired to the repricer)
        if on_hand <= 5: hint, why = "HOLD", "we have %d units: keep the margin" % on_hand
        elif left is not None and (left <= 3 or (eta is not None and eta <= 10)):
            hint, why = "WAIT", "owner has %s left%s" % (left, (", gone in ~%.0f days" % eta) if eta else "")
        elif sold_m > 0 and cover and cover >= 45 and gap is not None and gap > 5 and (left is None or left >= 10 or (eta is not None and eta > 30)):
            hint, why = "DROP-CANDIDATE", "owner has %s, we have %.0f days of cover and are %.0f%% above the box" % ("plenty" if left is None else left, cover, gap)
        else: hint, why = "WATCH", ""
        rows.append([a, sku, lr.get("sold_by") or lr["seller_id"], lr.get("fulfil"), lr["bb_price"], own, "%.1f" % gap if gap is not None else "", left if left is not None else "20+/none",
                     len(s), "%.2f" % rate if rate is not None else "", eta if eta is not None else "", on_hand, sold_m, cover, hint, why])
    rows.sort(key=lambda r: ({"WAIT": 0, "DROP-CANDIDATE": 1, "WATCH": 2, "HOLD": 3}[r[14]], -(r[12] or 0)))
    write("bb_stock.tsv", ["asin", "sku", "box_owner", "type", "box_price", "our_price", "our_gap_pct", "owner_left", "reads", "owner_sales_per_day", "owner_days_to_zero", "our_stock", "our_sold_per_month", "our_cover_days", "hint", "why"], rows)
    hc = collections.Counter(r[14] for r in rows)

    # ---------------------------------------------------------------- 2. restock alert
    ledger = collections.defaultdict(dict)
    for fn in glob.glob(os.path.join(S, "ledger_*.tsv")):
        for r in tsv(fn):
            if r.get("Disposition") == "SELLABLE":
                try: ledger[r["MSKU"]][dt.datetime.strptime(r["Date"], "%m/%d/%Y").date()] = fl(r["Ending Warehouse Balance"], 0)
                except Exception: pass
    ra = []
    for sku, r in sig.items():
        sold_m, pu = fl(r.get("sold_per_month"), 0), fl(r.get("profit_unit_cons"), 0)
        sg = r.get("signal", "")
        if not (sg.startswith("BUY") and sold_m > 0): continue
        if fl(r.get("sellable_units"), 0) > 0 and (fl(r.get("days_cover"), 999) > 14): continue      # in stock with more than 2 weeks of cover: not urgent
        d_out = 0; led = ledger.get(sku, {}); day = now.date() - dt.timedelta(days=1)
        while led.get(day) is not None and led[day] <= 0 and d_out < 400: d_out += 1; day -= dt.timedelta(days=1)
        ra.append([sku, (r.get("group") or "")[:40], r.get("sellable_units"), sold_m, "%.2f" % pu, "%.0f" % (sold_m * pu), d_out if led else "", "OUT OF STOCK" if fl(r.get("sellable_units"), 0) <= 0 else "LOW", sg])
    ra.sort(key=lambda x: (x[7] != "OUT OF STOCK", -float(x[5])))
    write("restock_alert.tsv", ["sku", "product", "units_now", "sold_per_month", "profit_per_unit", "profit_at_risk_per_month", "days_out_of_stock", "status", "signal"], ra)

    # ---------------------------------------------------------------- 3. rival alerts
    byasin = collections.defaultdict(list)
    for r in web:
        if not r.get("err") and r.get("aod") is not None: byasin[r["asin"]].append(r)
    al = []
    for a, L in byasin.items():
        cur = {o["seller_id"]: o for o in (L[-1].get("aod") or []) if o.get("seller_id")}
        before = {o["seller_id"] for r in L[:-1] for o in (r.get("aod") or []) if o.get("seller_id")}
        own = fl((snaps.get(a) or {}).get("own_price"))
        if len(L) >= 3:
            for sid, o in cur.items():
                if sid != me and sid not in before:
                    al.append([a, sku_of.get(a, ""), "NEW SELLER", sid, o.get("sold_by") or "", o.get("fulfil"), o.get("price"), own, o.get("ratings")])
        if own:
            for sid, o in cur.items():
                if sid != me and o.get("price") and o["price"] < own * 0.92 and (o.get("fulfil") == "F" or (o.get("ratings") or 0) >= 50):
                    al.append([a, sku_of.get(a, ""), "FAR BELOW US", sid, o.get("sold_by") or "", o.get("fulfil"), o["price"], own, o.get("ratings")])
    write("rival_alerts.tsv", ["asin", "sku", "alert", "seller", "name", "type", "price", "our_price", "ratings"], al)

    # ---------------------------------------------------------------- 4. outcomes of our price changes
    sold = collections.defaultdict(collections.Counter); last = None
    for fn in glob.glob(os.path.join(S, "orders_*.tsv")):
        for r in tsv(fn):
            if (r.get("order-status") or "").lower().startswith("cancel"): continue
            try: d = dt.date.fromisoformat(r["purchase-date"][:10]); q = int(r["quantity"])
            except Exception: continue
            sold[r["sku"]][d] += q; last = max(last or d, d)
    dec = jl("decisions.jsonl"); reverted = {(d["sku"]) for d in dec if d.get("action") == "revert" and d.get("applied")}
    out = []
    for d in dec:
        if d.get("applied") and d.get("action") in ("up", "down", "to_floor", "revert") and last:
            t = tparse(d["ts"]).date(); sku = d["sku"]
            if (last - t).days < 0: continue
            b = sum(q for x, q in sold[sku].items() if t - dt.timedelta(days=14) <= x < t) / 14.0
            n = (last - t).days + 1
            af = sum(q for x, q in sold[sku].items() if t <= x <= last) / float(n)
            out.append([d["ts"][:16], sku, d["action"], d["price"], d["new"], "%.2f" % b, "%.2f" % af, n, "yes" if sku in reverted else ""])
    write("outcomes.tsv", ["when", "sku", "action", "old_price", "new_price", "units_per_day_before_14d", "units_per_day_after", "days_after", "later_reverted"], out)
    print("reports: rival stock hints %s | restock alerts %d (profit at risk $%.0f/month) | rival alerts %d | outcomes %d" % (dict(hc), len(ra), sum(float(x[5]) for x in ra), len(al), len(out)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("reports failed (ignored): %r" % e)
