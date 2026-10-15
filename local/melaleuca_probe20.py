"""probe20 (LAB, account 7): the 'Your Coupons' box of the cart page - what its add button does. Adds one coupon line and takes exactly that line out again."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def cart(s):
    js = s.fetch(s.cart_url()).get("json") or {}
    return (js.get("Data") or {}).get("Items") or [], (js.get("Data") or {}).get("Summary") or {}

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        reqs = []
        def on_req(rq):
            try:
                if rq.resource_type in ("fetch", "xhr") and rq.method != "GET" and "melaleuca.com/api" in rq.url:
                    try:
                        b = (rq.post_data or "")[:500]
                    except Exception:
                        b = "<binary>"
                    reqs.append({"m": rq.method, "u": rq.url[:150], "body": b})
            except Exception:
                pass
        s.ctx.on("request", on_req)
        s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s.settle(6000)
        before, sm = cart(s)
        ids0 = {str(i.get("LineId")) for i in before}
        print("BEFORE: %d lines, points %s" % (len(before), sm.get("Points")))
        s.page.locator("button.o-accordion__toggler", has_text="Your Coupons").first.click(timeout=8000)
        s.page.wait_for_timeout(2500)
        arts = s.page.locator("article.-cartCoupons")
        print("coupon cards:", arts.count(), [arts.nth(i).locator(".m-recentProduct__description").first.inner_text()[:70] for i in range(arts.count())])
        card = arts.filter(has_text="Revive").first
        btn = card.locator("button.-cartCoupon").first
        print("BUTTON:", btn.evaluate("e => e.outerHTML.slice(0, 500)"), "| visible:", btn.is_visible(), "| box:", btn.bounding_box())
        del reqs[:]
        btn.scroll_into_view_if_needed(timeout=5000)
        btn.click(timeout=8000)
        s.page.wait_for_timeout(6000)
        dl = s.page.evaluate("() => Array.from(document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal]')).filter(e => e.getBoundingClientRect().width > 0).map(e => e.innerText.slice(0, 600))")
        print("REQUESTS:", json.dumps(reqs)[:2500])
        print("DIALOGS:", json.dumps(dl)[:900])
        after, sm2 = cart(s)
        new = [i for i in after if str(i.get("LineId")) not in ids0]
        print("AFTER CLICK: %d lines, points %s | new lines:" % (len(after), sm2.get("Points")), [(i.get("Sku"), i.get("LineId"), i.get("LineType"), i.get("Quantity"), i.get("RawPrice"), i.get("RawPoints"), i.get("PromotionId"), i.get("RevenueSource")) for i in new])
        for i in new:
            s.remove_line(i["LineId"])
        s.page.wait_for_timeout(2500)
        fin, sm3 = cart(s)
        print("FINAL: %d lines, points %s | same lines as before: %s" % (len(fin), sm3.get("Points"), {str(i.get("LineId")) for i in fin} == ids0))
        s.close()

if __name__ == "__main__":
    main()
