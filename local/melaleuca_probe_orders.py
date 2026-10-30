"""probe_orders (LAB, read only): finds where the store shows order history + tracking numbers. Prints only the STRUCTURE (names / personal data masked).
usage: python melaleuca_probe_orders.py 7 4"""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

PII = re.compile(r"name|address|street|phone|email|zip|postal|line1|line2|attention|user|first|last", re.I)

def mask(k, v):
    if isinstance(v, str):
        if PII.search(k or ""): return "<pii>"
        if re.search(r"\d{8,}", v) or re.fullmatch(r"[A-Z0-9]{10,}", v): return v[:4] + "..." + v[-3:]
        return v[:50]
    return v

def shape(o, k="", d=0):
    if d > 7: return "..."
    if isinstance(o, dict): return {a: shape(b, a, d + 1) for a, b in list(o.items())[:40]}
    if isinstance(o, list): return [shape(o[0], k, d + 1), "(%d items)" % len(o)] if o else []
    return mask(k, o)

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    tabs = {}
    for ln in open(os.path.join(FEED, "mel_tabs.txt"), encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 3 and p[0].strip().isdigit(): tabs[int(p[0])] = (p[1], p[3].strip().lower() if len(p) > 3 else "")
    for an in [int(x) for x in sys.argv[1:]] or [7]:
        name, colour = tabs[an]
        region = env.get("REGION_%d" % an, "").strip().lower() or {"orange": "vancouver", "yellow": "toronto"}.get(colour, "socal")
        acct = {"tab": name, "n": an, "user": env["MELA_USER_%d" % an], "pass": env["MELA_PASS_%d" % an], "region": region}
        cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True, "early_route": True}
        print("=" * 30, an, region)
        with sync_playwright() as p:
            s = ms.Session(p, acct, an, cfg, None); s.login()
            pg = s.page
            print("after login:", pg.url[:80])
            hrefs = pg.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.innerText.trim().slice(0,40), a.getAttribute('href')]).filter(x => /order|track|history|purchase/i.test(x[0] + x[1]))")
            print("links:", json.dumps(hrefs[:30]))
            seen = set()
            cands = [h[1] for h in hrefs if h[1].startswith("/") or "melaleuca.com" in h[1]][:4] + ["/account/orders", "/account/order-history", "/orders"]
            for c in cands:
                if c in seen: continue
                seen.add(c)
                n0 = len(s.json_log)
                try:
                    pg.goto(c if c.startswith("http") else ms.BASE + c, wait_until="domcontentloaded", timeout=60000); s.settle(7000)
                except Exception as e:
                    print("GOTO FAIL", c, str(e)[:80]); continue
                print("--- page", c, "->", pg.url[:90], "| title:", pg.title()[:60])
                for u, m, js in s.json_log[n0:]:
                    if re.search(r"order|track|ship|histor", u, re.I):
                        print("API", m, u[:140]); print(json.dumps(shape(js))[:2500])
                try:
                    print("TEXT:", re.sub(r"\s+", " ", pg.inner_text("main")[:900]) if pg.locator("main").count() else "(no main)")
                except Exception: pass
            s.close()

main()
