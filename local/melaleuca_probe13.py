"""probe13 (LAB): does a filled cart survive closing the browser and signing in again? (adds 2 items, closes, signs in with a NEW browser, reads the cart, empties it)"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def summ(s):
    js = s.fetch(s.cart_url()).get("json")
    return [(i.get("Sku"), i.get("Quantity")) for i in mf.cart_items(js)], ((js or {}).get("Data") or {}).get("Summary", {}).get("Points")

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        fl = mf.Filler(s)
        try:
            fl.clear()
            for sku, q in (("3620", 1), ("6600", 1)):
                a = mf.Action("single", sku, q); print("add", sku, fl.post(a))
            print("A same session:", summ(s))
            s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); s.settle(3000)
            print("A after cart page:", summ(s))
            s.close()
        except Exception as e:
            print("ERR", e)
    time.sleep(5)
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        fl = mf.Filler(s)
        print("B new browser, signed in again:", summ(s))
        print("cleared", fl.clear(), "->", summ(s))
        s.close()

if __name__ == "__main__":
    main()
