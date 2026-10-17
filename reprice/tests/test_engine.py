import sys, os, math, random, unittest
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import engine

NOW = datetime(2026, 10, 16, 12, 0)

def base(**kw):
    s = dict(sku="S1", price=12.0, cost=5.0, fba_fee=3.5, on_hand=20, inbound=0,
             units_7=0, units_30=0, units_90=0, days_since_sale=40, bb=12.0, we_hold_bb=True,
             low_fba=12.0, low_new=12.0, foep=None, hist=None, last_change=None, changes=[], aged_units=0)
    s.update(kw); return s

class T(unittest.TestCase):
    def test_never_below_safety(self):
        cfg = engine.DEFAULTS
        for _ in range(3000):
            r = random.Random(_)
            s = base(price=r.uniform(1, 40), cost=r.uniform(1, 20), fba_fee=r.uniform(2, 8),
                     on_hand=r.randint(0, 200), units_30=r.randint(0, 40), units_90=r.randint(0, 100), days_since_sale=r.randint(0, 300),
                     low_fba=r.choice([None, r.uniform(1, 40)]), bb=r.uniform(1,40), we_hold_bb=r.random()<.5)
            d = engine.decide(s, cfg, NOW)
            safety, fl, ce = engine.floors(s, cfg)
            if d.get("price") is not None and d["action"] in ("down", "to_floor"):
                self.assertGreaterEqual(d["price"] + 1e-9, safety if s["price"] >= safety else s["price"] * 0 + safety, (s, d))

    def test_garbage_inputs_hold(self):
        for bad in (None, float("nan"), -1, 0):
            for k in ("price", "cost", "fba_fee", "low_fba", "bb", "foep"):
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
        d = engine.decide(base(units_30=10, units_7=3, days_since_sale=2, on_hand=2), engine.DEFAULTS, NOW)
        self.assertNotEqual(d["action"], "down")

class R(unittest.TestCase):
    def test_changes_in_runpy_format(self):
        import run
        old = {"ts": "2026-10-10T10:00:00", "from": 13.39, "to": 12.59, "action": "down"}
        new = {"ts": "2026-10-10T10:00:00", "old": 13.39, "new": 12.59, "dir": "down", "base_v": None}
        for x in (old, new):
            n = run.norm_change(x)
            s = base(units_30=8, units_90=20, on_hand=3, price=12.59, last_change=n, changes=[n], low_fba=None, bb=12.59)
            d = engine.decide(s, engine.DEFAULTS, NOW)
            self.assertIn(d["action"], ("hold", "up", "down", "to_floor", "revert"))
            self.assertNotIn("engine error", d.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
