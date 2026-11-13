"""Hot-product discovery: pulls AliExpress hot feed, keeps >=500 orders and 4.5+ rating and $2-15, stores privately in deals.ali_hot. Counts only in log."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg, ali_api
cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
cx.execute("create table if not exists deals.ali_hot (id bigserial primary key, at timestamptz default now(), ali_id text unique, data jsonb)")
cats = [c for c in os.environ.get("CATS", "").split(",")] or [""]
kws = [k for k in os.environ.get("KWS", "").split("|") if k.strip()]
tot = kept = 0
for cat in cats:
    for kw in (kws or [""]):
        try:
            rows = ali_api.hot(category_ids=cat.strip(), keywords=kw.strip(), pages=3)
        except Exception as e:
            print("hot ERR", str(e)[:80]); continue
        tot += len(rows)
        for r in rows:
            try:
                sold = int(str(r["sold"] or 0).replace(",", "")); rt = float(str(r["rating"] or "0").replace("%", ""))
            except Exception:
                continue
            if sold >= 500 and r["price"] and 2 <= r["price"] <= 15 and (rt >= 90 or 0 < rt <= 5 and rt >= 4.5):
                cx.execute("insert into deals.ali_hot(ali_id,data) values (%s,%s) on conflict (ali_id) do nothing", (r["id"], json.dumps(r)))
                kept += 1
print("ali_hot: %d fetched, %d kept" % (tot, kept))
