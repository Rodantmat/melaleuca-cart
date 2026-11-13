"""Check same-item Amazon competitors: price, seller count, rank, reviews. Input env ASINS = 'REF=ASIN ...'. Stores in private deals.comp_check; log prints counts only."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, spapi, deal_finder as df, validate as va

def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.comp_check (id bigserial primary key, at timestamptz default now(), ref_asin text, asin text, data jsonb)")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    pairs = [t.split("=") for t in (os.environ.get("ASINS") or "").split() if "=" in t]
    cat = {}
    for ref, a in pairs:
        try:
            r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": df.MK, "includedData": "summaries,salesRanks"}, quiet=True, tries=4)
            cat[a] = df._parse_item(r)
        except Exception as e:
            print("  catalog ERR", str(e)[:60])
        time.sleep(0.6)
    offers = df.offers_batch(c, list(cat))
    revs = va.review_info(list(cat))
    n = 0
    for ref, a in pairs:
        if a not in cat: continue
        d = dict(cat[a]); d.pop("image", None)
        d["offers"] = offers.get(a); d["reviews"] = revs.get(a)
        cx.execute("insert into deals.comp_check(ref_asin, asin, data) values (%s,%s,%s)", (ref, a, json.dumps(d))); n += 1
    print("comp_check: %d of %d checked" % (n, len(pairs)))

main()
