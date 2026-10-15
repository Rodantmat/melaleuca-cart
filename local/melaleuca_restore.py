"""restore (LAB, account 7): put the credit checkbox of the Replenex line (sku 4120) back ON, then show the cart. Nothing else is touched."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def lines(s):
    js = s.fetch(s.cart_url()).get("json") or {}
    return (js.get("Data") or {}).get("Items") or [], (js.get("Data") or {}).get("Summary") or {}

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        its, sm = lines(s)
        print("BEFORE: points", sm.get("Points"), "LSD used", (sm.get("LoyaltyShoppingDollars") or {}).get("Used"), [(i.get("Sku"), i.get("LineId"), i.get("LsdDollarsUsed")) for i in its if str(i.get("Sku")) in ("4120", "179")])
        for i in its:
            if str(i.get("Sku")) == "4120" and not str(i.get("LsdDollarsUsed")).replace("$", "").strip() in ("4.23",):
                url = s.cart_url().replace("/api/cart?", "/api/cart/linetype?")
                r = s.fetch(url, "POST", {"LineId": str(i.get("LineId")), "LineType": "LSD", "Quantity": 1})
                print("POST linetype:", r.get("status"), str(r.get("json"))[:300])
        its, sm = lines(s)
        print("AFTER: points", sm.get("Points"), "LSD used", (sm.get("LoyaltyShoppingDollars") or {}).get("Used"), [(i.get("Sku"), i.get("LineId"), i.get("LsdDollarsUsed"), i.get("RawPoints")) for i in its if str(i.get("Sku")) in ("4120", "179")])
        s.close()

if __name__ == "__main__":
    main()
