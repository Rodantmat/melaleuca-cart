import sys, os, unittest, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import run, bb_web


class T(unittest.TestCase):
    def test_stock_profile(self):
        t = dt.date(2026, 10, 20)
        d = {t - dt.timedelta(days=i): (0 if 3 <= i <= 12 else 5) for i in range(1, 19)}
        i30, i7, oos = run.stock_profile(d, t, 15)
        self.assertEqual((i30, oos), (13, 10))
        self.assertEqual(i7, 2)

    def test_stock_profile_no_data_means_in_stock(self):
        t = dt.date(2026, 10, 20)
        self.assertEqual(run.stock_profile({}, t, 40), (None, None, 0))
        self.assertEqual(run.stock_profile({t - dt.timedelta(days=1): 0}, t, 40)[:2], (None, None))   # too few known days: engine default

    def test_web_parse_aod_empty(self):
        self.assertEqual(bb_web.parse_aod("<html></html>"), {"pinned": None, "offers": []})

    def test_web_parse_dp_garbage(self):
        d = bb_web.parse_dp("<html>nothing</html>")
        self.assertIsNone(d["bb_price"]); self.assertIsNone(d["seller_id"])


if __name__ == "__main__":
    unittest.main()
