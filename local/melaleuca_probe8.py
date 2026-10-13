"""probe8 (LAB): where does the Special Offers dialog get its choices (scents) from? Opens the dialog of the MelaPower offer and keeps every api answer.
Adds throw-away points first (to open the page) and empties the cart at the end. The final add request is blocked."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright
OUT = os.path.join(FEED, "probe8")

def save(n, t):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, n), "w", encoding="utf-8").write(t if isinstance(t, str) else json.dumps(t, indent=1))

def main():
    n = 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "t", "n": n, "user": env["MELA_USER_7"], "pass": env["MELA_PASS_7"], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    state = {"block": False}
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        s.login()
        added = []
        try:
            for sku, q in (("39278", 6), ("8207", 6), ("33022", 4)):
                ok, line = s.add(sku, q)
                if ok and line:
                    added.append(line)
            print("cart", s.summary())

            def guard(route):
                rq = route.request
                if state["block"] and rq.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/cart" in rq.url:
                    print("BLOCKED", rq.post_data)
                    return route.fulfill(status=200, content_type="application/json", body='{"Success":false,"ErrorMessages":["blocked"],"Data":null}')
                return route.fallback()
            s.ctx.route("**/api/cart*", guard)
            s.page.goto(ms.BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
            s.settle(8000)
            b = len(s.json_log)
            idx = s.page.evaluate("""(t) => { const bs = Array.from(document.querySelectorAll('button')).filter(b => /^\\s*select\\s*$/i.test(b.innerText));
                for (let i = 0; i < bs.length; i++) { let a = bs[i]; for (let k = 0; k < 7 && a.parentElement; k++) { a = a.parentElement; if (a.innerText.includes(t) && a.innerText.length < 700) return i; } } return -1; }""", "MelaPower")
            print("button", idx)
            state["block"] = True
            s.page.evaluate("""(i) => { const bs = Array.from(document.querySelectorAll('button')).filter(b => /^\\s*select\\s*$/i.test(b.innerText)); bs[i].scrollIntoView(); bs[i].click(); }""", idx)
            s.page.wait_for_timeout(4000)
            save("after_select_api.json", [{"url": u[:260], "m": m, "j": json.dumps(j)[:6000]} for u, m, j in s.json_log[b:] if "/api/" in u and not any(x in u for x in ("profile/flags", "toast", "notification", "lsd", "cart/summary"))])
            # scripts / inline json of the page that mention the scent skus
            h = s.page.content()
            save("promo_page.html", h)
            hits = [m.start() for m in re.finditer(r"6901", h)]
            save("hits_6901.txt", "\n\n".join(h[max(0, i - 600):i + 400] for i in hits[:5]))
            state["block"] = False
        finally:
            state["block"] = False
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
