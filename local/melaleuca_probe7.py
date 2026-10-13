"""probe7 (LAB ONLY): how a coupon is applied. Adds 2 Renew Body Wash (3620) to the test cart, looks at the cart / Special Offers pages for coupons,
presses the coupon button, records the cart numbers, then empties the cart. Never goes to payment."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright
OUT = os.path.join(FEED, "probe7")

def save(n, t):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, n), "w", encoding="utf-8").write(t if isinstance(t, str) else json.dumps(t, indent=1))

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        added = []
        try:
            for sku, q in (("3620", 2), ("42996", 3)):
                ok, line = s.add(sku, q)
                print("add", sku, ok, line)
                if ok and line:
                    added.append(line)
            print("cart:", s.summary())
            for tag, path in (("cart", "/cart?sc_lang=en-US"), ("promo", "/checkout/promo-page")):
                b = len(s.json_log)
                s.page.goto(ms.BASE + path, wait_until="domcontentloaded", timeout=60000)
                s.settle(8000)
                save(tag + "_text.txt", " ".join(s.page.inner_text("body").split())[:6000])
                save(tag + "_api.json", [{"url": u[:220], "m": m, "j": (json.dumps(j)[:3000])} for u, m, j in s.json_log[b:] if "/api/" in u and not any(x in u for x in ("profile/flags", "toast", "notification", "lsd"))])
                s.page.screenshot(path=os.path.join(OUT, tag + ".png"), full_page=True)
                for label in ("Your Coupons", "Coupons", "Extra Savings"):
                    try:
                        s.page.get_by_text(label, exact=True).first.click(timeout=3000)
                        s.page.wait_for_timeout(3000)
                    except Exception:
                        pass
                save(tag + "_coupons_text.txt", " ".join(s.page.inner_text("body").split())[:6000])
                save(tag + "_buttons.json", s.page.evaluate("() => Array.from(document.querySelectorAll('button, a')).filter(e=>e.getBoundingClientRect().width>0).map(e=>[e.tagName,(e.innerText||'').trim().slice(0,50),(e.className||'').toString().slice(0,60)]).filter(x=>/coupon|apply|clip|redeem|add/i.test(x[1]))"))
                s.page.screenshot(path=os.path.join(OUT, tag + "_2.png"), full_page=True)
            # press the first apply / clip button on the cart page
            s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            s.settle(7000)
            try:
                s.page.get_by_text("Your Coupons", exact=True).first.click(timeout=3000)
                s.page.wait_for_timeout(2500)
            except Exception:
                pass
            b = len(s.json_log)
            btn = s.page.locator("button:visible", has_text=re.compile(r"apply|clip|redeem|add coupon", re.I)).first
            if btn.count():
                print("pressing", btn.inner_text()[:40])
                btn.click(timeout=6000)
                s.page.wait_for_timeout(5000)
                save("applied_api.json", [{"url": u[:220], "m": m, "j": json.dumps(j)[:3000]} for u, m, j in s.json_log[b:] if "/api/" in u])
                save("applied_text.txt", " ".join(s.page.inner_text("body").split())[:5000])
                s.page.screenshot(path=os.path.join(OUT, "applied.png"), full_page=True)
                r = s.fetch(s.cart_url())
                save("applied_cart.json", r.get("json"))
                print("cart after:", s.summary())
        finally:
            try:
                r = s.fetch(s.cart_url())
                for it in ((r.get("json") or {}).get("Data") or {}).get("Items") or []:
                    s.remove_line(it["LineId"])
                print("emptied; cart now", s.summary())
            except Exception as e:
                print("CLEANUP PROBLEM", e)
            s.close()

if __name__ == "__main__":
    main()
