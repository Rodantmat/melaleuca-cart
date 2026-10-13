"""probe12 (LAB): what happens when item 33961 (Revive with bottle) is added - full answer of the store; empties the cart afterwards."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    out = {}
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        try:
            for sku in ("33961",):
                s.page.goto("%s/products/%s?sc_lang=en-US" % (ms.BASE, sku), wait_until="domcontentloaded", timeout=60000)
                s.page.wait_for_timeout(3000)
                h = s.page.content()
                out["url"] = s.page.url
                out["title"] = re.findall(r"<title>([^<]*)", h)[:1]
                out["info"] = mf.parse_info(h)
                out["variants"] = mf.parse_variants(h)
                variants = {
                  "A_all": [{"FeatureSku":"F994","SelectedSku":"32993"},{"FeatureSku":"799","SelectedSku":None},{"FeatureSku":"33004","SelectedSku":None},{"FeatureSku":"33008","SelectedSku":None},{"FeatureSku":"32994","SelectedSku":None}],
                  "B_feat_only": [{"FeatureSku":"F994","SelectedSku":"32993"}],
                  "C_static_self": [{"FeatureSku":"F994","SelectedSku":"32993"},{"FeatureSku":"799","SelectedSku":"799"},{"FeatureSku":"33004","SelectedSku":"33004"},{"FeatureSku":"33008","SelectedSku":"33008"},{"FeatureSku":"32994","SelectedSku":"32994"}],
                  "D_nostatic_conf": [{"FeatureSku":"F994","SelectedSku":"32993"},{"FeatureSku":"32994","SelectedSku":None}],
                }
                out["tried"] = {}
                for k, conf in variants.items():
                    body = {"Sku": sku, "Quantity": 1, "Configurations": conf, "PromotionId": "", "LineType": "Normal", "LineId": "", "Position": None}
                    r = s.fetch(s.cart_url(), "POST", body)
                    it = ((r.get("json") or {}).get("Data") or {}).get("Item") or {}
                    out["tried"][k] = {"status": r.get("status"), "ok": (r.get("json") or {}).get("Success"), "val": [v.get("ValidationCode") + ":" + v.get("Status") for v in it.get("Validation") or []], "pts": (it.get("Details") or {}).get("RawPoints"), "line": (it.get("Details") or {}).get("LineId")}
                    c = s.fetch(s.cart_url())
                    out["tried"][k]["cart"] = [(i.get("LineId"), i.get("Sku"), i.get("RawPoints")) for i in mf.cart_items(c.get("json"))]
                    for i in mf.cart_items(c.get("json")):
                        s.remove_line(i["LineId"])
        finally:
            try:
                r = s.fetch(s.cart_url())
                for it in ((r.get("json") or {}).get("Data") or {}).get("Items") or []:
                    s.remove_line(it["LineId"])
            except Exception as e:
                print("CLEANUP PROBLEM", e)
            s.close()
    print(json.dumps(out, indent=1)[:6000])

if __name__ == "__main__":
    main()
