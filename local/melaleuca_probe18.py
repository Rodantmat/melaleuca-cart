"""probe18 (LAB, account 7): find how the cart page sends 'Buy with Loyalty Shopping Dollars' and the coupon add buttons: (1) look in the page's scripts for the api calls,
(2) real mouse clicks on the credit label / coupon button with the requests recorded.  Read-only apart from switching one credit box off and on again."""
import os, sys, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        reqs = []
        def on_req(rq):
            if rq.resource_type in ("fetch", "xhr") and rq.method != "GET":
                reqs.append({"m": rq.method, "u": rq.url[:160], "body": (rq.post_data or "")[:500]})
        s.ctx.on("request", on_req)
        scripts = []
        def on_resp(r):
            if r.request.resource_type == "script" and "melaleuca" in r.url:
                scripts.append(r.url)
        s.ctx.on("response", on_resp)
        s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s.settle(6000)
        print("scripts seen:", len(scripts))
        hits = {}
        for u in scripts[:80]:
            try:
                t = s.page.evaluate("async (u) => { const r = await fetch(u); return r.ok ? await r.text() : ''; }", u)
            except Exception:
                continue
            for m in re.finditer(r"[Ll]sd|BuyWithLsd|[Cc]artCoupon", t):
                seg = t[max(0, m.start() - 260): m.end() + 260]
                if "api/" in seg or "/cart" in seg.lower():
                    hits.setdefault(u.split("/")[-1][:40], []).append(seg.replace("\n", " "))
        for k, v in hits.items():
            print("SCRIPT", k, "matches:", len(v))
            for seg in v[:4]:
                print("    ...", seg[:520])
        # ---- real clicks
        try:
            card = s.page.locator("article, li, div").filter(has_text=re.compile(r"Item 4120 ")).filter(has=s.page.locator("input[name=BuyWithLsd]")).last
            html = card.locator("input[name=BuyWithLsd]").first.evaluate("e => (e.closest('label') || e.parentElement.parentElement).outerHTML.slice(0, 1200)")
            print("LABEL HTML:", html)
            lab = card.get_by_text("Buy with Loyalty Shopping Dollars").first
            for tag in ("CLICK 1", "CLICK 2"):
                del reqs[:]
                lab.click(timeout=8000, force=True)
                s.page.wait_for_timeout(4000)
                js = s.fetch(s.cart_url()).get("json") or {}
                it = [i for i in (js.get("Data") or {}).get("Items") or [] if str(i.get("Sku")) == "4120"]
                print(tag, "requests:", json.dumps(reqs)[:1500], "| 4120 LSD used:", it[0].get("LsdDollarsUsed") if it else None, "| summary LSD:", ((js.get("Data") or {}).get("Summary") or {}).get("LoyaltyShoppingDollars", {}).get("Used"))
        except Exception as e:
            print("label click failed:", str(e)[:300])
        try:
            del reqs[:]
            b = s.page.locator("button.-cartCoupon").first
            print("COUPON BUTTON:", b.evaluate("e => e.outerHTML.slice(0, 600)"), "| parent:", b.evaluate("e => e.closest('article').outerHTML.slice(0, 200)"))
            b.scroll_into_view_if_needed(timeout=5000)
            b.click(timeout=6000, force=True)
            s.page.wait_for_timeout(5000)
            dl = s.page.evaluate("() => Array.from(document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal]')).filter(e => e.getBoundingClientRect().width > 0).map(e => e.innerText.slice(0, 500))")
            js = s.fetch(s.cart_url()).get("json") or {}
            print("COUPON CLICK requests:", json.dumps(reqs)[:1500], "| dialogs:", json.dumps(dl)[:800], "| lines:", len((js.get("Data") or {}).get("Items") or []))
        except Exception as e:
            print("coupon click failed:", str(e)[:300])
        js = s.fetch(s.cart_url()).get("json") or {}
        its = (js.get("Data") or {}).get("Items") or []
        print("FINAL: lines", len(its), "points", ((js.get("Data") or {}).get("Summary") or {}).get("Points"), "| 4120/179 LSD:", [(i.get("Sku"), i.get("LsdDollarsUsed")) for i in its if str(i.get("Sku")) in ("4120", "179")])
        s.close()

if __name__ == "__main__":
    main()
