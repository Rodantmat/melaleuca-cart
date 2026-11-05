"""Tests for the owner's pricing rules of 2026-11-04 (his words are quoted in engine.py / OPEN_QUESTIONS_FOR_OWNER.md)."""
import sys, os, random, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine

NOW = datetime(2026, 11, 4, 12, 0)
CFG = engine.DEFAULTS


def base(**kw):
    s = dict(sku="S1", price=20.0, cost=5.0, fba_fee=3.0, on_hand=20, inbound=0, units_7=0, units_30=0, units_90=0, days_since_sale=40,
             bb=20.0, we_hold_bb=True, low_fba=None, low_new=None, foep=None, hist=None, last_change=None, changes=[], aged_units=0, n_rivals=None)
    s.update(kw)
    return s


class Floor(unittest.TestCase):
    def test_owner_example_cost5_fees_total3_floor_is_9(self):
        # cost 5, total Amazon fees 3 at the floor price, 20% profit on cost (= 1) -> price 9.  Engine: fees = fba + 15% of price -> fba = 3 - 1.35
        s = base(cost=5.0, fba_fee=3.0 - 0.15 * 9.0)
        hard, floor, ceil = engine.floors(s, CFG)
        self.assertAlmostEqual(floor, 9.0, places=2)

    def test_slow_tiers(self):
        s = base(cost=5.0, fba_fee=1.65, days_since_sale=40)
        f40 = engine.floors(s, CFG)[1]
        f95 = engine.floors(dict(s, days_since_sale=95), CFG)[1]
        f130 = engine.floors(dict(s, days_since_sale=130), CFG)[1]
        self.assertGreater(f40, f95)
        self.assertGreater(f95, f130)
        # 5% profit tier is still above break-even
        cost_all = 5.0 + 1.65 + 0.15 * f130
        self.assertGreater(f130, cost_all)

    def test_no_stock_does_not_use_slow_tier(self):
        s = base(on_hand=0, days_since_sale=200)
        self.assertEqual(engine.floors(s, CFG)[1], engine.floors(dict(s, days_since_sale=1), CFG)[1])

    def test_history_floor_lifted_after_30_days_without_sale(self):
        hist = {"n": 20, "p_low": 18.0, "p_mid": 20.0, "p_high": 24.0}
        s = base(cost=5.0, fba_fee=1.65, hist=hist, days_since_sale=5)
        self.assertGreaterEqual(engine.floors(s, CFG)[1], 18.0)
        self.assertLess(engine.floors(dict(s, days_since_sale=45), CFG)[1], 18.0)


class Drops(unittest.TestCase):
    def test_drop_starts_after_30_days_and_is_mild(self):
        s = base(price=30.0, cost=5.0, fba_fee=2.0, on_hand=40, units_30=0, units_90=3, days_since_sale=31, low_fba=None, bb=30.0)
        d = engine.decide(s, CFG, NOW)
        self.assertEqual(d["action"], "down")
        self.assertGreaterEqual(d["price"], 30.0 * (1 - 0.04) - 0.011)

    def test_never_below_20pct_floor_before_90_days(self):
        for dss in (31, 60, 89):
            s = base(price=10.0, cost=5.0, fba_fee=1.65, on_hand=40, units_90=3, days_since_sale=dss, bb=10.0)
            d = engine.decide(s, CFG, NOW)
            fl = engine.floors(s, CFG)[1]
            if d["action"] == "down":
                self.assertGreaterEqual(d["price"], fl - 0.005)

    def test_stuck_at_floor_stays(self):
        fl = engine.floors(base(cost=5.0, fba_fee=1.65), CFG)[1]
        s = base(price=fl, cost=5.0, fba_fee=1.65, on_hand=40, units_90=3, days_since_sale=60, bb=fl)
        d = engine.decide(s, CFG, NOW)
        self.assertNotEqual(d["action"], "down")


class Raises(unittest.TestCase):
    def test_zero_stock_follows_rival_box_a_few_cents_under(self):
        s = base(price=20.0, on_hand=0, inbound=30, units_90=12, units_30=4, bb=27.50, we_hold_bb=False, days_since_sale=10,
                 hist={"n": 20, "p_low": 18.0, "p_mid": 21.0, "p_high": 26.0})
        d = engine.decide(s, CFG, NOW)
        self.assertEqual(d["action"], "up")
        self.assertAlmostEqual(d["price"], 27.47, places=2)

    def test_zero_stock_without_box_data_holds(self):
        s = base(price=20.0, on_hand=0, inbound=30, units_90=12, bb=None, we_hold_bb=None)
        self.assertEqual(engine.decide(s, CFG, NOW)["action"], "hold")

    def test_zero_stock_anomalous_box_is_ignored(self):
        s = base(price=20.0, on_hand=0, inbound=30, units_90=12, bb=80.0, we_hold_bb=False, hist={"n": 20, "p_low": 18.0, "p_mid": 21.0, "p_high": 26.0})
        self.assertEqual(engine.decide(s, CFG, NOW)["action"], "hold")

    def test_alone_raises_in_big_steps(self):
        s = base(price=25.0, cost=6.0, fba_fee=4.0, on_hand=30, units_7=3, units_30=12, units_90=30, days_since_sale=1, bb=25.0, we_hold_bb=True,
                 n_rivals=0, hist={"n": 30, "p_low": 22.0, "p_mid": 25.0, "p_high": 26.0})
        d = engine.decide(s, CFG, NOW)
        self.assertEqual(d["action"], "up")
        self.assertTrue(d.get("alone"))
        self.assertGreater(d["price"], 25.0 * 1.06)
        self.assertLessEqual(d["price"], 25.0 * 1.08 + 0.011)

    def test_not_alone_keeps_small_steps(self):
        s = base(price=25.0, cost=6.0, fba_fee=4.0, on_hand=8, units_7=3, units_30=12, units_90=30, days_since_sale=1, bb=25.0, we_hold_bb=True,
                 n_rivals=2, low_fba=30.0, hist={"n": 30, "p_low": 22.0, "p_mid": 25.0, "p_high": 28.0})
        d = engine.decide(s, CFG, NOW)
        if d["action"] == "up":
            self.assertLessEqual(d["price"], 25.0 * 1.10 + 0.011)
            self.assertFalse(d.get("alone"))


class Properties(unittest.TestCase):
    def test_random_snapshots_never_break_the_floor_or_caps(self):
        bad = []
        for i in range(40000):
            r = random.Random(i)
            cost = r.uniform(1, 40)
            s = base(price=r.uniform(2, 120), cost=cost, fba_fee=r.uniform(2, 9), on_hand=r.choice([0, 0, 1, 5, 40, 200]), inbound=r.choice([0, 20]),
                     units_7=r.randint(0, 10), units_30=r.randint(0, 40), units_90=r.randint(0, 120), days_since_sale=r.choice([0, 3, 15, 31, 60, 95, 125, 300]),
                     bb=r.choice([None, r.uniform(2, 150)]), we_hold_bb=r.choice([True, False, None]), low_fba=r.choice([None, r.uniform(2, 150)]),
                     n_rivals=r.choice([None, 0, 1, 3]),
                     hist=r.choice([None, {"n": 20, "p_low": cost * 2, "p_mid": cost * 3, "p_high": cost * 4}]))
            d = engine.decide(s, CFG, NOW)
            hard, floor, ceil = engine.floors(s, CFG)
            if d["action"] == "down":
                if d["price"] < hard - 0.005:
                    bad.append(("down below hard floor", i))
                if s["on_hand"] <= 0:
                    bad.append(("down without stock", i))
                if d["price"] < s["price"] * (1 - 0.04 * 1.5 - 0.2) - 0.02:
                    bad.append(("down too big", i))
            if d["action"] in ("up",):
                lim = max(CFG["STEP_UP_ALONE"], CFG["STEP_UP_BIG"], CFG["STEP_UP"])
                if not d.get("zero_stock") and d["price"] > s["price"] * (1 + lim) + 0.011:
                    bad.append(("up too big", i))
                if d["price"] < s["price"]:
                    bad.append(("up goes down", i))
            if d.get("zero_stock") and s["bb"] and d["price"] > s["bb"] - CFG["UNDER_BB"] + 0.005:
                bad.append(("zero stock above rival box", i))
            if d["action"] == "to_floor" and d["price"] < s["price"]:
                bad.append(("to_floor lowers", i))
        self.assertEqual(bad[:5], [])


if __name__ == "__main__":
    unittest.main()
