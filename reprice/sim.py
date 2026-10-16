"""
Market simulator + stress tests for the pricing engine.   python sim.py [n_skus] [days] [seed]
Compares the engine with leaving the price alone (static), over many random products and nasty market situations, and checks every safety rule
(S1-S6 of engine.py) on EVERY decision it takes.  Exit code 1 if any rule is broken or if the engine is worse than static on average.
"""
import math, random, sys
from datetime import datetime, timedelta
import engine

SCENARIOS = ["stable", "war", "big_seller", "gouge", "troll", "no_competitor", "demand_drop", "demand_boom", "mispriced_high", "mispriced_low"]


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(rng.gauss(lam, math.sqrt(lam)) + 0.5))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class World:
    def __init__(self, rng, scenario, days):
        self.rng, self.scn, self.days = rng, scenario, days
        self.cost = rng.uniform(2.5, 30)
        self.fba = rng.uniform(3.0, 7.5)
        margin = rng.uniform(1.25, 2.6)
        self.M0 = round((self.cost + self.fba) * margin / (1 - 0.15), 2)       # where the market trades
        self.lam0 = rng.choice([0.03, 0.08, 0.2, 0.5, 1.0, 2.0])               # units/day with the whole Buy Box at M0
        self.e = rng.uniform(1.2, 3.2)
        self.p0 = self.M0 * (1.15 if scenario == "mispriced_high" else (0.93 if scenario == "mispriced_low" else rng.uniform(0.98, 1.04)))
        self.p0 = round(self.p0, 2)
        self.stock = int(max(5, self.lam0 * rng.choice([20, 45, 90, 200])))
        self.restock_q = max(6, int(self.lam0 * 45))
        self.pending = []                      # (arrival day, qty)
        self.comp = self.M0 * rng.uniform(0.97, 1.03)
        self.d = 0
        self.last_sale_day = 0
        self.sales = []                        # (day, units, price)
        self.stock_hist = []

    def comp_price(self):
        r, s, d = self.rng, self.scn, self.d
        self.comp += (self.M0 - self.comp) * 0.05 + self.M0 * r.gauss(0, 0.004)
        p = self.comp
        if s == "war":
            p = min(p, self.M0 * (1 - 0.0008 * d))                      # a competitor who keeps going down
        elif s == "big_seller":
            p = self.M0 * 0.88 if d < self.days * 0.6 else self.M0 * 1.06
        elif s == "gouge" and 30 <= d < 34:
            p = self.M0 * 3.2
        elif s == "troll" and d in (50, 51):
            p = 0.01
        elif s == "no_competitor":
            return None
        return round(max(0.01, p), 2)

    def demand_mult(self):
        d, s = self.d, self.scn
        if s == "demand_drop" and d > self.days * 0.35:
            return 0.25
        if s == "demand_boom" and d > self.days * 0.35:
            return 2.5
        return 1.0 + 0.15 * math.sin(d / 20.0)

    def share(self, p, pc):
        if pc is None:
            return 1.0
        x = (p - pc) / pc
        z = max(-50.0, min(50.0, 60 * (x - 0.015)))
        return 1.0 / (1.0 + math.exp(z))                 # equal price ~ shared box; 3-4% above -> almost nothing

    def day(self, p, pc):
        self.d += 1
        for a in [a for a in self.pending if a[0] <= self.d]:
            self.stock += a[1]; self.pending.remove(a)
        lam = self.lam0 * self.demand_mult() * self.share(p, pc) * (p / self.M0) ** (-self.e)
        n = min(self.stock, poisson(self.rng, lam))
        if n:
            self.stock -= n
            self.last_sale_day = self.d
            self.sales.append((self.d, n, p))
        if self.stock < self.lam0 * 20 and not self.pending and self.d < self.days - 40:
            self.pending.append((self.d + 14, self.restock_q))
        self.stock_hist.append(self.stock)
        return n


def snapshot(w, price, pc, changes, last_change, pc_prev, now, day):
    u = lambda k: sum(n for d, n, p in w.sales if day - d < k)
    ist = lambda k: max(1, sum(1 for s in w.stock_hist[-k:] if s > 0)) if w.stock_hist else k
    sold_p = []
    for d, n, p in w.sales[-400:]:
        sold_p += [p] * min(n, 5)
    sold_p.sort()
    hist = None
    if len(sold_p) >= 6:
        hist = {"n": len(sold_p), "p_low": sold_p[int(0.07 * (len(sold_p) - 1))], "p_mid": sold_p[len(sold_p) // 2], "p_high": sold_p[int(0.95 * (len(sold_p) - 1))]}
    we_hold = (pc is None) or price <= pc * 1.005
    bb = price if we_hold else pc
    return {"sku": "SIM", "price": price, "cost": w.cost, "fba_fee": w.fba, "on_hand": w.stock, "inbound": sum(q for _, q in w.pending),
            "units_7": u(7), "units_30": u(30), "units_90": u(90), "in_stock_days_30": ist(30), "in_stock_days_7": ist(7),
            "days_since_sale": day - w.last_sale_day, "aged_units": 0, "bb": bb, "we_hold_bb": we_hold, "low_fba": pc, "low_new": pc,
            "foep": (pc * 0.995 if pc and not we_hold else None), "hist": hist, "last_change": last_change, "changes": changes}


def run(seed, scenario, days, use_engine, cfg):
    rng = random.Random(seed)
    w = World(rng, scenario, days)
    price = w.p0
    changes, last_change = [], None
    start = datetime(2026, 1, 1)
    viol = []
    nchg = 0
    profit = 0.0
    cap_cost = 0.0
    pc = w.comp_price()
    frozen_until, manual_flag, last_applied = None, False, price
    for day in range(days):
        now = start + timedelta(days=day, hours=9)
        pc = w.comp_price()
        if use_engine and rng.random() < 0.004:           # the owner changes a price by hand
            price = round(price * rng.uniform(0.9, 1.1), 2)
        if use_engine and day >= 20:
            # fault injection: some days the data is missing or garbage - the engine must hold
            roll = rng.random()
            snap = snapshot(w, price, pc, changes, last_change, None, now, day)
            snap["manual_seen"] = abs(price - last_applied) > 0.005
            snap["frozen_until"] = frozen_until
            if roll < 0.03:
                snap["cost"] = None
            elif roll < 0.05:
                snap["price"] = None
            elif roll < 0.07:
                snap["units_30"] = float("nan")
            dec = engine.decide(snap, cfg, now)
            if snap["manual_seen"] and snap["price"]:
                last_applied = price
            if dec.get("freeze_days") and dec["action"] in ("hold", "revert"):
                frozen_until = now + timedelta(days=dec["freeze_days"])
            if dec["action"] != "hold" and dec.get("price"):
                newp = dec["price"]
                safety, floor, ceil = engine.floors(snap, cfg)
                # ---- the safety rules, checked on every decision
                if safety is not None and newp < safety - 0.005 and dec["action"] != "to_floor":
                    viol.append(("S1 below safety floor", scenario, seed, day, price, newp, safety))
                if dec["action"] == "down" and newp < floor - 0.005 and "severe" not in dec["flags"]:
                    viol.append(("S1 below floor (not severe)", scenario, seed, day, price, newp, floor))
                if ceil and dec["action"] == "up" and newp > ceil + 0.005:
                    viol.append(("S1 above ceiling", scenario, seed, day, price, newp, ceil))
                if dec["action"] == "down" and (price - newp) > price * (cfg["STEP_DOWN_MAX"]) + 0.011 and (price - newp) > cfg["MIN_STEP"] + 0.011:
                    viol.append(("S2 step down too big", scenario, seed, day, price, newp))
                if dec["action"] == "up" and (newp - price) > price * cfg["STEP_UP"] + 0.011 and (newp - price) > cfg["MIN_STEP"] + 0.011:
                    viol.append(("S2 step up too big", scenario, seed, day, price, newp))
                if dec["action"] == "down" and snap["on_hand"] <= 0:
                    viol.append(("S6 lowered with no stock", scenario, seed, day, price, newp))
                n14 = sum(1 for c in changes if (now - c["ts"]) <= timedelta(days=14))
                if dec["action"] in ("down", "up") and n14 >= cfg["MAX_CHANGES_14D"]:
                    viol.append(("S3 too many changes", scenario, seed, day, n14))
                if last_change and dec["action"] in ("down", "up"):
                    hrs = (now - last_change["ts"]).total_seconds() / 3600
                    need = cfg["COOLDOWN_DOWN_H"] if dec["action"] == "down" else cfg["COOLDOWN_UP_H"]
                    if hrs < need - 0.01:
                        viol.append(("S3 cooldown", scenario, seed, day, hrs))
                ch = {"ts": now, "old": price, "new": newp, "dir": "up" if newp > price else "down", "base_v": dec.get("base_v")}
                changes.append(ch); last_change = ch
                price = newp
                last_applied = newp
                nchg += 1
        n = w.day(price, pc)
        profit += n * (price - w.cost - w.fba - 0.15 * price)
        cap_cost += w.stock * w.cost * 0.0004                         # money tied up: 0.04% a day
    return {"profit": profit - cap_cost, "units": sum(n for _, n, _ in w.sales), "end_stock": w.stock, "changes": nchg, "viol": viol,
            "final_price": price, "p0": w.p0, "cost": w.cost, "M0": w.M0}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    cfg = engine.cfg_with()
    tot = {"static": 0.0, "engine": 0.0}
    allviol = []
    print("%-16s %8s %8s | %9s %9s | %7s %7s | %s" % ("scenario", "SKUs", "chg/sku", "profit st.", "profit eng", "units st", "units en", "stock end st/en"))
    for scn in SCENARIOS:
        a = {"profit": 0, "units": 0, "end": 0}; b = {"profit": 0, "units": 0, "end": 0, "chg": 0}
        for k in range(n):
            seed = seed0 * 100000 + SCENARIOS.index(scn) * 1000 + k
            s = run(seed, scn, days, False, cfg)
            e = run(seed, scn, days, True, cfg)
            a["profit"] += s["profit"]; a["units"] += s["units"]; a["end"] += s["end_stock"] * s["cost"]
            b["profit"] += e["profit"]; b["units"] += e["units"]; b["end"] += e["end_stock"] * e["cost"]; b["chg"] += e["changes"]
            allviol += e["viol"]
        tot["static"] += a["profit"]; tot["engine"] += b["profit"]
        print("%-16s %8d %8.1f | %9.0f %9.0f | %7d %7d | $%.0f / $%.0f" % (scn, n, b["chg"] / n, a["profit"], b["profit"], a["units"], b["units"], a["end"], b["end"]))
    print("\nTOTAL profit net of money tied up:  static %.0f   engine %.0f   (%+.1f%%)" % (tot["static"], tot["engine"], 100 * (tot["engine"] - tot["static"]) / max(1, abs(tot["static"]))))
    print("safety-rule violations:", len(allviol))
    for v in allviol[:15]:
        print("   ", v)
    bad = bool(allviol) or tot["engine"] < tot["static"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
