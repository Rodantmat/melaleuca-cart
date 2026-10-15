import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import melaleuca_scan as ms, melaleuca_run as mr
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
env = mr.read_env(os.path.join(HERE, "credentials.env"))
acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
cfg = {"proxy": env["PROXY_URL"], "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "fast": True, "early_route": True}
with sync_playwright() as p:
    s = ms.Session(p, acct, 7, cfg, 10007); s.login()
    s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); s.settle(8000)
    print("LAST", json.dumps(s.last)[:600])
    print("PERF", [u for u in s.page.evaluate("() => performance.getEntriesByType('resource').map(e => e.name)") if "/api/" in u][:20])
    s.close()
