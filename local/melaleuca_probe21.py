"""probe21 (LAB, account 7): step by step through the coupon dialog ('Your Choices') of the Revive coupon; prints what is in the dialog; takes out the line it adds."""
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
    return (js.get("Data") or {}).get("Items") or []

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
                        b = (rq.post_data or "")[:600]
                    except Exception:
                        b = "<binary>"
                    reqs.append({"m": rq.method, "u": rq.url[:150], "body": b})
            except Exception:
                pass
        s.ctx.on("request", on_req)
        ids0 = {str(i.get("LineId")) for i in cart(s)}
        pg = s.page
        pg.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); s.settle(5000)
        pg.locator("button.o-accordion__toggler", has_text="Your Coupons").first.click(timeout=8000); pg.wait_for_timeout(2000)
        card = pg.locator("article.-cartCoupons").filter(has_text="Revive").first
        card.locator("button.-cartCoupon").first.click(timeout=8000); pg.wait_for_timeout(3000)
        dlg = pg.locator("[role=dialog]:visible").first
        print("DIALOG HTML:", dlg.evaluate("e => e.outerHTML.slice(0, 5000)"))
        tog = dlg.locator(".o-accordion__toggler:visible")
        print("togglers:", tog.count())
        if tog.count():
            tog.first.click(timeout=4000); pg.wait_for_timeout(900)
            print("DIALOG AFTER OPENING THE BOX:", dlg.evaluate("e => e.innerText.slice(0, 600)"))
            opts = dlg.locator("button.m-refinerImage:visible")
            print("options:", opts.count(), [opts.nth(i).inner_text()[:30] for i in range(opts.count())])
            if opts.count():
                opts.first.click(timeout=4000); pg.wait_for_timeout(900)
        addb = dlg.locator("button", has_text=re.compile(r"add to cart", re.I)).last
        print("ADD TO CART button:", addb.evaluate("e => e.outerHTML.slice(0, 300)"), "| disabled:", addb.is_disabled())
        del reqs[:]
        addb.click(timeout=8000); pg.wait_for_timeout(5000)
        print("REQUESTS after ADD TO CART:", json.dumps(reqs)[:2500])
        print("dialog still open:", pg.locator("[role=dialog]:visible").count())
        new = [i for i in cart(s) if str(i.get("LineId")) not in ids0]
        print("NEW LINES:", [(i.get("Sku"), i.get("LineId"), i.get("LineType"), i.get("Quantity"), i.get("RawPrice"), i.get("RawPoints"), i.get("PromotionId")) for i in new])
        for i in new:
            s.remove_line(i["LineId"])
        print("FINAL same as before:", {str(i.get("LineId")) for i in cart(s)} == ids0)
        s.close()

if __name__ == "__main__":
    main()
