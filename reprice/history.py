"""History builder: up to 24 months of order lines (price actually paid, units) and the daily FBA inventory ledger (in-stock days).
usage: python history.py [months]   -> state/orders_YYYY-MM.tsv, state/ledger_YYYY-MM.tsv  (only the months not stored yet, plus the last 2 months refreshed)"""
import datetime as dt, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spapi

STATE = os.path.join(HERE, "state")
ORDERS = "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"
KEEP = ("purchase-date", "order-status", "fulfillment-channel", "sales-channel", "sku", "asin", "quantity", "item-price", "item-promotion-discount", "currency")


def month_windows(n):
    today = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    first = today.replace(day=1)
    out = []
    for k in range(n):
        y, m = first.year, first.month - k
        while m <= 0:
            m += 12; y -= 1
        s = dt.datetime(y, m, 1)
        e = dt.datetime(y + (m == 12), (m % 12) + 1, 1)
        e = min(e, today - dt.timedelta(minutes=10) if k == 0 else e)
        out.append((s, e))
    return out[::-1]


def pull_orders(c, s, e):
    """a month = two requests of <= 16 days (Amazon limit 30 days)"""
    mid = s + (e - s) / 2
    lines, head = [], None
    for a, b in ((s, mid), (mid, e)):
        st, txt = spapi.report(c, ORDERS, a.isoformat() + "Z", b.isoformat() + "Z")
        if st != "DONE":
            return None, st
        rows = txt.splitlines()
        if not rows:
            continue
        hdr = rows[0].split("\t")
        if head is None:
            head = hdr
        idx = [hdr.index(k) for k in KEEP if k in hdr]
        for r in rows[1:]:
            p = r.split("\t")
            lines.append("\t".join(p[i] if i < len(p) else "" for i in idx))
    keep = [k for k in KEEP if head and k in head]
    return ["\t".join(keep)] + lines, "DONE"


def pull_ledger(c, s, e):
    st, txt = spapi.report(c, "GET_LEDGER_SUMMARY_VIEW_DATA", s.isoformat() + "Z", e.isoformat() + "Z", {"aggregateByLocation": "COUNTRY", "aggregatedByTimePeriod": "DAILY"})
    if st != "DONE":
        return None, st
    return txt.replace('"', "").splitlines(), "DONE"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    c = spapi.load_creds(HERE)
    os.makedirs(STATE, exist_ok=True)
    wins = month_windows(n)
    for k, (s, e) in enumerate(wins):
        recent = k >= len(wins) - 2
        for kind, fn in (("orders", pull_orders), ("ledger", pull_ledger)):
            if kind == "ledger" and k < len(wins) - 12:      # the ledger only reaches back about a year
                continue
            path = os.path.join(STATE, "%s_%s.tsv" % (kind, s.strftime("%Y-%m")))
            if os.path.exists(path) and not recent:
                continue
            lines, st = fn(c, s, e)
            if lines is None:
                print("%s %s: %s" % (kind, s.strftime("%Y-%m"), st)); sys.stdout.flush()
                continue
            open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
            print("%s %s: %d rows" % (kind, s.strftime("%Y-%m"), len(lines) - 1)); sys.stdout.flush()
            time.sleep(1)


if __name__ == "__main__":
    main()
