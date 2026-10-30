"""probe_orders3 (LAB, read only, output sanitised): the card of an order with tracking, the receipt api (structure), what a tracking link does. usage: python melaleuca_probe_orders3.py 7 4 1"""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def clean(t):
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", t)
    t = re.sub(r"\b1Z[0-9A-Z]{16}\b", lambda m: m.group(0)[:4] + "..." + m.group(0)[-3:], t)
    t = re.sub(r"\b\d{9,}\b", lambda m: m.group(0)[:3] + "..." + m.group(0)[-2:], t)
    return t

KEEP = re.compile(r"city|state|province|country|carrier|status|track|ship|date|method|delivery|eta|url|link", re.I)
PII = re.compile(r"name|address|street|phone|email|zip|postal|line|attention|user|first|last", re.I)

def shape(o, k="", d=0):
    if d > 8: return "..."
    if isinstance(o, dict): return {a: shape(b, a, d + 1) for a, b in list(o.items())[:50]}
    if isinstance(o, list): return [shape(o[0], k, d + 1), "(%d items)" % len(o)] if o else []
    if isinstance(o, str):
        if PII.search(k) and not re.search(r"city|state|province|country", k, re.I): return "<pii>"
        return clean(o)[:80]
    return o

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
            cards = pg.evaluate("""() => [...document.querySelectorAll('ul.m-po__header')].slice(0, 6).map(u => {
                const tr = u.querySelector('li.m-po__track');
                return {text: u.innerText.replace(/\\s+/g, ' ').slice(0, 220), trackHtml: tr ? tr.outerHTML.replace(/\\s+/g, ' ').slice(0, 1500) : null,
                        hasStatus: [...u.children].map(c => c.className.slice(0, 40))};
            })""")
            for c in cards:
                print("CARD:", clean(c["text"])); print("   cols:", c["hasStatus"]); print("   track:", clean(c["trackHtml"] or "-"))
            # receipt api for the newest order
            num = pg.evaluate("() => (document.querySelector('.m-po__number.-value, .m-po__number .-value, span.m-po__number') || {}).innerText || ''")
            first = pg.evaluate("() => (document.querySelector('ul.m-po__header span.m-po__number.-value') || {}).innerText || ''")
            print("first order number length:", len(first.strip()))
            if first.strip():
                r = s.fetch("/api/receipt/%s?sc_lang=%s&sc_site=%s" % (first.strip(), "en-CA" if region != "socal" else "en-US", "productstoreCa" if region != "socal" else "productstoreUs"))
                print("receipt api status:", r.get("status")); print(json.dumps(shape(r.get("json") or r.get("text")))[:3500])
            # what does a tracking link do?
            tl = pg.locator("li.m-po__track a, li.m-po__track button").first
            if tl.count():
                print("tracking element:", clean(tl.evaluate("e => e.outerHTML.slice(0, 400)")))
                try:
                    with pg.context.expect_page(timeout=8000) as npg:
                        tl.click(timeout=8000)
                    print("opened new page:", clean(npg.value.url)[:200]); npg.value.close()
                except Exception as e:
                    print("click -> no new page;", pg.url[:100], "| dialogs:", pg.locator("[role=dialog]:visible").count(), "|", clean(re.sub(r"\s+", " ", pg.locator("[role=dialog]:visible").first.inner_text())[:400]) if pg.locator("[role=dialog]:visible").count() else "")
            s.close()

main()
