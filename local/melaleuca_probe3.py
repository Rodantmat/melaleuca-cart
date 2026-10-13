"""
melaleuca_probe3.py - READ-ONLY, second look: how the choices of a pack / special offer are sent to the cart.
  python melaleuca_probe3.py 7
Same safety as the first probe: the final "add" request of every pack / offer is BLOCKED (never reaches the store), the throw-away products
used to open the Special Offers page are taken out again, no checkout, no order.  Result: feed\\probe3.zip
"""
import os, sys, json, re, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

OUT = os.path.join(FEED, "probe3")
PACKS = ["190", "34906", "33968"]
OFFERS = ["MelaPower Laundry"]


def save(name, text):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(text)


JS_OPEN_BOX = """(i) => {
  const t = document.querySelectorAll('.o-accordion__toggler')[i];
  if (!t) return null;
  let b = t; for (let k = 0; k < 4 && b.parentElement; k++) { b = b.parentElement; if (b.innerText && b.innerText.length > t.innerText.length + 3) break; }
  return {text: b.innerText.slice(0, 1500), html: b.outerHTML.slice(0, 7000)};
}"""


def pick_in_open_boxes(pg, tag, which):
    """one box after the other: if its options are not showing, press its title, then pick an option"""
    n = pg.locator(".o-accordion__toggler:visible").count()
    chosen = []
    opts = lambda: pg.locator(".o-configuratorAcc__list button.m-refinerImage:visible")
    for i in range(n):
        try:
            t = pg.locator(".o-accordion__toggler:visible").nth(i)
            t.scroll_into_view_if_needed(timeout=3000)
            pg.wait_for_timeout(500)
            tries = 0
            while opts().count() == 0 and tries < 2:
                t.click(timeout=4000)
                pg.wait_for_timeout(1500)
                tries += 1
            k = opts().count()
            pg.screenshot(path=os.path.join(OUT, "%s_slot%d_open.png" % (tag, i)))
            if k:
                idx = (which + i) % k
                txt = opts().nth(idx).inner_text()[:60]
                opts().nth(idx).click(timeout=4000)
                chosen.append((i, idx, k, txt))
            else:
                chosen.append((i, "no options visible"))
            pg.wait_for_timeout(1500)
        except Exception as e:
            chosen.append((i, "error", str(e)[:100]))
    return chosen


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
    blocked, state, added = [], {"block": False, "tag": ""}, []
    log = []
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, port)
        try:
            s.login()
            print("signed in as", name)

            def guard(route):
                rq = route.request
                if state["block"] and rq.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/cart" in rq.url and "/api/cart/ads" not in rq.url:
                    blocked.append({"for": state["tag"], "method": rq.method, "url": rq.url[:120], "body": rq.post_data})
                    print("   BLOCKED (not sent):", state["tag"], (rq.post_data or "")[:400])
                    return route.fulfill(status=200, content_type="application/json", body='{"Success":false,"ErrorMessages":["blocked by probe"],"Data":null}')
                return route.fallback()
            s.ctx.route("**/api/cart*", guard)
            # ---- packs
            for sku in PACKS:
                tag = "pack_%s" % sku
                try:
                    print("pack", sku)
                    s.page.goto("%s/products/%s?sc_lang=en-US" % (ms.BASE, sku), wait_until="domcontentloaded", timeout=60000)
                    s.settle(6000)
                    save(tag + "_page.html", s.page.content())
                    links = s.page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => [a.innerText.trim().slice(0,60), a.href]).filter(x => /pack|bundle|4|5/i.test(x[0]) && x[1].includes('/productstore')).slice(0,40)")
                    save(tag + "_links.json", json.dumps(links, indent=1))
                    chosen = pick_in_open_boxes(s.page, tag, 0)
                    save(tag + "_chosen.json", json.dumps(chosen))
                    s.page.screenshot(path=os.path.join(OUT, tag + "_chosen.png"), full_page=True)
                    state["block"], state["tag"] = True, tag
                    btn = s.page.locator("button", has_text=re.compile(r"^\s*add to cart\s*$", re.I)).first
                    btn.click(timeout=6000)
                    s.page.wait_for_timeout(3500)
                    s.page.screenshot(path=os.path.join(OUT, tag + "_afteradd.png"), full_page=False)
                    save(tag + "_afteradd.txt", " ".join(s.page.inner_text("body", timeout=8000).split())[:2500])
                    if sku == "34911":      # an accessory (spray bottle) of the cleaner pack
                        state["tag"] = tag + "_bottle"
                        acc = s.page.locator("xpath=//*[contains(normalize-space(.),'Mixing Spray Bottle')]/following::button[contains(.,'add')][1]").first
                        if acc.count():
                            acc.click(timeout=5000)
                            s.page.wait_for_timeout(3000)
                    state["block"] = False
                except Exception as e:
                    state["block"] = False
                    print("   trouble:", str(e)[:200])
                    save(tag + "_error.txt", str(e))
            # ---- special offers
            try:
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
                print("cart for the offers page:", cur)
                for t in OFFERS:
                    tag = "offer_" + re.sub(r"[^A-Za-z0-9]+", "_", t)
                    try:
                        print("offer", t)
                        s.page.goto(ms.BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
                        s.settle(7000)
                        idx = s.page.evaluate("""(t) => {
                            const bs = Array.from(document.querySelectorAll('button')).filter(b => /^\\s*select\\s*$/i.test(b.innerText));
                            for (let i = 0; i < bs.length; i++) { let a = bs[i]; for (let k = 0; k < 7 && a.parentElement; k++) { a = a.parentElement; if (a.innerText.includes(t) && a.innerText.length < 700) return i; } }
                            return -1; }""", t)
                        if idx < 0:
                            print("   card not found")
                            continue
                        state["block"], state["tag"] = True, tag
                        s.page.evaluate("""(i) => { const bs = Array.from(document.querySelectorAll('button')).filter(b => /^\\s*select\\s*$/i.test(b.innerText)); bs[i].scrollIntoView(); bs[i].click(); }""", idx)
                        s.page.wait_for_timeout(2500)
                        dl = s.page.evaluate("() => Array.from(document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal], [class*=dialog]')).filter(e => e.getBoundingClientRect().width > 0).map(e => ({text: e.innerText.slice(0,1500), html: e.outerHTML.slice(0,9000)}))")
                        save(tag + "_dialog.json", json.dumps(dl, indent=1))
                        s.page.screenshot(path=os.path.join(OUT, tag + "_1.png"), full_page=False)
                        chosen = pick_in_open_boxes(s.page, tag, 0)
                        for sel in ("[role=dialog] input[type=radio]", "[role=dialog] select"):
                            els = s.page.locator(sel + ":visible")
                            for k in range(min(els.count(), 6)):
                                try:
                                    if sel.endswith("select"):
                                        els.nth(k).select_option(index=1)
                                    else:
                                        els.nth(k).check(timeout=1500)
                                except Exception:
                                    pass
                        save(tag + "_chosen.json", json.dumps(chosen))
                        s.page.screenshot(path=os.path.join(OUT, tag + "_2.png"), full_page=False)
                        dl2 = s.page.evaluate("() => Array.from(document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal]')).filter(e => e.getBoundingClientRect().width > 0).map(e => e.innerText.slice(0,800))")
                        save(tag + "_dialog_after_choice.json", json.dumps(dl2, indent=1))
                        ok = s.page.locator("[role=dialog] button:visible, [class*=modal] button:visible", has_text=re.compile(r"add to cart|^\s*add\s*$|confirm|done|continue|select", re.I)).last
                        if ok.count():
                            ok.click(timeout=5000)
                            s.page.wait_for_timeout(2500)
                            s.page.screenshot(path=os.path.join(OUT, tag + "_3.png"), full_page=False)
                        state["block"] = False
                    except Exception as e:
                        state["block"] = False
                        print("   trouble:", str(e)[:200])
                        save(tag + "_error.txt", str(e))
            except Exception as e:
                print("offers part trouble:", str(e)[:200])
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
    zp = os.path.join(FEED, "probe3.zip")
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
