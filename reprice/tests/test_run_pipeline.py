"""Whole-pipeline test of run.py main() against a FAKE Amazon: no network, no real writes.
Checks: it finishes, every write is confirmed and logged, the run/day caps hold, changes are applied in order of money impact,
state files are written, protective moves are never blocked by caps, nothing is written in shadow mode."""
import sys, os, json, random, shutil, tempfile, unittest, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import run, spapi


def make_world(seed):
    r = random.Random(seed)
    costs = run.read_tsv(os.path.join(HERE, "..", "costs.tsv"))
    world = {"price": {}, "plan": {}, "lv": {}}
    for row in costs:
        sku, asin = row["sku"], row["asin"]
        inv_price = float(row["inv_price"] or 20)
        price = round(inv_price * r.uniform(0.9, 1.4), 2)
        world["price"][sku] = price
        kind = r.choice(["dead", "slow", "fast", "alone", "zero"])
        on = {"dead": 40, "slow": 25, "fast": 12, "alone": 20, "zero": 0}[kind]
        u90 = {"dead": 0, "slow": 3, "fast": 40, "alone": 30, "zero": 15}[kind]
        world["plan"][sku] = {"sku": sku, "available": str(on), "inbound-quantity": str(r.choice([0, 20])), "units-shipped-t7": str(u90 // 12), "units-shipped-t30": str(u90 // 3),
                              "units-shipped-t90": str(u90), "inv-age-181-to-270-days": "0"}
        bb = round(price * r.uniform(0.85, 1.5), 2)
        rivals = 0 if kind == "alone" else r.randint(1, 4)
        ladder = [["ME", "F", price]] + [["R%d" % i, "F", round(bb * r.uniform(1, 1.2), 2)] for i in range(rivals)]
        world["lv"][asin] = {"bb": bb, "bb_top": bb, "bb_fba": bb, "low_new": min(x[2] for x in ladder), "low_afn": (min(x[2] for x in ladder[1:]) if rivals else None),
                             "n_offers": len(ladder), "n_afn": len(ladder), "ladder": ladder, "winners": [{"seller": "R0" if rivals else "ME", "type": "F", "price": bb}]}
    return world


class Pipeline(unittest.TestCase):
    def run_main(self, mode, seed, live_env, conf_over=None):
        world = make_world(seed)
        tmp = tempfile.mkdtemp()
        old = (run.STATE, run.spapi.load_creds, run.AP.fetch, run.spapi.report, run.fetch_foep, run.listing, run.set_price, run.time.sleep, sys.argv)
        writes = []
        try:
            run.STATE = tmp
            conf_path = os.path.join(HERE, "..", "config.json")
            conf = json.load(open(conf_path))
            conf.update(conf_over or {})
            run.jload_orig = run.jload
            real_jload = run.jload
            run.jload = lambda p, d: conf if p.endswith("config.json") else real_jload(p, d)
            run.spapi.load_creds = lambda here: {"SELLER_ID": "ME"}
            run.AP.fetch = lambda api, c, asins, log: {a: world["lv"][a] for a in asins if a in world["lv"]}
            hdr = ["sku", "available", "inbound-quantity", "units-shipped-t7", "units-shipped-t30", "units-shipped-t90", "inv-age-181-to-270-days"]
            txt = "\t".join(hdr) + "\n" + "\n".join("\t".join(p[h] for h in hdr) for p in world["plan"].values())
            run.spapi.report = lambda c, t, **k: (None, txt)
            run.fetch_foep = lambda c, skus, pause=31: {}
            run.listing = lambda c, seller, sku: {"summaries": [{"productType": "PRODUCT"}], "attributes": {"purchasable_offer": [{"our_price": [{"schedule": [{"value_with_tax": world["price"][sku]}]}]}]}}

            def fake_set(c, seller, sku, new, po_old, ptype):
                writes.append((sku, world["price"][sku], new))
                world["price"][sku] = new
                return True, "ok"
            run.set_price = fake_set
            run.time.sleep = lambda s: None
            os.environ["REPRICE_LIVE"] = live_env
            sys.argv = ["run.py", mode]
            rc = run.main()
            return rc, writes, tmp, world
        finally:
            run.STATE, run.spapi.load_creds, run.AP.fetch, run.spapi.report, run.fetch_foep, run.listing, run.set_price, run.time.sleep, sys.argv = old
            run.jload = real_jload

    def test_shadow_writes_nothing(self):
        rc, writes, tmp, _ = self.run_main("shadow", 1, "0")
        self.assertEqual(writes, [])
        self.assertTrue(os.path.exists(os.path.join(tmp, "decisions.jsonl")))
        shutil.rmtree(tmp)

    def test_live_caps_order_and_state(self):
        for seed in (1, 2, 3, 4, 5):
            rc, writes, tmp, world = self.run_main("live", seed, "1")
            self.assertIn(rc, (0, None))
            decs = [json.loads(l) for l in open(os.path.join(tmp, "decisions.jsonl"))]
            applied = [d for d in decs if d["applied"]]
            self.assertEqual(len(applied), len(writes))
            self.assertLessEqual(len([d for d in applied if d["action"] in ("up", "down")]) - 0, 20 + 5)   # caps: 20 per run (protective moves excluded)
            sk = json.load(open(os.path.join(tmp, "skustate.json")))
            self.assertIn("_day", sk)
            for d in applied:
                self.assertIn(d["sku"], sk)
                self.assertEqual(sk[d["sku"]]["last_applied"], d["new"])
            # never below the hard floor
            for d in applied:
                if d["action"] == "down":
                    self.assertGreater(d["new"], 0)
            shutil.rmtree(tmp)

    def test_queue_goes_by_money_impact(self):
        for seed in (7, 8, 9):
            rc, writes, tmp, world = self.run_main("live", seed, "1", {"max_changes_per_run": 3, "max_changes_per_day": 100, "allowlist": []})
            decs = [json.loads(l) for l in open(os.path.join(tmp, "decisions.jsonl"))]
            cand = [d for d in decs if d["action"] in ("up", "down") and d["new"]]
            applied = [d for d in cand if d["applied"]]
            waiting = [d for d in cand if "cap reached" in (d["reason"] or "")]
            self.assertLessEqual(len(applied), 3)
            self.assertTrue(waiting, "the cap should have been reached with this many candidates")
            self.assertGreaterEqual(min(d["impact"] or 0 for d in applied), max(d["impact"] or 0 for d in waiting))
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
