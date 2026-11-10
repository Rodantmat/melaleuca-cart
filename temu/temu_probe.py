"""Temu probe - can a cloud runner (no laptop, logged out) read Temu products + prices?
Real Chromium (headful under xvfb, same chain as reprice/bb_web.py). Nothing is bought, no account.

Data rules:
  - images, video, fonts and stylesheets are ALWAYS blocked (only the page HTML, scripts and data calls load)
  - the proxy is OFF by default (plain GitHub runner IP, costs nothing). TEMU_PROXY=1 turns it on, on its own port.
  - every page prints the bytes really carried on the wire, plus a run total.
Env: TEMU_QUERY (search word), TEMU_PROXY (0/1), PROXY_URL (secret, only read when TEMU_PROXY=1).
"""
import json, os, re, sys, time, urllib.parse

QUERY = os.environ.get("TEMU_QUERY", "dog shirt")
USE_PROXY = os.environ.get("TEMU_PROXY", "0") == "1"
PORT = int(os.environ.get("TEMU_PROXY_PORT", "10150"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
BLOCK = {"image", "media", "font", "stylesheet"}

EXTRACT_JS = r"""() => {
  const out=[]; const seen=new Set();
  for (const a of document.querySelectorAll('a[href*="goods_id="], a[href*="-g-"]')) {
    const m = a.href.match(/goods_id=(\d+)/) || a.href.match(/-g-(\d+)\.html/);
    if (!m || seen.has(m[1])) continue;
    let card=a; for (let k=0;k<6 && card.parentElement;k++){ if (/\$\s?\d/.test(card.innerText||'')) break; card=card.parentElement; }
    const txt=(card.innerText||'').replace(/\s+/g,' ').trim();
    const prices=[...txt.matchAll(/\$\s?([\d,]+(?:\.\d{1,2})?)/g)].map(x=>x[1]);
    const img=card.querySelector('img[alt]');
    let title=(img && img.alt || a.getAttribute('aria-label') || '').replace(/^item picture\s*/i,'').trim();
    if (!title || title.length < 8) title = txt.slice(0,120);
    const sold=(txt.match(/([\d.,]+K?\+?)\s*sold/i)||[])[1]||null;
    seen.add(m[1]);
    out.push({goods_id:m[1], title:title.slice(0,140), price:prices[0]||null, prices:prices.slice(0,3), sold, url:a.href.split('&_oak')[0]});
  }
  return out;
}"""

wire = {"bytes": 0, "n": 0, "blocked": 0}


def block_reason(url, title, body):
    u, t, b = (url or "").lower(), (title or "").lower(), (body or "").lower()
    if "login" in u or "sign in / register" in b: return "LOGIN_WALL"
    if "captcha" in u or "verify" in t or "slide to" in b or "security check" in b: return "CAPTCHA"
    return None


def visit(pg, label, url, scrolls=0, wait=6):
    b0, t0 = wire["bytes"], time.time()
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(json.dumps({"page": label, "error": str(e)[:200]}), flush=True); return []
    pg.wait_for_timeout(wait * 1000)
    for _ in range(scrolls):
        pg.mouse.wheel(0, 2500); pg.wait_for_timeout(2200)
    try:
        body = re.sub(r"\s+", " ", pg.evaluate("() => (document.body && document.body.innerText || '').slice(0,400)"))
    except Exception:
        body = ""
    blk = block_reason(pg.url, pg.title(), body)
    items = []
    if not blk:
        try: items = pg.evaluate(EXTRACT_JS) or []
        except Exception as e: body += " EXTRACT_ERR " + str(e)[:150]
    priced = [i for i in items if i.get("price")]
    print(json.dumps({"page": label, "secs": round(time.time() - t0, 1), "final_url": pg.url[:160], "title": pg.title()[:80],
                      "block": blk, "products": len(items), "with_price": len(priced),
                      "page_kb": round((wire["bytes"] - b0) / 1024), "body_head": body[:160]}), flush=True)
    for i in priced[:8]:
        print("   ", json.dumps(i)[:300], flush=True)
    return items


def main():
    from playwright.sync_api import sync_playwright
    kw = {"headless": False}
    if USE_PROXY:
        raw = os.environ.get("PROXY_URL", "").strip()
        if not raw:
            print("TEMU_PROXY=1 but no PROXY_URL secret - stopping"); return
        u = urllib.parse.urlparse(raw); login = urllib.parse.unquote(u.username or "")
        if "__" not in login: login += "__cr.us"
        kw["proxy"] = {"server": "http://%s:%s" % (u.hostname, PORT), "username": login, "password": urllib.parse.unquote(u.password or "")}
    print("=== TEMU PROBE  mode=%s  query=%r  blocked types=%s" % ("PROXY" if USE_PROXY else "runner-ip (no proxy)", QUERY, sorted(BLOCK)), flush=True)
    with sync_playwright() as p:
        b = p.chromium.launch(**kw)
        ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900})

        def gate(r):
            if r.request.resource_type in BLOCK:
                wire["blocked"] += 1; return r.abort()
            return r.continue_()
        ctx.route("**/*", gate)

        def done(rq):
            try:
                sz = rq.sizes()
                wire["bytes"] += sum((sz.get(k) or 0) for k in ("responseBodySize", "responseHeadersSize", "requestBodySize", "requestHeadersSize"))
                wire["n"] += 1
            except Exception:
                pass
        ctx.on("requestfinished", done)

        pg = ctx.new_page()
        home = visit(pg, "homepage", "https://www.temu.com/", scrolls=6, wait=8)
        chans = []
        try:
            chans = pg.evaluate(r"""() => [...new Set([...document.querySelectorAll('a[href]')].map(a=>a.href).filter(h=>/temu\.com\/(channel\/|[a-z0-9-]+-o3-\d+)/.test(h)))].slice(0,6)""") or []
        except Exception:
            pass
        print("channel/category links seen:", json.dumps(chans)[:600], flush=True)
        visit(pg, "search", "https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(QUERY), scrolls=2)
        if home:
            visit(pg, "product_full_link", home[0]["url"])
            visit(pg, "product_bare", "https://www.temu.com/goods.html?goods_id=" + home[0]["goods_id"])
        for c in chans[:3]:
            visit(pg, "channel", c, scrolls=2)
        visit(pg, "best_sellers", "https://www.temu.com/channel/best-sellers.html", scrolls=2)
        visit(pg, "homepage_again", "https://www.temu.com/", scrolls=3, wait=5)
        print("cookies (names):", sorted({c["name"] for c in ctx.cookies()}), flush=True)
        b.close()
    print("TOTAL wire traffic: %.2f MB in %d requests, %d image/media/font/css requests blocked (%s)"
          % (wire["bytes"] / 1048576.0, wire["n"], wire["blocked"], "PROXY" if USE_PROXY else "runner IP - no proxy GB used"), flush=True)


if __name__ == "__main__":
    main()
