"""
melaleuca_probe_packs.py - READ-ONLY look at how the Melaleuca store builds mix-and-match packs and special offers with choices.

  python melaleuca_probe_packs.py 7        (7 = the number of the account in credentials.env, same as  melaleuca_run.py --only 7)

What it does
  * signs in with the account's usual steady IP (feed\\ip_7.json) and opens a few pack pages (toothpaste 3-pack, deodorant 3-pack, cleaner pack, ...)
  * saves the page text, a screenshot and every data answer the store gives, then presses "Add to cart" / "Choose" and writes down what the
    store sends - but that final request is BLOCKED, so the pack is NEVER added
  * adds the same throw-away products as the offers scan (44 points) only to open the Special Offers page, looks at the offer that needs a choice,
    blocks the final request again, and takes the throw-away products out again
  * never opens the checkout and never places an order
Result: folder  feed\\probe_packs\\  and the file  feed\\probe_packs.zip  - send me the zip.
"""
import os, sys, json, re, time, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

OUT = os.path.join(FEED, "probe_packs")
TARGETS = [("43987", "toothpaste 3-pack (mix)"), ("190", "deodorant 3-pack (mix)"), ("34911", "cleaner 3/4/5 pack"),
           ("39172", "diamond brite + rinse aid (one of each)"), ("34906", "laundry value 3-pack (A1,B1,C1)"), ("8911", "2-pack of one product"),
           ("5026", "lemon brite 3-pack"), ("33968", "wipes 5-pack")]


def save(name, text):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(text)


def describe_dom(pg, tag):
    """what a person would see and could press: dialogs, buttons, inputs, selects, radio / checkbox"""
    js = """() => {
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const d = el => ({tag: el.tagName, text: (el.innerText || el.value || '').trim().slice(0, 80), type: el.type || '', name: el.name || '', id: el.id || '',
                        cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 80), aria: el.getAttribute('aria-label') || '',
                        role: el.getAttribute('role') || '', dis: !!el.disabled});
      const q = s => Array.from(document.querySelectorAll(s)).filter(vis).slice(0, 60).map(d);
      const dlg = Array.from(document.querySelectorAll('[role=dialog]')).filter(vis).map(x => x.innerText.trim().slice(0, 1500));
      return {url: location.href, dialogs: dlg, buttons: q('button, [role=button], a.button'), inputs: q('input'), selects: q('select, [role=combobox], [role=listbox]')};
    }"""
    try:
        save("%s_dom.json" % tag, json.dumps(pg.evaluate(js), indent=1))
    except Exception as e:
        save("%s_dom.json" % tag, "error %s" % e)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    tabs = {}
    for ln in open(os.path.join(FEED, "mel_tabs.txt"), encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 3 and p[0].strip().isdigit():
            tabs[int(p[0])] = (p[1], p[2].strip(), p[3].strip().lower() if len(p) > 3 else "")
    name, kind, colour = tabs[n]
    region = {"orange": "vancouver", "yellow": "toronto"}.get(colour, "socal" if kind == "2" else "vancouver")
    acct = {"tab": name, "n": n, "user": env["MELA_USER_%d" % n], "pass": env["MELA_PASS_%d" % n], "region": region}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": int(env.get("STICKY_BASE") or 10000), "headless": True,
           "channel": env.get("BROWSER", "") or "", "session_minutes": int(env.get("SESSION_MINUTES", "120") or 0),
           "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    port = None
    try:
        port = json.load(open(os.path.join(FEED, "ip_%d.json" % n))).get("port")
    except Exception:
        pass
    os.makedirs(OUT, exist_ok=True)
    blocked = []                         # requests the store would have received - blocked on purpose
    state = {"block": False}
    added = []
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, port)
        try:
            s.login()
            print("signed in as", name)

            def guard(route):
                rq = route.request
                if state["block"] and rq.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/cart" in rq.url:
                    blocked.append({"method": rq.method, "url": rq.url, "body": rq.post_data})
                    print("   BLOCKED (not sent):", rq.method, (rq.post_data or "")[:300])
                    return route.fulfill(status=200, content_type="application/json", body='{"Success":false,"ErrorMessages":["blocked by probe"],"Data":null}')
                return route.fallback()
            s.ctx.route("**/api/cart*", guard)
            # ---- pack pages
            for sku, what in TARGETS:
                tag = "pack_%s" % sku
                print("page", sku, what)
                before = len(s.json_log)
                try:
                    s.page.goto("%s/products/%s?sc_lang=en-US" % (ms.BASE, sku), wait_until="domcontentloaded", timeout=60000)
                    s.settle(7000)
                    save(tag + "_text.txt", s.page.url + "\n" + " ".join(s.page.inner_text("body", timeout=8000).split())[:6000])
                    s.page.screenshot(path=os.path.join(OUT, tag + "_1.png"), full_page=True)
                    save(tag + "_api.json", json.dumps([{"url": u[:200], "method": m, "json": j} for u, m, j in s.json_log[before:] if "/api/" in u], indent=1)[:900000])
                    describe_dom(s.page, tag + "_1")
                    state["block"] = True
                    btn = s.page.locator("button:visible", has_text=re.compile(r"add to cart|choose|customi[sz]e|select|build", re.I)).first
                    if btn.count():
                        print("   pressing:", btn.inner_text()[:40].strip())
                        btn.click(timeout=8000)
                        s.page.wait_for_timeout(4000)
                        s.page.screenshot(path=os.path.join(OUT, tag + "_2.png"), full_page=True)
                        describe_dom(s.page, tag + "_2")
                        # second step: first choice in each slot, then the confirming button
                        for sel in ("[role=dialog] input[type=radio]", "[role=dialog] input[type=checkbox]", "[role=dialog] select"):
                            try:
                                els = s.page.locator(sel + ":visible")
                                for i in range(min(els.count(), 6)):
                                    try:
                                        if sel.endswith("select"):
                                            els.nth(i).select_option(index=1)
                                        else:
                                            els.nth(i).check(timeout=2000)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        s.page.wait_for_timeout(1500)
                        s.page.screenshot(path=os.path.join(OUT, tag + "_3.png"), full_page=True)
                        describe_dom(s.page, tag + "_3")
                        ok = s.page.locator("[role=dialog] button:visible", has_text=re.compile(r"add to cart|add|done|confirm|continue", re.I)).last
                        if ok.count():
                            print("   pressing in dialog:", ok.inner_text()[:40].strip())
                            ok.click(timeout=8000)
                            s.page.wait_for_timeout(3500)
                            s.page.screenshot(path=os.path.join(OUT, tag + "_4.png"), full_page=True)
                            save(tag + "_after_text.txt", " ".join(s.page.inner_text("body", timeout=8000).split())[:3000])
                    state["block"] = False
                except Exception as e:
                    state["block"] = False
                    print("   trouble:", str(e)[:150])
                    save(tag + "_error.txt", str(e))
            # ---- special offers with a choice
            try:
                print("special offers page (adds throw-away products, removes them afterwards)")
                fill = ms.pick_fill_products(s)
                cur = s.summary() or (0, 0)
                for sku, pts, title in fill:
                    if cur[1] >= ms.TARGET_POINTS:
                        break
                    qty = max(1, min(6, int((ms.TARGET_POINTS - cur[1]) // pts) + (1 if (ms.TARGET_POINTS - cur[1]) % pts else 0)))
                    ok, line = s.add(sku, qty)
                    if ok and line:
                        added.append(line)
                    cur = s.summary() or cur
                print("   cart now", cur)
                before = len(s.json_log)
                s.page.goto(ms.BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
                s.settle(9000)
                s.page.screenshot(path=os.path.join(OUT, "offers_1.png"), full_page=True)
                save("offers_api.json", json.dumps([{"url": u[:200], "method": m, "json": j} for u, m, j in s.json_log[before:] if "/api/" in u], indent=1)[:900000])
                describe_dom(s.page, "offers_1")
                state["block"] = True
                cards = s.page.locator("button:visible", has_text=re.compile(r"^\s*select\s*$", re.I))
                print("   SELECT buttons:", cards.count())
                for i in range(min(cards.count(), 30)):
                    cards.nth(i).click(timeout=8000)
                    s.page.wait_for_timeout(2500)
                    txt = " ".join((s.page.locator("[role=dialog]:visible").first.inner_text() if s.page.locator("[role=dialog]:visible").count() else "").split())
                    if re.search(r"your choices|choose", txt, re.I):
                        print("   offer needing a choice found (button %d): %s" % (i, txt[:100]))
                        s.page.screenshot(path=os.path.join(OUT, "offers_choice_1.png"), full_page=True)
                        describe_dom(s.page, "offers_choice_1")
                        for sel in ("[role=dialog] input[type=radio]", "[role=dialog] select", "[role=dialog] input[type=checkbox]"):
                            els = s.page.locator(sel + ":visible")
                            for k in range(min(els.count(), 8)):
                                try:
                                    if sel.endswith("select"):
                                        els.nth(k).select_option(index=1)
                                    else:
                                        els.nth(k).check(timeout=2000)
                                except Exception:
                                    pass
                        s.page.wait_for_timeout(1500)
                        s.page.screenshot(path=os.path.join(OUT, "offers_choice_2.png"), full_page=True)
                        describe_dom(s.page, "offers_choice_2")
                        ok = s.page.locator("[role=dialog] button:visible", has_text=re.compile(r"add to cart|add|done|confirm|continue|select", re.I)).last
                        if ok.count():
                            ok.click(timeout=8000)
                            s.page.wait_for_timeout(3000)
                            s.page.screenshot(path=os.path.join(OUT, "offers_choice_3.png"), full_page=True)
                        break
                    try:
                        s.page.locator("[role=dialog] button:visible", has_text=re.compile(r"close|cancel", re.I)).first.click(timeout=3000)
                    except Exception:
                        s.page.keyboard.press("Escape")
                    s.page.wait_for_timeout(800)
                state["block"] = False
            except Exception as e:
                state["block"] = False
                print("   offers part trouble:", str(e)[:200])
                save("offers_error.txt", str(e))
        finally:
            state["block"] = False
            try:
                for line in added:
                    s.remove_line(line)
                print("throw-away products removed; cart now", s.summary())
            except Exception as e:
                print("CLEANUP PROBLEM - please empty the cart of this account by hand:", e)
            save("blocked_requests.json", json.dumps(blocked, indent=1))
            s.close()
    zp = os.path.join(FEED, "probe_packs.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(OUT):
            z.write(os.path.join(OUT, f), f)
    print("\nDone. Send me:", zp)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    main()
