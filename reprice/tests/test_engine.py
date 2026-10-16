import sys, os, math, random, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine

NOW = datetime(2026, 10, 16, 12, 0)

def base(**kw):
    s = dict(asin="B0TEST", sku="S1", price=12.0, cost=5.0, fba_fee=3.5, fee_fixed=0.0,
             on_hand=20, units30=0, units7=0, days_since_sale=40, hist_median=12.0,
             market_low_fba=11.0, foep=None, has_buybox=True, changes_14d=0, last_change=None,
             frozen_until=None, manual_seen=False, comp_price=12.0, dos=60, aged_units=0)
    s.update(kw); return s

class T(unittest.TestCase):
    def test_never_below_safety(self):
        cfg = engine.DEFAULTS
        for _ in range(3000):
            r = random.Random(_)
            s = base(price=r.uniform(1, 40), cost=r.uniform(1, 20), fba_fee=r.uniform(2, 8),
                     on_hand=r.randint(0, 200), units30=r.randint(0, 40), days_since_sale=r.randint(0, 300),
                     market_low_fba=r.choice([None, r.uniform(1, 40)]), dos=r.uniform(0, 400),
                     hist_median=r.uniform(1, 40), changes_14d=r.randint(0, 5))
            d = engine.decide(s, cfg, NOW)
            safety, fl, ce = engine.floors(s, cfg)
            if d.get("price") is not None and d["action"] in ("down", "to_floor"):
                self.assertGreaterEqual(d["price"] + 1e-9, safety if s["price"] >= safety else s["price"] * 0 + safety, (s, d))

    def test_garbage_inputs_hold(self):
        for bad in (None, float("nan"), -1, 0):
            for k in ("price", "cost", "fba_fee", "hist_median", "market_low_fba"):
                s = base(); s[k] = bad
                d = engine.decide(s, engine.DEFAULTS, NOW)
                self.assertIn(d["action"], ("hold", "down", "up", "to_floor", "revert"))
                if d.get("price") is not None:
                    self.assertTrue(math.isfinite(d["price"]) and d["price"] > 0)

    def test_frozen_holds(self):
        d = engine.decide(base(frozen_until=NOW + timedelta(days=2)), engine.DEFAULTS, NOW)
        self.assertEqual(d["action"], "hold")

    def test_drought_steps_down_once_and_small(self):
        d = engine.decide(base(), engine.DEFAULTS, NOW)
        if d["action"] == "down":
            self.assertGreaterEqual(d["price"], 12.0 * (1 - engine.DEFAULTS["STEP_DOWN_MAX"]) - 0.011)

    def test_no_drop_when_little_stock(self):
        d = engine.decide(base(units30=10, units7=3, days_since_sale=2, on_hand=2), engine.DEFAULTS, NOW)
        self.assertNotEqual(d["action"], "down")

if __name__ == "__main__":
    unittest.main()
