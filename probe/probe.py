"""Melaleuca PROBE. Read-only: signs in, looks at pages, saves screenshots + text. Never adds to cart, never checks out."""
import os, sys, re, json, time, pathlib
from playwright.sync_api import sync_playwright

IDX = os.environ.get("ACCOUNT_INDEX", "1")
USER = os.environ.get("MELA_USER", "")
PASS = os.environ.get("MELA_PASS", "")
OUT = pathlib.Path("probe-output"); OUT.mkdir(exist_ok=True)
LOG = []

def log(m):
    print(m, flush=True); LOG.append(str(m))

def snap(page, name):
    try:
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception as e:
        log(f"[{name}] screenshot failed: {e}")
    try:
        txt = page.inner_text("body")
        txt = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", txt)
        (OUT / f"{name}.txt").write_text(txt[:60000], encoding="utf-8")
    except Exception as e:
        log(f"[{name}] text failed: {e}")
    log(f"[{name}] url={page.url} title={page.title()!r}")

def inputs(page, name):
    try:
        info = page.evaluate("""() => [...document.querySelectorAll('input,button,a[href*=cart],a[href*=sign],a[href*=login]')].slice(0,80).map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',id:e.id||'',ph:e.placeholder||'',text:(e.innerText||e.value||'').trim().slice(0,40),href:e.href||''}))""")
        (OUT / f"{name}.elements.json").write_text(json.dumps(info, indent=1))
    except Exception as e:
        log(f"[{name}] elements failed: {e}")

def step(label, fn):
    try:
        fn(); log(f"OK   {label}")
    except Exception as e:
        log(f"FAIL {label}: {type(e).__name__}: {str(e)[:300]}")

with sync_playwright() as p:
    px = os.environ.get("PROXY_URL", "").strip()
    kw = {}
    if px:
        from urllib.parse import urlparse, unquote
        u = urlparse(px)
        login = unquote(u.username or "")
        if "__" not in login:
            login += "__cr.us"                      # US residential IPs only
        port = u.port or 823
        base = os.environ.get("PROXY_STICKY_PORT_BASE", "").strip() or "10000"
        if base:                                   # one fixed port = one fixed IP per account (sticky)
            port = int(base) + int(IDX)
        kw["proxy"] = {"server": f"http://{u.hostname}:{port}", "username": login, "password": unquote(u.password or "")}
        log(f"using proxy {u.hostname}:{port} (account {IDX})")
    b = p.chromium.launch(headless=True, **kw)
    ctx = b.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    page = ctx.new_page()
    def myip():
        try:
            r = ctx.request.get("https://api.ipify.org?format=json", timeout=30000)
            return r.json().get("ip")
        except Exception as e:
            return f"ip check failed: {type(e).__name__}"
    log("exit IP at start: " + str(myip()))
    reqs = []
    API = OUT / "api"; API.mkdir(exist_ok=True)
    cnt = {"n": 0}
    LAST = {}
    def on_resp(r):
        try:
            if "/api/cart/summary" in r.url and r.request.method == "GET": LAST["summary"] = r.url
            ct = r.headers.get("content-type", "")
            if "json" in ct and "melaleuca" in r.url and cnt["n"] < 150:
                body = r.body()
                if 0 < len(body) < 400000:
                    cnt["n"] += 1
                    (API / f"{cnt['n']:03d}.json").write_text(json.dumps({"url": r.url, "status": r.status, "method": r.request.method, "page": page.url[:120], "body": body.decode("utf-8", "replace")}))
        except Exception:
            pass
    page.on("response", on_resp)
    REQS = []
    def on_req(rq):
        try:
            if "melaleuca.com/api/" in rq.url and rq.method in ("POST", "PUT", "DELETE", "PATCH") and "cart/ads" not in rq.url:
                REQS.append({"method": rq.method, "url": rq.url[:200], "body": (rq.post_data or "")[:3000]})
        except Exception:
            pass
    page.on("request", on_req)
    page.on("response", lambda r: reqs.append((r.status, r.request.method, r.url[:160])) if "melaleuca" in r.url and r.request.resource_type in ("xhr", "fetch", "document") else None)

    def home():
        r = page.goto("https://www.melaleuca.com/", wait_until="domcontentloaded", timeout=60000)
        log(f"home status={r.status if r else None}")
        page.wait_for_timeout(4000); snap(page, "01_home"); inputs(page, "01_home")
    step("home", home)

    def login():
        page.goto("https://www.melaleuca.com/cart", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        snap(page, "02_signin_page")
        log("username inputs: %d, visible: %d" % (page.locator("input[name=username]").count(), page.locator("input[name=username]:visible").count()))
        if not USER or not PASS:
            raise RuntimeError("no credentials in env (secret not set?)")
        page.locator("input[name=username]:visible").first.fill(USER)
        page.locator("input[name=password]:visible").first.fill(PASS)
        page.wait_for_timeout(500)
        page.locator("button:visible", has_text=re.compile(r"^\s*sign in\s*$", re.I)).last.click()
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        snap(page, "03_after_login"); inputs(page, "03_after_login")
        log("still on sign-in form: " + str(page.locator("input[name=password]:visible").count() > 0))
    step("login", login)

    for name, url in (("04_outlet", "https://www.melaleuca.com/productstore/extra-savings/outlet-store?sc_lang=en-US"),
                      ("05_monthly", "https://www.melaleuca.com/productstore/extra-savings/monthly-specials?sc_lang=en-US"),
                      ("06_cart", "https://www.melaleuca.com/cart?sc_lang=en-US"),
                      ("07_search", "https://www.melaleuca.com/search?q=lip%20balm&sc_lang=en-US"),
                      ("08_account", "https://www.melaleuca.com/account?sc_lang=en-US")):
        def go(name=name, url=url):
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            log(f"{name} status={r.status if r else None}")
            try: page.wait_for_load_state("networkidle", timeout=40000)
            except Exception: pass
            page.wait_for_timeout(12000)
            page.mouse.wheel(0, 2500); page.wait_for_timeout(3000)
            snap(page, name); inputs(page, name)
        if os.environ.get("MODE") not in ("cart", "checkout"):
            step(name, go)

    if os.environ.get("MODE") == "cart":
        # ---- CART MECHANICS TEST: add ONE item, look at the cart, remove it. Never checks out. ----
        def cart_total():
            try:
                u = LAST["summary"]
                r = page.evaluate("async (u) => { const r = await fetch(u, {credentials:'include'}); return await r.json(); }", u)
                sm = r["Data"]["Summary"]; return sm.get("ItemCount"), sm.get("Points")
            except Exception as e:
                return f"summary failed {e}"
        def warm():
            page.goto("https://www.melaleuca.com/account?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            try: page.wait_for_load_state("networkidle", timeout=40000)
            except Exception: pass
            page.wait_for_timeout(8000)
            log("warm-up page: " + page.url[:60] + " title=" + page.title())
        step("warm up session", warm)
        def add_one():
            page.goto("https://www.melaleuca.com/productstore/extra-savings/outlet-store?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            try: page.wait_for_load_state("networkidle", timeout=40000)
            except Exception: pass
            page.wait_for_timeout(8000)
            log("cart before: " + str(cart_total()))
            btns = page.get_by_text(re.compile(r"^\s*(select|add to cart)\s*$", re.I)).locator("visible=true")
            log("add-to-cart buttons visible: %d" % btns.count())
            snap(page, "10_outlet_ready")
            try:
                html = page.content()
                i = html.find("Defining Gel")
                (OUT / "10_card.html").write_text(html[max(0, i - 3000): i + 3000], encoding="utf-8")
            except Exception as e:
                log("card html failed " + str(e))
            if btns.count() == 0:
                # open the first product card and look for the button there
                cards = page.locator("a[href*='/productstore/']:visible")
                log("product links: %d" % cards.count())
                raise RuntimeError("no add-to-cart button on the listing")
            btns.first.click()
            page.wait_for_timeout(6000)
            snap(page, "11_after_add"); inputs(page, "11_after_add")
            log("cart after add: " + str(cart_total()))
        step("cart add one", add_one)
        def view_cart():
            page.goto("https://www.melaleuca.com/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            try: page.wait_for_load_state("networkidle", timeout=40000)
            except Exception: pass
            page.wait_for_timeout(10000)
            snap(page, "12_cart_with_item"); inputs(page, "12_cart_with_item")
        step("view cart", view_cart)
        def remove_it():
            rm = page.locator("button:visible, a:visible, [role=button]:visible").filter(has_text=re.compile(r"remove|delete|^\s*clear", re.I))
            if rm.count() == 0:
                rm = page.locator("[aria-label*=remove i]:visible, [aria-label*=delete i]:visible, [title*=remove i]:visible")
            log("remove controls: %d" % rm.count())
            rm.first.click(); page.wait_for_timeout(5000)
            snap(page, "13_after_remove")
            log("cart after remove: " + str(cart_total()))
        step("remove item", remove_it)
    if os.environ.get("MODE") == "checkout":
        # ---- CHECKOUT TEST: fill the cart to 35+ points, look at cart + checkout screens (read only), empty the cart. NEVER places an order. ----
        FORBID = re.compile(r"place\s*order|confirm\s*order|submit\s*order|pay\s*now|complete\s*(my\s*)?order", re.I)
        def summ():
            try:
                u = LAST["summary"]
                r = page.evaluate("async (u) => { const r = await fetch(u, {credentials:'include'}); return await r.json(); }", u)
                sm = r["Data"]["Summary"]; return int(sm.get("ItemCount") or 0), float(sm.get("Points") or 0)
            except Exception as e:
                return None
        def settle(ms=7000):
            try: page.wait_for_load_state("networkidle", timeout=30000)
            except Exception: pass
            page.wait_for_timeout(ms)
        def warm():
            page.goto("https://www.melaleuca.com/account?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); settle(6000)
            log("warm-up: " + page.title())
        step("warm up", warm)
        def fill_cart():
            for src in ("https://www.melaleuca.com/productstore/extra-savings/monthly-specials?sc_lang=en-US",
                        "https://www.melaleuca.com/productstore/extra-savings/outlet-store?sc_lang=en-US"):
                page.goto(src, wait_until="domcontentloaded", timeout=60000); settle(8000)
                n = page.get_by_text(re.compile(r"^\s*select\s*$", re.I)).locator("visible=true").count()
                log(f"{src[-30:]}: {n} SELECT buttons; cart now {summ()}")
                for i in range(min(n, 14)):
                    st = summ()
                    if st and st[1] >= 40: break
                    try:
                        page.get_by_text(re.compile(r"^\s*select\s*$", re.I)).locator("visible=true").nth(i).click(timeout=8000)
                        page.wait_for_timeout(3500)
                        # options dialog? close it
                        if page.locator("[role=dialog]:visible").count():
                            snap(page, f"20_options_dialog_{i}")
                            page.keyboard.press("Escape"); page.wait_for_timeout(1000)
                    except Exception as e:
                        log(f"click {i} failed: {str(e)[:100]}")
                    log(f"after click {i}: {summ()}")
                st = summ()
                if st and st[1] >= 40: break
            log("cart filled: " + str(summ()))
        step("fill cart", fill_cart)
        (OUT / "requests.json").write_text(json.dumps(REQS, indent=1))
        def cart_screen():
            page.goto("https://www.melaleuca.com/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); settle(12000)
            page.mouse.wheel(0, 3000); page.wait_for_timeout(2000)
            snap(page, "30_cart_full"); inputs(page, "30_cart_full")
        step("cart screen", cart_screen)
        def go_checkout():
            b = page.locator("button:visible, a:visible").filter(has_text=re.compile(r"proceed to checkout|checkout", re.I))
            log("checkout controls: %d: %s" % (b.count(), [b.nth(i).inner_text()[:30] for i in range(min(b.count(), 5))]))
            t = b.first.inner_text()
            if FORBID.search(t): raise RuntimeError("refusing to click: " + t)
            b.first.click(); settle(12000)
            snap(page, "31_checkout_1"); inputs(page, "31_checkout_1")
            page.mouse.wheel(0, 3000); page.wait_for_timeout(2000); snap(page, "32_checkout_1_scrolled")
        step("go to checkout", go_checkout)
        def empty_cart():
            for k in range(25):
                page.goto("https://www.melaleuca.com/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000); settle(8000)
                st = summ()
                if st and st[0] == 0: break
                rm = page.locator("button:visible, a:visible, [role=button]:visible").filter(has_text=re.compile(r"remove|delete", re.I))
                if rm.count() == 0:
                    rm = page.locator("[aria-label*=remove i]:visible, [aria-label*=delete i]:visible")
                if rm.count() == 0: log("no remove control found"); break
                rm.first.click(); page.wait_for_timeout(4000)
            log("cart at end: " + str(summ()))
        step("empty cart", empty_cart)
        (OUT / "requests.json").write_text(json.dumps(REQS, indent=1))
    log("exit IP at end: " + str(myip()))
    (OUT / "network.txt").write_text("\n".join(f"{s} {m} {u}" for s, m, u in reqs[:400]))
    (OUT / "log.txt").write_text("\n".join(LOG))
    b.close()
