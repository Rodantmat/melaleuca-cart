"""Competitor intelligence (read-only, never changes a price).   python bb_intel.py
 1. once a day: for every ASIN where we are NOT the Buy Box winner, read the full offer list (getItemOffers v0) and keep per seller:
    feedback count / rating, FBA or FBM, ships-from state, handling hours, Prime flag  -> state/sellers.json
 2. every run: build state/bb_report.tsv  (per ASIN: share of snapshots we won, who wins when we do not, price gap, units sold)
               and state/bb_sellers.tsv   (per seller: ASINs, wins, FBA/FBM, feedback, how far below/above us they sit)
What the data is for: tells us WHO takes the Buy Box (a big FBA seller with thousands of reviews cannot be beaten by price alone, a 5-review FBM seller with
slow shipping only takes non-Prime shoppers) so that a price cut is only made where it can win."""
import collections, datetime as dt, json, os, statistics, sys, time
import spapi
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(HERE, "state")


def jl(name):
    out = []
    try:
        for l in open(os.path.join(S, name)):
            try: out.append(json.loads(l))
            except Exception: pass
    except Exception:
        pass
    return out


def sweep(c, me, asins, pause=2.2):
    prof = {}
    try: prof = json.load(open(os.path.join(S, "sellers.json")))
    except Exception: prof = {"meta": {}, "sellers": {}}
    today = dt.date.today().isoformat()
    if prof.get("meta", {}).get("last_sweep") == today:
        print("seller sweep already done today"); return prof
    n = 0
    for a in asins:
        try:
            r = spapi.call(c, "GET", "/products/pricing/v0/items/%s/offers" % a, params={"MarketplaceId": spapi.MARKETPLACE, "ItemCondition": "New", "CustomerType": "Consumer"}, quiet=True, tries=3)
        except Exception as e:
            print("  offers %s: %s" % (a, str(e)[:100])); time.sleep(pause); continue
        n += 1
        for o in (r.get("payload") or {}).get("Offers") or []:
            sid = o.get("SellerId")
            if not sid: continue
            fb = o.get("SellerFeedbackRating") or {}
            p = prof["sellers"].setdefault(sid, {"first": today})
            p.update({"type": "F" if o.get("IsFulfilledByAmazon") else "M", "fb_count": fb.get("FeedbackCount"), "fb_pct": fb.get("SellerPositiveFeedbackRating"),
                      "ships_from": (o.get("ShipsFrom") or {}).get("State"), "hours": (o.get("ShippingTime") or {}).get("maximumHours"),
                      "prime": (o.get("PrimeInformation") or {}).get("IsPrime"), "last": today})
        time.sleep(pause)
    prof["meta"]["last_sweep"] = today
    json.dump(prof, open(os.path.join(S, "sellers.json"), "w"), indent=1)
    print("seller profiles: %d sellers from %d ASINs" % (len(prof["sellers"]), n))
    return prof


def report(me, prof):
    win = jl("bbwin.jsonl")
    if not win: print("no bbwin data yet"); return
    snaps = {}
    try:
        L = open(os.path.join(S, "snapshots.tsv")).read().splitlines(); h = L[0].split("\t")
        for l in L[1:]:
            r = dict(zip(h, l.split("\t"))); snaps.setdefault(r["asin"], []).append(r)
    except Exception: pass
    by = collections.defaultdict(list)
    for w in win: by[w["asin"]].append(w)
    rows, sell = [], collections.defaultdict(lambda: {"asins": set(), "wins": 0, "obs": 0})
    for a, L in by.items():
        we = sum(1 for w in L if w["win"][0]["seller"] == me)
        others = collections.Counter(w["win"][0]["seller"] for w in L if w["win"][0]["seller"] != me)
        top = others.most_common(1)[0][0] if others else ""
        lastw = L[-1]["win"][0]
        sn = snaps.get(a) or []
        own = float(sn[-1]["own_price"]) if sn and sn[-1].get("own_price") else None
        for w in L:
            s = w["win"][0]["seller"]
            sell[s]["asins"].add(a); sell[s]["wins"] += 1
        p = prof.get("sellers", {}).get(top, {})
        rows.append([a, sn[-1]["sku"] if sn else "", len(L), "%.2f" % (we / len(L)), top, lastw["type"], lastw["price"], own or "",
                     ("%.1f" % (100 * (own / lastw["price"] - 1))) if own and lastw["price"] else "", p.get("fb_count", ""), p.get("fb_pct", ""), p.get("ships_from", ""), p.get("hours", "")])
    with open(os.path.join(S, "bb_report.tsv"), "w") as fh:
        fh.write("asin\tsku\tobs\twe_win_share\ttop_rival\tlast_winner_type\tlast_winner_price\town_price\tgap_pct\trival_fb_count\trival_fb_pct\trival_ships_from\trival_hours\n")
        for r in sorted(rows, key=lambda r: float(r[3])): fh.write("\t".join(str(x) for x in r) + "\n")
    with open(os.path.join(S, "bb_sellers.tsv"), "w") as fh:
        fh.write("seller\tis_me\tasins_won_on\tobs_won\ttype\tfb_count\tfb_pct\tships_from\thours\tprime\n")
        for s, d in sorted(sell.items(), key=lambda kv: -kv[1]["wins"]):
            p = prof.get("sellers", {}).get(s, {})
            fh.write("\t".join(str(x) for x in [s, int(s == me), len(d["asins"]), d["wins"], p.get("type", ""), p.get("fb_count", ""), p.get("fb_pct", ""), p.get("ships_from", ""), p.get("hours", ""), p.get("prime", "")]) + "\n")
    print("bb report: %d ASINs, %d winning sellers (we win %.0f%% of observations)" % (len(rows), len(sell), 100 * sum(1 for w in win if w["win"][0]["seller"] == me) / len(win)))


def main():
    c = spapi.load_creds(HERE)
    me = c.get("SELLER_ID") or (open(os.path.join(S, "seller.txt")).read().strip() if os.path.exists(os.path.join(S, "seller.txt")) else "")
    win = jl("bbwin.jsonl")
    latest = {}
    for w in win: latest[w["asin"]] = w
    todo = sorted(a for a, w in latest.items() if w["win"][0]["seller"] != me)
    prof = sweep(c, me, todo) if todo else {"meta": {}, "sellers": {}}
    report(me, prof)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("bb_intel failed (ignored): %r" % e)
