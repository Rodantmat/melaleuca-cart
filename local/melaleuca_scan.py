"""
melaleuca_scan.py - reads, for each account, the Special Offers, the monthly/outlet deals and the coupons shown by the Melaleuca store.

SAFE BY DESIGN
  * It never opens the order confirmation and never places an order.
  * It only adds a few throw-away products to reach the point level that unlocks the Special Offers page,
    reads the page, and takes out ONLY the lines it added (anything already in the cart stays).

USAGE   python melaleuca_scan.py [accounts.json] [output.json] [--only "Tab name"]
"""
import json, os, random, re, sys, time, pathlib, datetime, traceback
from urllib.parse import urlparse, unquote

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright is not installed. Run:  pip install playwright   and then   playwright install chromium")
    sys.exit(2)

BASE = "https://www.melaleuca.com"
TARGET_POINTS = 44                    # points to reach in the cart (offers unlock at 35, shipping rebate steps at 39 / 44)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def geo_params(region, level=0):
    """DataImpulse targeting for the proxy user name. level 0 = the city, 1 = wider (state / country), 2 = the country only."""
    r = (region or "").lower()
    if r == "vancouver":
        return ["cr.ca;city.vancouver", "cr.ca", "cr.us"][min(level, 2)], ("America/Vancouver" if level < 2 else None)
    if r == "toronto":
        return ["cr.ca;city.toronto", "cr.ca", "cr.us"][min(level, 2)], ("America/Toronto" if level < 2 else None)
    if r == "socal":
        return ["cr.us;city.losangeles,sandiego,longbeach,anaheim,irvine,santaana,riverside", "cr.us;city.losangeles,burbank,glendale,pasadena,torrance,pomona,fullerton,oceanside,escondido,sanbernardino,corona,ontario,fontana,ventura,oxnard,carlsbad,murrieta,temecula", "cr.us"][min(level, 2)], "America/Los_Angeles"
    return "cr.us", None


class BlockedError(RuntimeError):
    """IP blocked / human check / network trouble: trying again from another IP can help"""


class BadLogin(RuntimeError):
    """the account's user name or password is refused: another IP will not help"""


class Session:
    def __init__(self, p, acct, idx, cfg, oport=None):
        self.acct, self.idx, self.cfg = acct, idx, cfg
        self.port = None
        self.bytes = 0
        self.last = {}
        self.json_log = []                        # (url, parsed json) of the api calls, for the coupon discovery
        kw = {}
        px = (cfg.get("proxy") or "").strip()
        tz = None
        if px:
            u = urlparse(px)
            login = unquote(u.username or "").split("__")[0]
            geo, tz = geo_params(acct.get("region"), acct.get("geo_level", 0))
            login += "__" + geo + (";sessttl.%d" % int(cfg.get("session_minutes", 120)) if cfg.get("session_minutes", 120) else "")
            port = u.port or 823
            if cfg.get("sticky_base"):
                port = int(cfg["sticky_base"]) + int(idx)   # one port = one steady IP for this account
            if oport:
                port = int(oport)                           # a port chosen by the runner (the saved one, or a fresh one after a block)
            self.port = port
            kw["proxy"] = {"server": "http://%s:%s" % (u.hostname, port), "username": login, "password": unquote(u.password or "")}
            log("  proxy port", port, "| location:", geo)
        self.channel = None
        self.browser = None
        for ch in [acct.get("channel_override") or cfg.get("channel") or None, "chromium", None]:     # the real Chrome / new headless mode looks much more like a person than the bare headless shell
            try:
                a = dict(headless=cfg.get("headless", True), args=["--disable-blink-features=AutomationControlled"], **kw)
                if ch:
                    a["channel"] = ch
                self.browser = p.chromium.launch(**a)
                self.channel = ch
                break
            except Exception as e:
                log("  browser", ch or "default", "not available:", str(e).split("\n")[0][:80])
        if self.browser is None:
            raise RuntimeError("no browser could be started - run install_scan.bat")
        ctxkw = dict(viewport={"width": 1366, "height": 900}, locale="en-US")
        if tz:
            ctxkw["timezone_id"] = tz                        # the clock of the browser matches the city of the IP
        ctxkw["user_agent"] = UA                             # headless browsers announce themselves ("HeadlessChrome"): the security check catches that, so always give a normal name
        if self.channel:
            try:
                ctxkw["user_agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36" % self.browser.version.split(".")[0]
            except Exception:
                pass
        self.ctx = self.browser.new_context(**ctxkw)
        self.page = self.ctx.new_page()
        self.page.on("response", self._on_resp)
        self.login_route = bool(cfg.get("fast", True) and cfg.get("early_route"))
        if self.login_route:          # also during sign-in: no pictures / fonts / trackers through the proxy
            self.ctx.route("**/*", self._route_login)

    TRACKERS = ("google-analytics", "googletagmanager", "doubleclick", "googlesyndication", "facebook.", "fbcdn", "hotjar", "clarity.ms", "segment.",
                "tiktok", "snapchat", "linkedin", "pinterest", "criteo", "optimizely", "newrelic", "nr-data", "bing.com", "adsrvr", "taboola", "outbrain",
                "quantserve", "scorecardresearch", "fullstory", "mouseflow", "crazyegg", "hubspot", "marketo", "mpulse", "akamai-rum", "sentry.io", "datadoghq")

    def _route(self, route):
        """after sign-in: no pictures, fonts, videos or tracking scripts - they cost proxy traffic and are not needed to read offers"""
        rq = route.request
        if rq.resource_type in ("image", "media", "font") or any(t in rq.url.lower().split("/")[2] for t in self.TRACKERS if len(rq.url.split("/")) > 2):
            return route.abort()
        return route.continue_()

    def _route_login(self, route):
        """during sign-in only pictures and videos are dropped (the security check needs the scripts, fonts and trackers to look normal)"""
        if route.request.resource_type in ("image", "media"):
            return route.abort()
        return route.continue_()

    def _on_resp(self, r):
        try:
            try:
                self.bytes += int(r.headers.get("content-length") or 0)
            except Exception:
                pass
            u = r.url
            if "/api/cart/summary" in u and r.request.method == "GET":
                self.last["summary"] = u
            elif "/api/cart?" in u and r.request.method == "GET":
                self.last["cart"] = u
            elif "/api/bogo" in u:
                self.last["bogo"] = u
            if "json" in r.headers.get("content-type", "") and "melaleuca.com/api/" in u and len(self.json_log) < 400:
                body = r.body()
                if 0 < len(body) < 600000:
                    self.json_log.append((u, r.request.method, json.loads(body.decode("utf-8", "replace"))))
        except Exception:
            pass

    def close(self):
        try:
            self.browser.close()
        except Exception:
            pass

    # ---- helpers
    def settle(self, ms=6000):
        try:
            self.page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        self.page.wait_for_timeout(ms)

    def fetch(self, url, method="GET", body=None):
        # a dropped connection ("Failed to fetch") on a read / delete is simply asked again (a POST is never repeated: it could have been done twice)
        tries = 4 if method in ("GET", "DELETE") else 1
        for k in range(tries):
            try:
                return self._fetch1(url, method, body)
            except Exception as e:
                if k == tries - 1 or "fetch" not in str(e).lower():
                    raise
                self.page.wait_for_timeout(2500 * (k + 1))

    def _fetch1(self, url, method="GET", body=None):
        # the Canadian store lives on ca.melaleuca.com: a call to www.melaleuca.com from there is blocked ("Failed to fetch"), so a full address of
        # the main site is turned into a path = always the site the page is on
        url = re.sub(r"^https?://www\.melaleuca\.com", "", url or "")
        return self.page.evaluate("""async ([u, m, b]) => {
            const o = {method: m, credentials: 'include'};
            if (b) { o.headers = {'Content-Type': 'application/json'}; o.body = JSON.stringify(b); }
            const r = await fetch(u, o); const t = await r.text();
            try { return {status: r.status, json: JSON.parse(t)}; } catch (e) { return {status: r.status, text: t.slice(0, 300)}; }
        }""", [url, method, body])

    def login(self):
        pg = self.page
        pg.goto(BASE + "/cart", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000 + random.randint(0, 2500))
        u = pg.locator("input[name=username]:visible").first
        try:
            u.wait_for(state="visible", timeout=25000)
        except Exception:
            self.snap(pg, "noform")
            raise BlockedError("the sign-in form did not appear (page: %s)" % pg.url[:90])
        u.click(timeout=15000)
        u.press_sequentially(self.acct["user"], delay=random.randint(45, 95))
        pg.wait_for_timeout(500 + random.randint(0, 600))
        w = pg.locator("input[name=password]:visible").first
        w.click(timeout=20000)
        w.press_sequentially(self.acct["pass"], delay=random.randint(45, 95))
        pg.wait_for_timeout(600 + random.randint(0, 800))
        pg.locator("button:visible", has_text=re.compile(r"^\s*sign in\s*$", re.I)).last.click()
        # wait until the sign-in page is left (slow proxies need more than a few seconds), or the page shows a message
        for _ in range(45):
            pg.wait_for_timeout(1000)
            if "signin" not in pg.url.lower():
                break
            try:
                if pg.locator("[role=alert]:visible, .error:visible, [class*=rror]:visible").count():
                    break
            except Exception:
                pass
        pg.wait_for_timeout(3000)
        if "signin" in pg.url.lower():
            self.diagnose(pg)
        pg.goto(BASE + "/account?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        self.settle(6000)
        if "signin" in pg.url.lower():
            self.diagnose(pg)
        if self.cfg.get("fast", True):                 # after sign-in, images / fonts / videos are not needed to read offers: pages load faster
            self.ctx.route("**/*", self._route)

    def snap(self, pg, why):
        """save a screenshot + the visible text of the page, for me to read when something does not work"""
        try:
            d = self.cfg.get("debug_dir")
            if not d:
                return
            os.makedirs(d, exist_ok=True)
            tag = re.sub(r"[^A-Za-z0-9]+", "_", str(self.acct.get("tab")))
            pg.screenshot(path=os.path.join(d, "%s_%s_%s.png" % (why, tag, self.port)))
            try:
                txt = " ".join(pg.inner_text("body", timeout=5000).split())
            except Exception:
                txt = ""
            open(os.path.join(d, "%s_%s_%s.txt" % (why, tag, self.port)), "w", encoding="utf-8").write(pg.url + "\n" + txt[:3000])
            log("  saved debug/%s_%s_%s.png | page: %s | %s" % (why, tag, self.port, pg.url[:80], txt[:160]))
        except Exception:
            pass

    def diagnose(self, pg):
        """sign-in did not work: save what the page shows and say why (wrong password -> do not retry; a human check / block -> new IP)"""
        try:
            txt = " ".join(pg.inner_text("body", timeout=8000).split())
        except Exception:
            txt = ""
        try:
            d = self.cfg.get("debug_dir")
            if d:
                os.makedirs(d, exist_ok=True)
                tag = re.sub(r"[^A-Za-z0-9]+", "_", str(self.acct.get("tab")))
                pg.screenshot(path=os.path.join(d, "signin_%s_%s.png" % (tag, self.port)))
                open(os.path.join(d, "signin_%s_%s.txt" % (tag, self.port)), "w", encoding="utf-8").write(pg.url + "\n" + txt[:3000])
        except Exception:
            pass
        try:
            alerts = " | ".join(t.strip() for t in pg.locator("[role=alert], .error, [class*=rror]").all_inner_texts() if t.strip())[:300]
        except Exception:
            alerts = ""
        try:
            main = " ".join(pg.inner_text("main", timeout=3000).split())[:300]
        except Exception:
            main = txt[-300:]
        log("  sign-in page says:", alerts or main, "| url:", pg.url[:80])
        low = (alerts + " " + main).lower() if (alerts or main) else txt.lower()
        frames = " ".join(f.url for f in pg.frames).lower()
        if re.search(r"captcha|recaptcha|hcaptcha|turnstile|challenge", frames) or re.search(r"verify you are human|not a robot|captcha|unusual activity|access denied|blocked|just a moment|try again later", low):
            raise BlockedError("the site asked for a human check / blocked this IP")
        if re.search(r"incorrect|invalid|doesn.t match|not recognized|wrong|did not match|locked", low):
            raise BadLogin("the site rejected the user name or password: " + txt[:160])
        raise BlockedError("sign-in did not complete (no error shown): " + txt[:120])

    def summary(self):
        u = self.last.get("summary")
        if not u:
            return None
        r = self.fetch(u)
        sm = r["json"]["Data"]["Summary"]
        return int(sm.get("ItemCount") or 0), float(sm.get("Points") or 0)

    def cart_url(self):
        if "cart" in self.last:
            return self.last["cart"]
        # the cart address is the same for every sign-in: ask for it directly (works even when the cart page is slow or never announces it)
        site = "productstoreCa" if str(self.acct.get("region") or "").lower() in ("vancouver", "toronto") else "productstoreUs"
        direct = BASE + "/api/cart?sc_itemid=%7BFE1DED98-281E-46FA-9656-7D6A0C2E436D%7D&sc_lang=en-US&sc_site=" + site
        try:
            r = self.fetch(direct)
            if r.get("status") == 200 and (r.get("json") or {}).get("Data") is not None:
                self.last["cart"] = direct
                return direct
        except Exception:
            pass
        for attempt in range(3):
            if "cart" in self.last:
                return self.last["cart"]
            self.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
            for _ in range(20):                                   # the page asks for its cart a few seconds after it loads
                if "cart" in self.last:
                    return self.last["cart"]
                self.page.wait_for_timeout(1000)
        self.snap(self.page, "nocart")
        raise RuntimeError("the cart page did not load its cart (page: %s)" % self.page.url[:90])

    def add(self, sku, qty, promo=0, line_type=None):
        r = self.fetch(self.cart_url(), "POST", {"Sku": str(sku), "Quantity": qty, "Configurations": [], "PromotionId": promo,
                                                  "LineType": line_type, "LineId": None, "Position": None})
        ok = r.get("status") == 200 and r.get("json", {}).get("Success")
        line = None
        if ok:
            try:
                line = r["json"]["Data"]["Item"]["Details"]["LineId"]
            except Exception:
                pass
        return ok, line

    def remove_line(self, line):
        return self.fetch(self.cart_url(), "DELETE", {"LineId": str(line)})


def money(v):
    try:
        return float(v)
    except Exception:
        return None


def compact_card(d):
    pr = d.get("PriceRange") or {}
    return {"sku": d.get("Sku"), "promo_id": d.get("PromotionId"), "title": d.get("Title"),
            "price": pr.get("RawMinPreferredPrice"), "regular": pr.get("RawMinRegularPrice"),
            "points": pr.get("RawMinPoints"), "max_qty": d.get("MaxQuantity"), "qty_available": d.get("QtyAvailable"),
            "points_required": d.get("ProductPointsRequired"), "stamp": d.get("Stamp"), "description": (d.get("Description") or "")[:200]}


def read_store_page(s, name, url):
    """outlet / monthly specials: the page loads /api/category/search/<id>; returns the product cards"""
    before = len(s.json_log)
    s.page.goto(BASE + url, wait_until="domcontentloaded", timeout=60000)
    s.settle(9000)
    out = []
    for u, m, j in s.json_log[before:]:
        if "/api/category/search/" in u and isinstance(j, dict):
            for c in j.get("Cards", []):
                d = (c.get("InnerData") or {}).get("Data") or {}
                pr = d.get("PriceRange") or {}
                prods = d.get("Products") or []
                out.append({"title": d.get("Title"), "family": d.get("FamilyID"), "skus": [p.get("Sku") for p in prods] or [d.get("Sku")],
                            "sold_out": [bool(p.get("IsSoldout")) for p in prods],
                            "price": pr.get("RawMinPreferredPrice"), "price_max": pr.get("RawMaxPreferredPrice"),
                            "regular": pr.get("RawMinRegularPrice"), "points": pr.get("RawMinPoints"),
                            "is_pack": bool(c.get("IsSavingPack")), "size": d.get("Size")})
            break
    return out


def pick_fill_products(s):
    """throw-away products with points that can be added by number: from the monthly-specials / outlet cards"""
    fill = []
    for url in ("/productstore/extra-savings/monthly-specials?sc_lang=en-US", "/productstore/extra-savings/outlet-store?sc_lang=en-US"):
        for c in read_store_page(s, "fill", url):
            if c["skus"] and len(c["skus"]) == 1 and c["skus"][0] and not any(c["sold_out"]) and (c["points"] or 0) >= 2:
                fill.append((c["skus"][0], float(c["points"]), c["title"]))
        if fill:
            break
    fill.sort(key=lambda x: -x[1])
    return fill


def scan_account(p, acct, idx, cfg, port=None):
    res = {"tab": acct.get("tab"), "scanned": datetime.datetime.now().isoformat(timespec="seconds"), "ok": False}
    s = Session(p, acct, idx, cfg, port)
    res["port"] = s.port
    added = []
    try:
        s.login()
        try:
            res["ip"] = s.ctx.request.get("https://api.ipify.org", timeout=20000).text().strip()
            log("  IP:", res["ip"])
        except Exception:
            pass
        start = s.summary()
        res["cart_at_start"] = start
        log("  signed in; cart at start:", start)
        res["loyalty_balance"] = None
        try:
            r = s.fetch(s.last.get("cart") or s.cart_url())
            res["loyalty_balance"] = r["json"]["Data"]["Summary"]["LoyaltyShoppingDollars"]["Balance"]
            res["monthly_commitment_points"] = r["json"]["Data"].get("MonthlyPointCommitment")
        except Exception:
            pass
        res["monthly_specials"] = read_store_page(s, "monthly", "/productstore/extra-savings/monthly-specials?sc_lang=en-US")
        res["outlet"] = read_store_page(s, "outlet", "/productstore/extra-savings/outlet-store?sc_lang=en-US")
        log("  monthly specials: %d cards, outlet: %d cards" % (len(res["monthly_specials"]), len(res["outlet"])))
        # ---- coupons: the cart screen has a collapsed "Your Coupons" section; open it and keep every api answer
        before = len(s.json_log)
        s.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
        s.settle(8000)
        for label in ("Your Coupons", "Extra Savings"):
            try:
                s.page.get_by_text(label, exact=True).first.click(timeout=5000)
                s.page.wait_for_timeout(4000)
            except Exception:
                pass
        res["coupon_api_calls"] = [{"url": u[:140], "keys": list(j.keys())[:6] if isinstance(j, dict) else None}
                                   for u, m, j in s.json_log[before:] if "coupon" in u.lower() or "bogo" in u.lower() or "promo" in u.lower()]
        try:
            res["coupons_text"] = s.page.inner_text("body")[:6000].split("Your Coupons", 1)[-1][:2500]
        except Exception:
            res["coupons_text"] = ""
        # the coupons this account really has (None = could not be read; [] = the account has none)
        res["coupons"] = None
        try:
            pg = s.page
            if "shopping cart" in pg.inner_text("body", timeout=8000).lower():
                tg = pg.locator("button.o-accordion__toggler", has_text="Your Coupons").first
                if tg.count() and tg.get_attribute("aria-expanded") != "true":
                    tg.click(timeout=8000)
                    pg.wait_for_timeout(2500)
                cards = pg.locator("article.-cartCoupons")
                lst = []
                for i in range(cards.count()):
                    try:
                        lst.append(cards.nth(i).locator(".m-recentProduct__description").first.inner_text().strip())
                    except Exception:
                        pass
                res["coupons"] = lst
                log("  coupons of this account: %d | %s" % (len(lst), " ; ".join(x[:60] for x in lst)))
        except Exception as e:
            log("  coupons could not be read:", str(e)[:100])
        # ---- fill the cart with throw-away products up to the target points
        fill = pick_fill_products(s)
        log("  fill candidates:", fill[:4])
        cur = s.summary() or (0, 0)
        for sku, pts, title in fill:
            if cur[1] >= TARGET_POINTS:
                break
            qty = max(1, min(6, int((TARGET_POINTS - cur[1]) // pts) + (1 if (TARGET_POINTS - cur[1]) % pts else 0)))
            ok, line = s.add(sku, qty)
            if ok and line:
                added.append(line)
            cur = s.summary() or cur
            log("   add", sku, "x", qty, "->", cur)
        res["points_in_cart"] = cur[1]
        # ---- Special Offers page
        s.page.goto(BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
        s.settle(9000)
        if "promo-page" not in s.page.url:
            res["note"] = "special offers page did not open (cart points %s) -> %s" % (cur[1], s.page.url[:60])
        offers = []
        if s.last.get("bogo"):
            r = s.fetch(s.last["bogo"])
            for c in (r.get("json") or {}).get("Data", {}).get("Cards", []):
                d = (c.get("InnerData") or {}).get("Data") or {}
                o = compact_card(d)
                o["coupon_price_field"] = c.get("CouponPrice")
                o["can_redeem"] = d.get("CanRedeem")
                offers.append(o)
        res["special_offers"] = offers
        log("  special offers:", len(offers))
        res["ok"] = bool(offers)
    except Exception as e:
        res["error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
        res["error_kind"] = "badlogin" if isinstance(e, BadLogin) else "retry"
        log("  ERROR", res["error"])
    finally:
        # take out only what this scan added
        try:
            for line in added:
                s.remove_line(line)
            res["cart_at_end"] = s.summary()
            log("  cart at end:", res["cart_at_end"])
        except Exception as e:
            res["cleanup_error"] = str(e)[:200]
            log("  CLEANUP PROBLEM:", e)
        res["mb"] = round(s.bytes / 1048576.0, 1)
        log("  traffic through the proxy: about %.1f MB (counted from the page headers, real use is a bit higher)" % res["mb"])
        s.close()
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
        args = [a for a in args if a != only]
    cfg_path = args[0] if args else "accounts.json"
    out_path = args[1] if len(args) > 1 else "melaleuca_offers.json"
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    results = []
    with sync_playwright() as p:
        for i, acct in enumerate(cfg["accounts"], 1):
            if only and acct.get("tab") != only:
                continue
            log("[%d/%d] %s" % (i, len(cfg["accounts"]), acct.get("tab")))
            try:
                results.append(scan_account(p, acct, i, cfg))
            except Exception:
                results.append({"tab": acct.get("tab"), "ok": False, "error": traceback.format_exc()[-400:]})
            pathlib.Path(out_path).write_text(json.dumps({"generated": datetime.datetime.now().isoformat(timespec="seconds"), "accounts": results}, indent=1), encoding="utf-8")
    log("done ->", out_path, "| ok:", sum(1 for r in results if r.get("ok")), "of", len(results))


if __name__ == "__main__":
    main()
