"""Image gate for dossiers (private: verdict goes ONLY into Postgres deals.dealsheet.data->'img_gate').
Finds same-product Amazon listings by photo similarity and decides PASS / WARN / FAIL.
FAIL: >= 8 active close matches, or a much cheaper, better-ranked twin. WARN: 4-7 active close matches or our price above market. PASS otherwise."""
import json, os, statistics, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, spapi
import img_match as im

CLOSE = float(os.environ.get("CLOSE_SIM", "0.90"))
MAX = int(os.environ.get("GATE_MAX", "12"))


def gate(our_price, ref_rank, out):
    close = [(s, a, p, o) for s, a, p, o in out if s >= CLOSE]
    active = [x for x in close if x[3] and (x[3].get("total") or 0) >= 1 and x[3].get("bb")]
    ranked = [x for x in active if x[2].get("rank")]
    prime = [x for x in active if (x[3].get("fba") or 0) >= 1]
    prices = [x[3]["bb"] for x in ranked]
    med = round(statistics.median(prices), 2) if prices else None
    reasons = []
    twin = None
    for s, a, p, o in ranked:
        if our_price and o["bb"] <= 0.70 * our_price / 0.85 and (not ref_rank or p["rank"] <= ref_rank * 1.5):
            twin = {"asin": a, "price": o["bb"], "rank": p["rank"], "sim": round(s, 3)}; break
    if twin:
        reasons.append("cheaper well-ranked twin at $%.2f (rank %s)" % (twin["price"], twin["rank"]))
    if len(active) >= 8:
        reasons.append("%d active same-product listings" % len(active))
    elif len(active) >= 4:
        reasons.append("%d active same-product listings" % len(active))
    if med and our_price and our_price > 1.15 * med:
        reasons.append("our price is above the ranked-twin median $%.2f" % med)
    verdict = "FAIL" if twin or len(active) >= 8 else "WARN" if reasons else "PASS"
    return {"verdict": verdict, "reasons": reasons, "close_matches": len(close), "active": len(active), "ranked": len(ranked), "prime_sellers": len(prime),
            "ranked_median_price": med, "lowest_ranked_price": min(prices) if prices else None, "cheaper_twin": twin,
            "top": [{"asin": a, "sim": round(s, 3), "price": (o or {}).get("bb"), "rank": p.get("rank"), "brand": p.get("brand"), "prime": ((o or {}).get("fba") or 0) >= 1}
                    for s, a, p, o in sorted(close, key=lambda x: -x[0])[:12]]}


def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.img_match (id bigserial primary key, at timestamptz default now(), ref_asin text, asin text, sim real, data jsonb)")
    rows = cx.execute("""select id, ref_asin, data from (select distinct on (ref_asin) id, ref_asin, data, run_at from deals.dealsheet
                         where run_at > now() - interval '48 hours' order by ref_asin, run_at desc) t
                         where not (data ? 'img_gate') and (data->'model'->'scenarios'->'base'->>'profit_12m_after_setup')::numeric > 0
                         order by id desc limit %s""", (MAX,)).fetchall()
    print("img_gate: %d dossiers to gate" % len(rows))
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    embed = im.load_embed()
    cnt = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for id_, ref, data in rows:
        try:
            n, out = im.match_ref(cx, c, embed, ref)
            ref_it = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + ref, params={"marketplaceIds": im.df.MK, "includedData": "salesRanks"}, quiet=True, tries=3)
            ref_rank = im.df._parse_item(ref_it).get("rank")
        except Exception as e:
            print("  gate ERR", str(e)[:70]); continue
        g = gate(((data.get("model") or {}).get("our_price")), ref_rank, out)
        g["searched"] = n
        cx.execute("update deals.dealsheet set data = data || %s::jsonb where id=%s", (json.dumps({"img_gate": g}), id_))
        cnt[g["verdict"]] += 1
    print("img_gate: %d PASS, %d WARN, %d FAIL" % (cnt["PASS"], cnt["WARN"], cnt["FAIL"]))


main()
