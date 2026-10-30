"""probe_orders2 (LAB, read only): DOM of the order history cards, tracking links, receipt page. usage: python melaleuca_probe_orders2.py 7 4"""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def m(t):
    return re.sub(r"\d", "#", t)

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    tabs = {}
    for ln in open(os.path.join(FEED, "mel_tabs.txt"), encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 3 and p[0].strip().isdigit(): tabs[int(p[0])] = (p[1], p[3].strip().lower() if len(p) > 3 else "")
    for an in [int(x) for x in sys.argv[1:]] or [7]:
        name, colour = tabs[an]
        region = {"orange": "vancouver", "yellow": "toronto"}.get(colour, "socal")
        acct = {"tab": name, "n": an, "user": env["MELA_USER_%d" % an], "pass": env["MELA_PASS_%d" % an], "region": region}
        cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True, "early_route": True}
        print("=" * 30, an, region)
        with sync_playwright() as p:
            s = ms.Session(p, acct, an, cfg, None); s.login()
            pg = s.page
            pg.goto(ms.BASE + "/my-account/order-history", wait_until="domcontentloaded", timeout=60000); s.settle(8000)
            print("url:", pg.url[:90])
            info = pg.evaluate("""() => {
              const all = [...document.querySelectorAll('*')].filter(e => e.children.length > 2 && /Order #:/.test(e.innerText || '') && (e.innerText.match(/Order #:/g) || []).length === 1);
              all.sort((a, b) => a.innerText.length - b.innerText.length);
              const c = all[0]; if (!c) return null;
              return {html: c.outerHTML.replace(/\\s+/g, ' ').slice(0, 4500), links: [...c.querySelectorAll('a,button')].map(a => [a.tagName, (a.innerText || '').trim().slice(0, 30), a.getAttribute('href'), a.getAttribute('aria-label')]).slice(0, 14)};
            }""")
            print("FIRST CARD:", json.dumps(info)[:6000])
            n0 = len(s.json_log)
            try:
                b = pg.locator("a,button", has_text=re.compile(r"^\s*Track\s*$", re.I)).first
                print("track element count:", pg.locator("a,button", has_text=re.compile(r"^\s*Track\s*$", re.I)).count())
            except Exception as e:
                print("track err", e)
            for u, mth, js in s.json_log[n0:]:
                print("API", mth, u[:160])
            rec = pg.locator("a", has_text=re.compile(r"See Full Order Receipt", re.I)).first
            href = rec.get_attribute("href")
            print("receipt href:", m(href or ""))
            rec.click(timeout=15000); s.settle(7000)
            print("receipt url:", m(pg.url)[:120])
            t = re.sub(r"\s+", " ", pg.inner_text("main"))[:1800]
            print("RECEIPT TEXT:", m(t))
            for u, mth, js in s.json_log[n0:]:
                print("API", mth, u[:160], json.dumps(js)[:300] if re.search(r"order|ship|track", u, re.I) else "")
            s.close()

main()
