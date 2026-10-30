"""LAB probe (sanitised): where does the store keep tracking numbers for an order whose order-history card shows none?  usage (from local/): python ../status/probe_track.py 10"""
import json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); LOCAL = os.path.join(os.path.dirname(HERE), "local"); sys.path.insert(0, HERE); sys.path.insert(0, LOCAL)
import scrape as S
import melaleuca_run as mr, melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def mk(t): return re.sub(r"\b(D\d{3})\d{8,}(\d{3})\b", r"\1...\2", re.sub(r"\b1Z\w{5}(\w{8})(\w{3})\b", r"1Z..\2", re.sub(r"\d{9,}", "#", t)))

def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, path + "." + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:6]): yield from walk(v, path + "[]")
    else: yield path, o

an = int(sys.argv[1])
env = mr.read_env(os.path.join(LOCAL, "credentials.env"))
name, colour = S.tab_info(an)
region = S.region_of(colour)
acct = {"tab": name, "n": an, "user": env["MELA_USER_%d" % an], "pass": env["MELA_PASS_%d" % an], "region": region}
cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": "/tmp", "fast": True, "early_route": True}
with sync_playwright() as p:
    s = ms.Session(p, acct, an, cfg, None); s.login(); pg = s.page
    urls = []
    pg.on("response", lambda r: urls.append((r.request.method, r.url)) if "melaleuca.com/api" in r.url else None)
    pg.goto(ms.BASE + "/my-account/order-history", wait_until="domcontentloaded", timeout=60000); s.settle(9000)
    cards = pg.evaluate(S.JS)
    print("cards:", [(c["date"], mk(c["number"]), len(c["opts"])) for c in cards[:4]])
    print("api calls on the order-history page:", sorted({re.sub(r"[?].*", "", re.sub(r"\d{6,}", "#", u)) for m, u in urls})[:30])
    c = cards[0]
    r = s.fetch("/api/receipt/%s?sc_lang=en-US&sc_site=productstoreUs" % c["number"])
    d = (r.get("json") or {}).get("Data") or {}
    print("receipt top-level keys:", [k for k in d.keys() if k != "Items"])
    for path, v in walk({k: v for k, v in d.items() if k != "Items"}):
        if re.search(r"track|ship|carrier|package|parcel|deliver|status", path, re.I) or (isinstance(v, str) and re.search(r"\bD\d{14}\b|\b1Z[0-9A-Z]{16}\b", v)):
            print("  ", path, "=", mk(str(v))[:90])
    # the page text of the card itself
    print("card text:", mk(pg.evaluate("() => document.querySelector('ul.m-po__header').innerText.replace(/\\s+/g,' ')"))[:200])
    for u in ("/api/orders/shipments/%s" % c["number"], "/api/order/tracking/%s" % c["number"], "/api/receipt/tracking/%s" % c["number"]):
        r = s.fetch(u + "?sc_lang=en-US&sc_site=productstoreUs"); print("try", re.sub(r"\d{6,}", "#", u), "->", r.get("status"), mk(json.dumps(r.get("json") or r.get("text"))[:200]))
    s.close()
