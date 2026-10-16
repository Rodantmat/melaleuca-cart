"""lab probe: how does the Canadian store hand out the choices of an offer item (34050)?"""
import os, sys, json, re
from playwright.sync_api import sync_playwright
import melaleuca_scan as ms
import melaleuca_fill as mf
import melaleuca_run as mr
HERE = os.path.dirname(os.path.abspath(__file__))
env = mr.read_env(os.path.join(HERE, "credentials.env"))
an = 1
acct = {"tab": "David H", "n": an, "user": env["MELA_USER_1"], "pass": env["MELA_PASS_1"], "region": "vancouver"}
cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": int(env.get("STICKY_BASE") or 10000), "headless": True, "channel": "", "session_minutes": 120,
       "debug_dir": os.path.join(HERE, "feed", "debug"), "fast": True, "early_route": True}
mf.REG = "ca"
with sync_playwright() as p:
    s = ms.Session(p, dict(acct, geo_level=0), an, cfg, None)
    s.login()
    print("signed in", flush=True)
    for u in ["/api/shelf?Sku=34050&sc_lang=en-US&sc_site=productstoreCa", "/api/shelf?Sku=34050&sc_lang=en-CA&sc_site=productstoreCa",
              "/api/shelf?Sku=34050", "/api/shelf?Sku=34050&sc_lang=en-US&sc_site=productstoreUs", "/api/shelf?Sku=34050&sc_lang=en-US&sc_site=productstoreCa&sc_itemid=%7BFE1DED98-281E-46FA-9656-7D6A0C2E436D%7D"]:
        try:
            r = s._fetch1(u)
            print("URL", u, "->", r.get("status"), str(r.get("json") or r.get("text"))[:300], flush=True)
        except Exception as e:
            print("URL", u, "ERR", str(e)[:100], flush=True)
    print("page origin:", s.page.url[:60], flush=True)
    for sku in ("3441",):
        pg = s.page
        pg.goto("%s/products/%s?sc_lang=en-US" % (mf.BASE, sku), wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(3000)
        h = pg.content()
        print("PDP", sku, pg.url[:100], len(h), json.dumps(mf.parse_info(h))[:600], flush=True)
    # what does the cart page / offers page call?
    del s.json_log[:]
    s.page.goto(mf.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
    s.settle(8000)
    seen = []
    for u, m, j in s.json_log:
        pu = re.sub(r"\?.*", "", u)
        if pu not in seen:
            seen.append(pu)
    print("API calls of the cart page:", seen, flush=True)
    # the special offers listing
    del s.json_log[:]
    for path in ("/productstore/special-offers", "/special-offers", "/productstore/extra-savings"):
        try:
            s.page.goto(mf.BASE + path + "?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            s.settle(6000)
            print("PAGE", path, s.page.url[:100], flush=True)
        except Exception as e:
            print("PAGE", path, "ERR", str(e)[:80], flush=True)
    seen = []
    for u, m, j in s.json_log:
        pu = re.sub(r"\?.*", "", u)
        if pu not in seen:
            seen.append(pu)
    print("API calls of the offer pages:", seen, flush=True)
    for u, m, j in s.json_log:
        if "34050" in json.dumps(j)[:200000]:
            print("34050 appears in", u[:140], flush=True)
    s.close()
