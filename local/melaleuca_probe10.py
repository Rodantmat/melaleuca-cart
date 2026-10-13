"""probe10 (LAB, read only): every card title / sku / link of some categories - to find the item numbers of the 4-pack and 5-pack of the customizable cleaners."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    out = []
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        for cat in ("cleaning-and-laundry", "cleaning-and-laundry/cleaning", "member-savings-pack"):
            del s.json_log[:]
            s.page.goto("%s/productstore/%s?sc_lang=en-US" % (ms.BASE, cat), wait_until="domcontentloaded", timeout=60000)
            s.page.wait_for_timeout(6000)
            base = None; first = None
            for u, m, j in s.json_log:
                if "/api/category/search/" in u:
                    base, first = u, j
            if not base:
                print(cat, "no api"); continue
            total = int(first.get("TotalResults") or 0); got = len(first.get("Cards") or [])
            js = first
            if total > got and got:
                r = s.fetch(base + "&pageNumber=%d" % (-(-total // got)))
                js = r.get("json") or first
            print(cat, "total", total, "cards", len(js.get("Cards") or []))
            for c in js.get("Cards") or []:
                d = (c.get("InnerData") or {}).get("Data") or {}
                out.append({"cat": cat, "title": d.get("Title"), "sku": d.get("Sku"), "skus": [x.get("Sku") for x in d.get("Products") or []][:8], "pdp": d.get("PdpLink"), "pack": c.get("IsSavingPack")})
        s.close()
    json.dump(out, open(os.path.join(FEED, "probe10.json"), "w"), indent=1)
    for o in out:
        if re.search(r"custom|cleaners|4.pack|5.pack|4–pack|5–pack", o["title"] or "", re.I): print(o)

if __name__ == "__main__":
    main()
