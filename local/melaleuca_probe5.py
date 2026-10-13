"""probe5: how the category lists are paged (api url + parameters), to build a complete family map without scrolling."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_fill as mf
import melaleuca_run as mr
import melaleuca_scan as ms
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
        for cat in ("cleaning-and-laundry/laundry", "personal-care"):
            b = len(s.json_log)
            s.page.goto("%s/productstore/%s?sc_lang=en-US" % (ms.BASE, cat), wait_until="domcontentloaded", timeout=60000)
            s.page.wait_for_timeout(6000)
            out[cat] = []
            for u, m, j in s.json_log[b:]:
                if "/api/" in u:
                    cards = j.get("Cards") if isinstance(j, dict) else None
                    out[cat].append({"url": u, "method": m, "cards": len(cards) if cards else None, "keys": list(j)[:12] if isinstance(j, dict) else None,
                                     "total": {k: j.get(k) for k in j if isinstance(j.get(k), (int, str)) and k != "Html"} if isinstance(j, dict) else None})
            # does the page itself list a total?
            out[cat + "_text"] = " ".join(s.page.inner_text("body").split())[:600]
        # test the search box
        b = len(s.json_log)
        s.page.goto("%s/search?q=lemon+brite" % ms.BASE, wait_until="domcontentloaded", timeout=60000)
        s.page.wait_for_timeout(5000)
        out["search"] = [{"url": u, "cards": (len(j.get("Cards")) if isinstance(j, dict) and j.get("Cards") else None)} for u, m, j in s.json_log[b:] if "/api/" in u]
        out["search_url"] = s.page.url
        s.close()
    json.dump(out, open(os.path.join(FEED, "probe5.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)[:6000])

if __name__ == "__main__":
    main()
