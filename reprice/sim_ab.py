"""A/B test of an engine change on the simulated market.   python sim_ab.py [skus_per_scenario] [days] [seed]   env SIM_MARKET=steep|calibrated
A = engine without the MATCH rule, B = engine with it.  Same worlds, same random numbers -> paired differences per SKU."""
import math, os, sys, statistics
import engine, sim

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    A = engine.cfg_with({"MATCH_ENABLED": False}); B = engine.cfg_with(dict({"MATCH_ENABLED": True}, **__import__("json").loads(os.environ.get("B_CFG", "{}"))))
    scn_list = sim.SCENARIOS
    diffs_all, viol = [], 0
    print("market=%s  %d SKUs x %d scenarios x %d days" % (sim.MARKET, n, len(scn_list), days))
    print("%-16s %10s %10s %9s | %6s %6s | paired mean diff +- se | B better in" % ("scenario", "profit A", "profit B", "B vs A", "chg A", "chg B"))
    for scn in scn_list:
        pa = pb = ca = cb = 0.0; d = []
        for k in range(n):
            seed = seed0 * 100000 + scn_list.index(scn) * 1000 + k
            a = sim.run(seed, scn, days, True, A); b = sim.run(seed, scn, days, True, B)
            pa += a["profit"]; pb += b["profit"]; ca += a["changes"]; cb += b["changes"]
            d.append(b["profit"] - a["profit"]); viol += len(b["viol"])
        diffs_all += d
        m = statistics.mean(d); se = statistics.pstdev(d) / math.sqrt(len(d))
        print("%-16s %10.0f %10.0f %+8.1f%% | %6.1f %6.1f | %+8.1f +- %-6.1f | %3.0f%%" % (scn, pa, pb, 100 * (pb - pa) / max(1, abs(pa)), ca / n, cb / n, m, se, 100 * sum(1 for x in d if x > 0.5) / len(d)))
    m = statistics.mean(diffs_all); se = statistics.pstdev(diffs_all) / math.sqrt(len(diffs_all))
    worse = sum(1 for x in diffs_all if x < -0.5); better = sum(1 for x in diffs_all if x > 0.5)
    print("\\nALL: mean profit change per SKU %+.1f +- %.1f (z=%.1f); better in %d, worse in %d, same in %d; safety violations in B: %d" % (m, se, m / se if se else 0, better, worse, len(diffs_all) - better - worse, viol))

main()
