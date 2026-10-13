"""probe9 (LAB): how a coupon from 'Your Coupons' is added (button on the cart page), and what the cart line looks like. Empties the cart afterwards."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright
OUT = os.path.join(FEED, "probe9")

def save(n, t):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, n), "w", encoding="utf-8").write(t if isinstance(t, str) else json.dumps(t, indent=1))

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    posts = []
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        try:
            ok, line = s.add("3620", 1)
            print("added body wash", ok)
            s.page.on("request", lambda rq: posts.append({"m": rq.method, "u": rq.url[:160], "b": (rq.post_data or "")[:600]}) if rq.method in ("POST", "PUT", "DELETE") and "/api/" in rq.url and "ads" not in rq.url else None)
            s.page.goto(ms.BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            s.settle(7000)
            s.page.get_by_text("Your Coupons", exact=True).first.click(timeout=5000)
            s.page.wait_for_timeout(2500)
            # html of the coupon cards
            html = s.page.evaluate("() => Array.from(document.querySelectorAll('.m-shelfAccessory')).map(e => e.outerHTML.slice(0, 3000))")
            save("coupon_cards.json", html)
            cards = s.page.evaluate("""() => Array.from(document.querySelectorAll('button.-cartCoupon')).map(b => { let a = b; for (let k = 0; k < 6 && a.parentElement; k++) { a = a.parentElement; if (a.innerText.length > 40) break; } return a.innerText.replace(/\\s+/g,' ').slice(0, 200); })""")
            print("coupon cards:", cards)
            save("coupon_texts.json", cards)
            before = s.summary()
            btn = s.page.locator("button.-cartCoupon:visible").first
            if btn.count():
                btn.click(timeout=6000)
                s.page.wait_for_timeout(5000)
                print("cart before", before, "after", s.summary())
                r = s.fetch(s.cart_url())
                save("cart_after_coupon.json", r.get("json"))
                for it in ((r.get("json") or {}).get("Data") or {}).get("Items") or []:
                    print("  line", it.get("Sku"), it.get("LineType"), it.get("PromotionId"), it.get("Price"), it.get("Points"), it.get("Quantity"), (it.get("Title") or "")[:50])
            save("posts.json", posts)
        finally:
            try:
                r = s.fetch(s.cart_url())
                for it in ((r.get("json") or {}).get("Data") or {}).get("Items") or []:
                    s.remove_line(it["LineId"])
                print("emptied", s.summary())
            except Exception as e:
                print("CLEANUP PROBLEM", e)
            s.close()

if __name__ == "__main__":
    main()
