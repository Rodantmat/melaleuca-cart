"""Load a deal_finder run (/tmp/deals) into the private Postgres (schema deals). Nothing about the deals is printed to the public log.
Env: DATABASE_URL, RUN_ID (GitHub run id), CHUNK, SOURCE."""
import glob, json, os, sys
import psycopg

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/deals"
url = os.environ.get("DATABASE_URL", "")
if not url:
    print("DATABASE_URL secret missing in this repo - results NOT stored (and not published)"); sys.exit(1)
files = sorted(glob.glob(os.path.join(out, "deals_*.json")))
if not files:
    print("no deal_finder output"); sys.exit(0)
d = json.load(open(files[-1]))
log = open(os.path.join(out, "run.log")).read() if os.path.exists(os.path.join(out, "run.log")) else ""
rid = "gh%s" % os.environ.get("RUN_ID", "local")
m, a = d.get("markets") or [], d.get("abandoned") or []
summary = {"markets": len(m), "positive_roi": sum(1 for r in m if (r.get("roi_wholesale") or -1) > 0), "abandoned": len(a)}
with psycopg.connect(url) as cx, cx.cursor() as cur:
    cur.execute("insert into deals.runs(run_id, chunk, source, params, summary, log) values (%s,%s,%s,%s,%s,%s) on conflict (run_id) do update set summary=excluded.summary, log=excluded.log",
                (rid, os.environ.get("CHUNK"), os.environ.get("SOURCE"), json.dumps({k: os.environ.get(k) for k in ("ROI_MIN", "MAX_TEMU_PRICE", "WHOLESALE_FACTOR", "FREIGHT_PER_UNIT", "PER_KW")}),
                 json.dumps(summary), log[-200000:]))
    cur.execute("delete from deals.markets where run_id=%s", (rid,))
    cur.execute("delete from deals.abandoned where run_id=%s", (rid,))
    for r in m:
        cur.execute("insert into deals.markets(run_id, source_id, kw, cat, match_conf, profit_month, profit_12m, roi_wholesale, market_sales_month, listings, sellers, amazon_sells, source_price, amz_price, ref_asin, row) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, r.get("temu_id"), r.get("kw"), r.get("cat"), r.get("match_conf"), r.get("profit_month"), r.get("profit_12m"), r.get("roi_wholesale"),
                     r.get("market_sales_month"), r.get("listings"), r.get("sellers"), r.get("amazon_sells"), r.get("temu_price"), r.get("amz_price"), r.get("ref_asin"), json.dumps(r, default=str)))
    for r in a:
        cur.execute("insert into deals.abandoned(run_id, asin, rank, est_sales_month, reviews, rating, bought_month, list_price, roi_wholesale, profit_month, row) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, r.get("asin"), r.get("rank"), r.get("est_sales_month"), r.get("reviews"), r.get("rating"), r.get("bought_month"), r.get("list_price"),
                     r.get("roi_wholesale"), r.get("profit_month"), json.dumps(r, default=str)))
print("stored run %s in Postgres: %s" % (rid, summary))
