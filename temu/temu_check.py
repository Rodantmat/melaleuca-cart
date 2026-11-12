"""Slow Temu cross-check for the best dossiers (private: results go ONLY into Postgres deals.dealsheet.data->'temu_check').
Temu is a second price opinion for the same product: a cheaper Temu price than AliExpress means a better source; no match = just no second opinion.
Paced by temu_bridge (35 s between requests); stops at the first block. Env: DATABASE_URL, MAXN (default 6)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, temu_bridge, deal_finder as df

MAXN = int(os.environ.get("MAXN", "6"))
cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
rows = cx.execute("""select id, ref_asin, data from (select distinct on (ref_asin) id, ref_asin, data, run_at from deals.dealsheet
                       where run_at > now() - interval '48 hours' order by ref_asin, run_at desc) t
                     where not (data ? 'temu_check') and (data->'model'->'scenarios'->'base'->>'profit_12m_after_setup')::numeric > 0
                     order by (data->'model'->'scenarios'->'base'->>'profit_12m_after_setup')::numeric desc limit %s""", (MAXN,)).fetchall()
print("temu_check: %d dossiers to cross-check" % len(rows))
done = hits = 0
for id_, ref, d in rows:
    if temu_bridge.STATS.get("closed"):
        print("temu_check: Temu blocked, stopping (%s)" % temu_bridge.STATS["closed"]); break
    title = d.get("product") or ""
    try:
        res = [r for r in temu_bridge.search(df.query_for(title)) if r.get("price")]
    except Exception as e:
        print("temu_check: search error", str(e)[:80]); break
    scored = sorted(((df.sim(title, r["title"]), r) for r in res), key=lambda x: -x[0])
    pk = d.get("pack_ratio") or 1
    best = [{"sim": round(s, 2), "title": r["title"][:100], "price": r["price"], "price_for_our_pack": round(r["price"] * pk, 2), "sold": r.get("sold"), "url": r.get("url")}
            for s, r in scored[:3] if s >= 0.35]
    ali = (d.get("source_price_shown") or 0) * pk
    chk = {"checked": True, "matches": best, "aliexpress_price_for_our_pack": round(ali, 2)}
    if best:
        hits += 1
        chk["cheapest_match_price"] = min(b["price_for_our_pack"] for b in best)
        chk["verdict"] = "Temu cheaper" if chk["cheapest_match_price"] < ali * 0.95 else "AliExpress equal or cheaper"
    else:
        chk["verdict"] = "no comparable Temu listing found"
    cx.execute("update deals.dealsheet set data = data || %s::jsonb where id=%s", (json.dumps({"temu_check": chk}), id_))
    done += 1
print("temu_check: %d checked, %d with a comparable Temu match" % (done, hits))
