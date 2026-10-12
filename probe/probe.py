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
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1366, "height": 900}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    page = ctx.new_page()
    reqs = []
    page.on("response", lambda r: reqs.append((r.status, r.request.method, r.url[:160])) if "melaleuca" in r.url and r.request.resource_type in ("xhr", "fetch", "document") else None)

    def home():
        r = page.goto("https://www.melaleuca.com/", wait_until="domcontentloaded", timeout=60000)
        log(f"home status={r.status if r else None}")
        page.wait_for_timeout(4000); snap(page, "01_home"); inputs(page, "01_home")
    step("home", home)

    def login():
        for u in ("https://www.melaleuca.com/signin", "https://www.melaleuca.com/login"):
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=45000); page.wait_for_timeout(3000)
                if page.locator("input[type=password]").count(): break
            except Exception as e:
                log(f"goto {u}: {e}")
        if not page.locator("input[type=password]").count():
            for t in ("Sign In", "Log In", "Sign in", "Login"):
                l = page.get_by_text(t, exact=False).first
                if l.count():
                    l.click(); page.wait_for_timeout(4000); break
        snap(page, "02_signin_page"); inputs(page, "02_signin_page")
        if not USER or not PASS:
            raise RuntimeError("no credentials in env (secret not set?)")
        user_in = page.locator("input[type=email], input[name*=user i], input[id*=user i], input[name*=email i], input[type=text]").first
        user_in.fill(USER)
        # some sites show the password after the user name
        if not page.locator("input[type=password]:visible").count():
            page.keyboard.press("Enter"); page.wait_for_timeout(3000)
        page.locator("input[type=password]").first.fill(PASS)
        page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=45000); page.wait_for_timeout(6000)
        snap(page, "03_after_login"); inputs(page, "03_after_login")
        log("logged-in guess: " + str(not page.locator("input[type=password]:visible").count()))
    step("login", login)

    for name, url in (("04_outlet", "https://www.melaleuca.com/productstore/extra-savings/outlet-store"),
                      ("05_monthly", "https://www.melaleuca.com/productstore/extra-savings/monthly-specials"),
                      ("06_cart", "https://www.melaleuca.com/cart"),
                      ("07_search", "https://www.melaleuca.com/search?q=lip%20balm")):
        def go(name=name, url=url):
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            log(f"{name} status={r.status if r else None}")
            page.wait_for_timeout(6000); snap(page, name); inputs(page, name)
        step(name, go)

    (OUT / "network.txt").write_text("\n".join(f"{s} {m} {u}" for s, m, u in reqs[:400]))
    (OUT / "log.txt").write_text("\n".join(LOG))
    b.close()
