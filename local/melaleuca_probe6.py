"""probe6: category paging parameter + product search api"""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def first(js):
    c = (js or {}).get("Cards") or []
    return [((x.get("InnerData") or {}).get("Data") or {}).get("FamilyID") for x in c[:3]], len(c), (js or {}).get("CurrentPage"), (js or {}).get("TotalResults")

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    out = {}
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        b = len(s.json_log)
        s.page.goto("%s/productstore/personal-care?sc_lang=en-US" % ms.BASE, wait_until="domcontentloaded", timeout=60000)
        s.page.wait_for_timeout(5000)
        base = None
        for u, m, j in s.json_log[b:]:
            if "/api/category/search/" in u:
                base = u
        out["base"] = base
        r = s.fetch(base)
        out["p1"] = first(r.get("json"))
        for k in ("page", "currentPage", "pageNumber", "p", "pageIndex", "Page"):
            r = s.fetch(base + "&%s=2" % k)
            out["try_" + k] = first(r.get("json"))
        for term in ("melaboost", "splash", "original shampoo"):
            u = "%s/api/productstore/search/products?searchTerm=%s&pageSize=40&sc_lang=en-US" % (ms.BASE, term.replace(" ", "%20"))
            r = s.fetch(u)
            js = r.get("json") or {}
            out["search_" + term] = {"status": r.get("status"), "keys": list(js)[:10] if isinstance(js, dict) else None, "first": first(js.get("Data") if isinstance(js.get("Data"), dict) else js),
                                     "titles": [((x.get("InnerData") or {}).get("Data") or {}).get("Title") for x in ((js.get("Data") or js).get("Cards") or [])][:8] if isinstance(js, dict) else None,
                                     "text": (r.get("text") or "")[:300] if not js else ""}
        s.close()
    json.dump(out, open(os.path.join(FEED, "probe6.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)[:5000])

if __name__ == "__main__":
    main()
