"""probe17 (LAB, account 7): how the cart page applies Loyalty Shopping Dollars (the credit checkbox), what 'Your Coupons' holds, and whether a NEW
browser can open /checkout directly.  It never adds, removes or empties anything: the credit checkbox of one line is switched off and on again,
and the cart is compared before / after."""
import os, sys, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
import melaleuca_fill as mf
from playwright.sync_api import sync_playwright

def money(v):
    try:
        return float(str(v).replace("$", "").replace(",", "") or 0)
    except Exception:
        return 0.0

def snap(s):
    js = s.fetch(s.cart_url()).get("json") or {}
    its = (js.get("Data") or {}).get("Items") or []
    return [(i.get("Sku"), i.get("LineId"), i.get("Quantity"), i.get("LsdEligible"), money(i.get("LsdDollarsUsed")), i.get("RawPrice"), i.get("RawPoints")) for i in its], (js.get("Data") or {}).get("Summary", {}), js

def main():
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": 7, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    os.makedirs(FEED, exist_ok=True)
    with sync_playwright() as p:
        s = ms.Session(p, acct, 7, cfg, None); s.login()
        before, sm, js = snap(s)
        print("CART BEFORE: %d lines, points %s, LSD used %s" % (len(before), sm.get("Points"), (sm.get("LoyaltyShoppingDollars") or {}).get("Used")))
        for b in before:
            print("   ", b)
        json.dump(js, open(os.path.join(FEED, "probe17_cart_before.json"), "w"))
        reqs = []
        def on_req(rq):
            if rq.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/" in rq.url:
                reqs.append({"m": rq.method, "u": rq.url[:200], "body": (rq.post_data or "")[:600]})
        s.ctx.on("request", on_req)
        s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s.settle(6000)
        # ---- coupons box (read only)
        try:
            tg = s.page.locator("text=Your Coupons").first
            tg.click(timeout=5000)
            s.page.wait_for_timeout(2500)
            box = s.page.evaluate("""() => { const t = Array.from(document.querySelectorAll('*')).find(e => e.children.length < 3 && /^\\s*Your Coupons\\s*$/.test(e.innerText||''));
                 let b = t; for (let k = 0; k < 6 && b && b.parentElement; k++) { b = b.parentElement; if ((b.innerText||'').length > 200) break; }
                 return b ? {text: b.innerText.slice(0, 1500), html: b.outerHTML.slice(0, 6000)} : null; }""")
            print("YOUR COUPONS:", json.dumps(box)[:2500])
        except Exception as e:
            print("coupon box not opened:", str(e)[:150])
        # ---- the credit checkbox of one line: off, then on again
        lines = [b for b in before if b[3]]
        pick = [b for b in lines if (b[4] or 0) > 0] or lines
        print("lines eligible for the credit:", len(lines), "| using the one already checked:" if pick and (pick[0][4] or 0) > 0 else "| using (will be switched on and off again):", pick[:1])
        if pick:
            sku = str(pick[0][0])
            info = s.page.evaluate("""(sku) => { const ts = Array.from(document.querySelectorAll('*')).filter(e => /Buy with Loyalty Shopping Dollars/.test(e.innerText||'') && e.children.length < 4);
                 for (const t of ts) { let b = t; for (let k = 0; k < 10 && b.parentElement; k++) { b = b.parentElement; if ((b.innerText||'').includes('Item ' + sku + ' ')) { const cb = b.querySelector('input[type=checkbox]');
                    return {html: t.outerHTML.slice(0, 1500), cb: cb ? cb.outerHTML.slice(0, 600) : null, checked: cb ? cb.checked : null}; } } } return null; }""", sku)
            print("CHECKBOX DOM:", json.dumps(info)[:2500])
            def toggle(tag):
                del reqs[:]
                ok = s.page.evaluate("""(sku) => { const ts = Array.from(document.querySelectorAll('*')).filter(e => /Buy with Loyalty Shopping Dollars/.test(e.innerText||'') && e.children.length < 4);
                    for (const t of ts) { let b = t; for (let k = 0; k < 10 && b.parentElement; k++) { b = b.parentElement; if ((b.innerText||'').includes('Item ' + sku + ' ')) { const cb = b.querySelector('input[type=checkbox]'); (cb || t).click(); return true; } } } return false; }""", sku)
                s.page.wait_for_timeout(4000)
                print(tag, "clicked:", ok, "| requests:", json.dumps(reqs)[:1800])
                a, sm2, _ = snap(s)
                print("   cart now: points %s LSD used %s" % (sm2.get("Points"), (sm2.get("LoyaltyShoppingDollars") or {}).get("Used")), [x for x in a if str(x[0]) == sku])
            toggle("TOGGLE 1")
            toggle("TOGGLE 2 (back)")
        after, sm3, js3 = snap(s)
        print("CART AFTER: %d lines, points %s, LSD used %s | identical to before: %s" % (len(after), sm3.get("Points"), (sm3.get("LoyaltyShoppingDollars") or {}).get("Used"), after == before))
        if after != before:
            for b, a in zip(before, after):
                if a != b: print("   CHANGED", b, "->", a)
        # ---- a coupon card: press its add button, look at the request and the new line, take the line out again
        try:
            del reqs[:]
            n0 = len(snap(s)[0])
            btn = s.page.locator("button.-cartCoupon").first
            print("coupon buttons:", s.page.locator("button.-cartCoupon").count())
            btn.click(timeout=6000)
            s.page.wait_for_timeout(5000)
            print("COUPON ADD requests:", json.dumps(reqs)[:2000])
            a, sm4, js4 = snap(s)
            old_ids = {str(b[1]) for b in before}
            new = [x for x in a if str(x[1]) not in old_ids]
            print("   new lines after the coupon:", new)
            for it in (js4.get("Data") or {}).get("Items") or []:
                if str(it.get("LineId")) in {str(x[1]) for x in new}:
                    print("   line detail:", json.dumps({k: it.get(k) for k in ("Sku", "LineType", "PromotionId", "Title", "RawPrice", "RawPoints", "Quantity", "RevenueSource")}))
                    s.remove_line(it["LineId"])
            s.page.wait_for_timeout(2000)
        except Exception as e:
            print("coupon test failed:", str(e)[:200])
        after, sm3, js3 = snap(s)
        print("CART AFTER COUPON TEST: %d lines, points %s | identical to before: %s" % (len(after), sm3.get("Points"), after == before))
        # ---- a new browser opens /checkout directly
        s2 = ms.Session(p, acct, 7, cfg, None); s2.login()
        s2.page.goto(ms.BASE + "/checkout?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s2.settle(8000)
        print("NEW BROWSER /checkout ->", s2.page.url[:100])
        print("   text:", " ".join(s2.page.inner_text("body").split())[:700])
        s2.close(); s.close()

if __name__ == "__main__":
    main()
