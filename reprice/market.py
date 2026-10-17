"""Market-depth estimate from our own saved offer snapshots (no scraping, no account).  usage: python market.py -> state/market.tsv
Competitor stock is not published by Amazon, so it is INFERRED from how the offers behave over time:
  sellers      : other sellers with a new offer right now (FBA / FBM)
  entered/left : sellers that appeared / vanished since the first snapshot (a vanished FBA seller usually sold out or stopped)
  stability    : share of snapshots in which the cheapest rival was the same seller (a seller that holds the low price for weeks has deep stock)
  undercut_runs: how often the cheapest rival moved its price down between snapshots (price pressure)
  room_above   : gap between our price and the next rival ABOVE us (room to raise)
  pressure     : LOW / MEDIUM / HIGH   (HIGH = several FBA sellers, rival stable at the bottom and cutting)"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(HERE, "state")


def analyse(rows, own=None):
    """rows: chronological list of ladders ([[seller, 'F'|'M', price], ...]) for one ASIN -> metrics dict"""
    if not rows:
        return None
    last = rows[-1]
    first_set, last_set = {x[0] for x in rows[0] if x[1] == "F"}, {x[0] for x in last if x[1] == "F"}
    lows = []
    for lad in rows:
        fb = sorted((x[2], x[0]) for x in lad if x[1] == "F")
        lows.append(fb[0] if fb else None)
    seen = [l for l in lows if l]
    stab = (collections.Counter(s for _, s in seen).most_common(1)[0][1] / len(seen)) if seen else 0.0
    cuts = sum(1 for a, b in zip(seen, seen[1:]) if b[0] < a[0] - 0.005)
    above = sorted(x[2] for x in last if own and x[2] > own * 1.005)
    nF = len({x[0] for x in last if x[1] == "F"})
    nM = len({x[0] for x in last if x[1] == "M"})
    snaps = len(rows)
    if nF == 0 and nM == 0: press = "NONE"
    elif nF >= 3 and (snaps < 4 or (stab >= 0.6 and cuts >= 1)): press = "HIGH"
    elif nF >= 2 or (nF == 1 and cuts >= 2): press = "MEDIUM"
    else: press = "LOW"
    return {"sellers_fba": nF, "sellers_fbm": nM, "entered": len(last_set - first_set), "left": len(first_set - last_set), "stability": round(stab, 2), "undercut_runs": cuts,
            "room_above": round(above[0] / own - 1, 3) if above and own else "", "pressure": press, "snapshots": snaps}


def main():
    by = collections.defaultdict(list)
    for l in open(os.path.join(S, "offers.jsonl")):
        j = json.loads(l); by[j["asin"]].append(j["ladder"])
    own = {}
    try:
        for l in open(os.path.join(S, "snapshots.tsv")).read().splitlines()[1:]:
            c = l.split("\t")
            if c[4:5] and c[3]: own[c[2]] = float(c[3])
    except Exception:
        pass
    out = [(a, analyse(rows, own.get(a))) for a, rows in by.items()]
    cols = ["sellers_fba", "sellers_fbm", "entered", "left", "stability", "undercut_runs", "room_above", "pressure", "snapshots"]
    with open(os.path.join(S, "market.tsv"), "w") as fh:
        fh.write("asin\t" + "\t".join(cols) + "\n")
        for a, m in out:
            if m: fh.write(a + "\t" + "\t".join(str(m[c]) for c in cols) + "\n")
    print("market depth for %d products: %s" % (len(out), dict(collections.Counter(m["pressure"] for _, m in out if m))))


if __name__ == "__main__":
    main()
