"""LAB probe: how to read the status of an OnTrac package without a carrier account (output sanitised).  usage (from local/): python ../status/probe_ontrac.py 7 3"""
import json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import scrape as S
from playwright.sync_api import sync_playwright

def clean(t): return re.sub(r"\b([A-Z]\d{3})\d{8,}(\d{3})\b", r"\1...\2", re.sub(r"\b\d{9,}\b", lambda m: m.group(0)[:3] + "..", t))
PII = re.compile(r"name|address|street|phone|email|zip|postal", re.I)
def shape(o, k="", d=0):
    if d > 7: return "..."
    if isinstance(o, dict): return {a: shape(b, a, d + 1) for a, b in list(o.items())[:30]}
    if isinstance(o, list): return [shape(o[0], k, d + 1), "(%d)" % len(o)] if o else []
    return "<pii>" if (isinstance(o, str) and PII.search(k)) else (clean(o)[:60] if isinstance(o, str) else o)

nums = []
for an in [int(x) for x in sys.argv[1:]]:
    r = S.scrape(an, 50, log=lambda *a: None)
    print("account", an, "ok:", r["ok"], "|", r["error"][:200])
    for o in r["orders"]:
        for p in o["packages"]:
            if not p["n"].startswith("1Z"): nums.append((p["n"], p["href"]))
    if nums: break
print("non-UPS packages found:", len(nums), "| hosts:", sorted({re.sub(r'https?://([^/]+)/.*', r'\1', h) for _, h in nums}))
if nums:
    n, href = nums[0]
    print("store link pattern:", clean(href))
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
        pg = ctx.new_page(); seen = []
        def on(r):
            try:
                if r.request.resource_type in ("fetch", "xhr"):
                    t = r.text(); seen.append((r.request.method, r.url, r.status, t[:200000]))
            except Exception: pass
        pg.on("response", on)
        pg.goto(href, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(9000)
        print("landed:", clean(pg.url)[:150], "| title:", pg.title()[:60])
        print("TEXT:", clean(re.sub(r"\s+", " ", pg.inner_text("body"))[:900]))
        for m, u, st, t in seen[:25]:
            print("XHR", m, st, clean(u)[:150])
            try: print("   ", json.dumps(shape(json.loads(t)))[:900])
            except Exception: print("    (not json)", clean(t[:120]))
        b.close()
