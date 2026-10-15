"""probe19 (LAB, read only): where does the cart page's coupon 'add' button send its request? looks into the page's script text."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        scripts = []
        s.ctx.on("response", lambda r: scripts.append(r.url) if r.request.resource_type == "script" and "melaleuca" in r.url else None)
        s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s.settle(6000)
        for u in scripts:
            t = s.page.evaluate("async (u) => { const r = await fetch(u); return r.ok ? await r.text() : ''; }", u)
            print("SCRIPT", u[-50:], len(t))
            for pat in (r"-cartCoupon", r"o-cartCoupons", r"CouponPrice", r"LineType:\s*[\"']Coupon", r"[\"']Coupon[\"']"):
                for m in list(re.finditer(pat, t))[:3]:
                    print("  [%s] ...%s..." % (pat, t[max(0, m.start() - 500): m.end() + 700].replace("\n", " ")))
        s.close()

if __name__ == "__main__":
    main()
