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
    pass
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        sa = ms.Session(p, acct, 7, cfg, None); sa.login()
        fa = mf.Filler(sa)
        fa.clear()
        for sku in ("3620", "6600"):
            fa.post(mf.Action("single", sku, 1))
        print("A:", summ(sa))
        sb = ms.Session(p, acct, 7, cfg, None); sb.login()
        print("B (second browser, A still open):", summ(sb))
        print("A again after B signed in:", summ(sa))
        sb.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); sb.settle(4000)
        print("B cart page text:", " ".join(sb.page.inner_text("body").split())[:300])
        print("B after viewing cart page:", summ(sb))
        print("cleared A:", fa.clear(), summ(sa))
        sb.close(); sa.close()

if __name__ == "__main__":
    main()
