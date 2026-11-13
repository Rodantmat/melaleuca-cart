"""Find AliExpress suppliers that match an Amazon reference product BY PHOTO (private results in deals.ali_match; log prints counts only).
Env: REFS (ASINs), QUERIES ('|' separated AliExpress keyword searches), DATABASE_URL, ALIEXPRESS_APP_KEY/SECRET."""
import json, os, sys, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, spapi
import img_match as im, ali_api

def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.ali_match (id bigserial primary key, at timestamptz default now(), ref_asin text, ali_id text, sim real, data jsonb)")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    embed = im.load_embed()
    qs = [q.strip() for q in (os.environ.get("QUERIES") or "").split("|") if q.strip()]
    for ref in (os.environ.get("REFS") or "").split():
        urls = [i["url"] for i in im.ensure_images(cx, c, ref) if i.get("url") and "_SL" not in i["url"]][:6]
        R = embed([x for x in (im.fetch(u) for u in urls) if x])
        seen = {}
        for q in qs:
            for r in ali_api.search(q, pages=2, size=50):
                seen.setdefault(r["goods_id"], r)
        out = []
        for gid, r in seen.items():
            pic = im.fetch(r["image"]) if r.get("image") else None
            if not pic: continue
            out.append((float((embed([pic]) @ R.T).max()), r))
        out.sort(key=lambda x: -x[0])
        keep = [x for x in out if x[0] >= 0.85][:25]
        for s, r in keep:
            d = {k: r.get(k) for k in ("title", "price", "list_price", "sold", "rating", "url")}
            cx.execute("insert into deals.ali_match(ref_asin, ali_id, sim, data) values (%s,%s,%s,%s)", (ref, gid_of(r), round(s, 3), json.dumps(d)))
        print("ali_match: %d AliExpress items searched, %d match the photo (sim>=0.85)" % (len(out), len(keep)))

def gid_of(r): return r["goods_id"]

main()
