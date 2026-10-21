"""Competitor intelligence from the logged-out web scan (bb_web.py -> state/webbb.jsonl).  No SP-API calls, never changes a price.   python bb_intel.py
 writes state/bb_report.tsv  (per ASIN: share of scans we owned the Buy Box, who owns it otherwise, price gap, rival size)
        state/bb_sellers.tsv (per seller: ASINs, wins, FBA/FBM, ratings, % positive, how far from our price)
        state/bb_agreement.tsv (SP-API Buy Box vs what shoppers see)
What it is for: tells WHO takes the Buy Box (a seller with thousands of ratings cannot be beaten by price alone; a 5-rating FBM seller with slow shipping only takes
non-Prime shoppers) so that a price cut is only made where it can win."""
import collections, json, os, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(HERE, "state")
ME = "A3431QI59MY9RE"


def jl(name):
    out = []
    try:
        for l in open(os.path.join(S, name)):
            try: out.append(json.loads(l))
            except Exception: pass
    except Exception:
        pass
    return out


def main():
    me = ME
    try: me = open(os.path.join(S, "seller.txt")).read().strip() or ME
    except Exception: pass
    web = [r for r in jl("webbb.jsonl") if r.get("seller_id") and r.get("bb_price")]
    if not web:
        print("no web Buy Box data yet"); return
    snaps = {}
    try:
        L = open(os.path.join(S, "snapshots.tsv")).read().splitlines(); h = L[0].split("\t")
        for l in L[1:]:
            r = dict(zip(h, l.split("\t"))); snaps[r["asin"]] = r
    except Exception: pass
    by = collections.defaultdict(list)
    for r in web: by[r["asin"]].append(r)
    prof = {}                                                     # seller -> latest profile from the offers drawer
    for r in jl("webbb.jsonl"):
        for o in (r.get("aod") or []):
            if o.get("seller_id"):
                p = prof.setdefault(o["seller_id"], {})
                p.update({k: o[k] for k in ("sold_by", "ships_from", "fulfil", "ratings", "pos_pct") if o.get(k) is not None})
    rows, sell = [], collections.defaultdict(lambda: {"asins": set(), "wins": 0, "gaps": []})
    for a, L in by.items():
        n = len(L); wins = sum(1 for r in L if r["seller_id"] == me)
        rivals = collections.Counter(r["seller_id"] for r in L if r["seller_id"] != me)
        top = rivals.most_common(1)[0][0] if rivals else ""
        last = L[-1]; sn = snaps.get(a) or {}
        try: own = float(sn.get("own_price"))
        except Exception: own = None
        for r in L:
            s = sell[r["seller_id"]]; s["asins"].add(a); s["wins"] += 1
            if own and r["seller_id"] != me: s["gaps"].append(r["bb_price"] / own - 1)
        p = prof.get(top, {})
        rows.append([a, sn.get("sku", ""), n, "%.2f" % (wins / n), top, p.get("sold_by", ""), last["bb_price"], own or "", ("%.1f" % (100 * (own / last["bb_price"] - 1))) if own else "",
                     p.get("fulfil", ""), p.get("ratings", ""), p.get("pos_pct", ""), last.get("offers_n", ""), last.get("left", "")])
    with open(os.path.join(S, "bb_report.tsv"), "w") as fh:
        fh.write("asin\tsku\tscans\twe_own_share\ttop_rival\trival_name\tbuybox_price\town_price\tour_gap_pct\trival_type\trival_ratings\trival_pos_pct\toffers\tleft\n")
        for r in sorted(rows, key=lambda r: float(r[3])): fh.write("\t".join(str(x) for x in r) + "\n")
    with open(os.path.join(S, "bb_sellers.tsv"), "w") as fh:
        fh.write("seller\tis_me\tname\tasins_owned\tscans_owned\ttype\tratings\tpos_pct\tships_from\tmedian_vs_our_price_pct\n")
        for s, d in sorted(sell.items(), key=lambda kv: -kv[1]["wins"]):
            p = prof.get(s, {})
            fh.write("\t".join(str(x) for x in [s, int(s == me), p.get("sold_by", ""), len(d["asins"]), d["wins"], p.get("fulfil", ""), p.get("ratings", ""), p.get("pos_pct", ""), p.get("ships_from", ""),
                                                ("%.1f" % (100 * statistics.median(d["gaps"]))) if d["gaps"] else ""]) + "\n")
    api = {}
    for r in jl("bbwin.jsonl"): api[r["asin"]] = r
    agree = collections.Counter(); lines = []
    for a, L in by.items():
        x = api.get(a)
        if not x: continue
        w = L[-1]; aw = x["win"][0]
        k = ("same seller" if aw["seller"] == w["seller_id"] else "different seller", "same price" if abs(aw["price"] - w["bb_price"]) < 0.006 else "different price")
        agree[k] += 1
        if k[0] == "different seller":
            lines.append([a, snaps.get(a, {}).get("sku", ""), aw["seller"], aw["type"], aw["price"], w["seller_id"], w["bb_price"]])
    with open(os.path.join(S, "bb_agreement.tsv"), "w") as fh:
        fh.write("asin\tsku\tapi_winner\tapi_type\tapi_price\tweb_winner\tweb_price\n")
        for r in lines: fh.write("\t".join(str(x) for x in r) + "\n")
    print("bb intel: %d ASINs, we own the box in %.0f%% of web scans; API vs web: %s" % (len(by), 100 * sum(1 for r in web if r["seller_id"] == me) / len(web), dict(agree)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("bb_intel failed (ignored): %r" % e)
