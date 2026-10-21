"""Buy Box intelligence from the PUBLIC amazon.com pages - logged out, no seller account, no SP-API key, its own proxy port (never the ones the Melaleuca accounts use).
   python bb_web.py [max_asins]      -> appends state/webbb.jsonl, writes state/webbb_latest.tsv
 What a shopper sees: the Buy Box price and who sells it (seller id + name, ships from), 'Only N left' (competitor stock!), the offer list (all sellers with prices),
 '100+ bought in past month' (Amazon's own demand signal), rating and review count.
 Pure parsing functions at the top (tested offline on saved pages); the browser part below."""
import html as H, json, os, re, sys, time, datetime as dt, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.join(HERE, "state")
ME = "A3431QI59MY9RE"


def txt(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I).replace("<br>", " "))).strip() if s else ""


def strip_tags(s):
    t = H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)))
    t = re.sub(r"<[^>]*>?", " ", t)                      # tags that were HTML-escaped inside attributes
    return re.sub(r"\s+", " ", t).strip()


def money(s):
    m = re.search(r"\$\s*([0-9][0-9,]*)(?:\s*\.\s*([0-9]{2}))?", s or "")
    return float(m.group(1).replace(",", "") + "." + (m.group(2) or "00")) if m else None


def section(h, marker, n=7000):
    i = h.find(marker)
    if i < 0:
        return ""
    i = max(0, h.rfind("<", 0, i))
    return h[i:i + n]


def dedupe(name):
    if not name:
        return None
    t = name.strip(); n = len(t)
    for k in range(1, n // 2 + 1):
        if n % 2 == 0 and t[:n // 2].strip() == t[n // 2:].strip():
            return t[:n // 2].strip()
    w = t.split()
    if len(w) % 2 == 0 and w[:len(w) // 2] == w[len(w) // 2:]:
        return " ".join(w[:len(w) // 2])
    return t


def parse_dp(h):
    """product page -> dict"""
    out = {"captcha": bool(re.search(r"validateCaptcha|Type the characters you see|Robot Check", h, re.I)) and "productTitle" not in h}
    bx = section(h, 'id="buybox"', 14000) or section(h, 'id="desktop_buybox"', 14000)
    price = re.search(r'id="corePrice_feature_div".*?class="a-offscreen">\$([0-9,.]+)<', h, re.S) or re.search(r'class="a-offscreen">\$([0-9,.]+)<', bx)
    out["bb_price"] = float(price.group(1).replace(",", "")) if price else None
    mi = section(h, 'id="merchantInfoFeature_feature_div"', 3500)
    fi = section(h, 'id="fulfillerInfoFeature_feature_div"', 3000)
    sid = re.search(r"seller=([A-Z0-9]{10,14})", mi) or re.search(r"seller=([A-Z0-9]{10,14})", bx)
    out["seller_id"] = sid.group(1) if sid else None
    t = strip_tags(fi) + " " + strip_tags(mi)
    sf = re.search(r"Ships from\s+(.+?)(?:\s+(?:Ships from|Sold by|Returns|Payment|Gift)|$)", t)
    sb = re.search(r"Sold by\s+(.+?)(?:\s+(?:Sold by|Returns|Payment|Gift|Ships from|Fulfilled)|$)", t)
    ss = re.search(r"Shipper / Seller\s+(.+?)(?:\s+(?:Shipper|Returns|Payment|Gift)|$)", t)
    out["ships_from"] = dedupe(sf.group(1)) if sf else (dedupe(ss.group(1)) if ss else None)
    out["sold_by"] = dedupe(sb.group(1)) if sb else (dedupe(ss.group(1)) if ss else None)
    if out["ships_from"] and out["ships_from"].startswith("Amazon"):
        out["ships_from"] = "Amazon"
    out["fulfil"] = ("F" if out["ships_from"] == "Amazon" else "M") if out["ships_from"] else None
    avail = strip_tags(section(h, 'id="availability"', 1500))
    m = re.search(r"Only (\d+) left in stock", avail or strip_tags(bx))
    out["left"] = int(m.group(1)) if m else None
    out["unavailable"] = bool(re.search(r"Currently unavailable|out of stock", avail, re.I))
    m = re.search(r"New\s*\((\d+)\)\s*from\s*\$\s*([0-9,.]+)", strip_tags(section(h, 'id="aod-ingress-link"', 1500)) or strip_tags(h[h.find("olp_feature_div"):][:1500]))
    out["offers_n"], out["offers_from"] = (int(m.group(1)), float(m.group(2).replace(",", ""))) if m else (None, None)
    m = re.search(r"([0-9,]+)\+?\s*(K\+?)?\s*bought in past month", strip_tags(h[h.find("social-proofing-faceout"):][:1500]) if "social-proofing-faceout" in h else "")
    out["bought_month"] = (int(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)) if m else None
    m = re.search(r'id="acrCustomerReviewText"[^>]*>\(?([0-9,]+)', h)
    out["reviews"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"([0-9.]+) out of 5 stars", strip_tags(section(h, 'id="averageCustomerReviews"', 2500)))
    out["rating"] = float(m.group(1)) if m else None
    out["choice"] = "Amazon's Choice" in h[:900000] and "Amazon's Choice" in strip_tags(section(h, 'id="acBadge_feature_div"', 1500) or "")
    out["we_win"] = out["seller_id"] == ME if out["seller_id"] else None
    return out


def parse_aod(h):
    """offers drawer (ajax, ~250 KB) -> {"pinned": offer or None, "offers": [offer...]}   offer = seller id, price, ships_from, sold_by, rating count, % positive"""
    def after(chunk, key, label):
        i = chunk.find(key)
        if i < 0:
            return None
        t = strip_tags(chunk[max(0, chunk.rfind("<", 0, i)):i + 2500])
        m = re.search(label + r"\s+(.{2,60}?)(?:\s+(?:Sold by|Ships from|Seller rating|Returns|Payment|Gift|\d)|$)", t)
        return dedupe(m.group(1)) if m else None

    def one(chunk):
        sid = re.search(r"seller=([A-Z0-9]{10,14})", chunk)
        t = strip_tags(re.sub(r"<style.*?</style>", " ", chunk, flags=re.S))
        pr = re.search(r"\$\s*([0-9]{1,4})\s*\.\s*([0-9]{2})\b", t)
        rt = re.search(r"\(([0-9,]+) ratings?\)\s*([0-9]+)% positive", t)
        sf, sb = after(chunk, "aod-offer-shipsFrom", "Ships from"), after(chunk, "aod-offer-soldBy", "Sold by")
        if not sf and not sb:
            m = re.search(r"Shipper / Seller\s+(.{2,60}?)(?:\s+(?:Seller rating|Returns|Payment|\d)|$)", t)
            sf = sb = dedupe(m.group(1)) if m else None
        return {"seller_id": sid.group(1) if sid else None, "price": float(pr.group(1) + "." + pr.group(2)) if pr else None,
                "ships_from": sf, "sold_by": sb, "fulfil": ("F" if sf == "Amazon" else "M") if sf else None,
                "ratings": int(rt.group(1).replace(",", "")) if rt else None, "pos_pct": int(rt.group(2)) if rt else None}
    out = {"pinned": None, "offers": []}
    i = h.find('id="aod-pinned-offer"')
    if i >= 0:
        j = h.find('id="aod-offer-list"', i)
        out["pinned"] = one(h[i:(j if j > i else i + 30000)])
    for part in h.split('id="aod-offer"')[1:]:
        o = one(part[:30000])
        if o["price"] is not None:
            out["offers"].append(o)
    return out


# ---------------------------------------------------------------- browser part
def run(max_asins=0):
    import random
    from playwright.sync_api import sync_playwright
    raw = os.environ.get("PROXY_URL", "").strip()
    port = int(os.environ.get("AMZ_PROXY_PORT", "10090"))
    kw = {"headless": False}
    if raw:
        u = urllib.parse.urlparse(raw); login = urllib.parse.unquote(u.username or "")
        if "__" not in login: login += "__cr.us"
        kw["proxy"] = {"server": "http://%s:%s" % (u.hostname, port), "username": login, "password": urllib.parse.unquote(u.password or "")}
    asins = []
    L = open(os.path.join(HERE, "costs.tsv")).read().splitlines(); hd = L[0].split("\t")
    for l in L[1:]:
        a_ = dict(zip(hd, l.split("\t"))).get("asin")
        if a_ and a_ not in asins: asins.append(a_)
    if max_asins: asins = asins[:max_asins]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    rows = []
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    with sync_playwright() as p:
        b = p.chromium.launch(**kw)
        ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900})
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font", "stylesheet") else r.continue_())   # traffic: text only
        pg = ctx.new_page()
        bytes_ = 0
        pg.goto("https://www.amazon.com/dp/%s?th=1&psc=1" % asins[0], timeout=60000, wait_until="domcontentloaded")      # warm-up: cookies / session like a shopper
        pg.wait_for_timeout(1500)
        dp_budget = int(os.environ.get("DP_MAX", "25"))                      # full product pages (2 MB each) only where they add something
        fails = 0
        for k, a in enumerate(asins):
            rec = {"t": now, "asin": a}
            try:
                ah = pg.evaluate("""async (asin) => { const r = await fetch('/gp/product/ajax/aodAjaxMain/ref=dp_aod_NEW_mobile?asin='+asin+'&pc=dp&experienceId=aodAjaxMain', {credentials:'include'}); return r.status + '|' + (r.status===200 ? await r.text() : ''); }""", a)
                st, _, body = ah.partition("|")
                bytes_ += len(body)
                if st != "200":
                    rec["err"] = "aod http %s" % st; fails += 1
                    if fails >= 4:
                        print("blocked (%s) - stopping this run" % st); rows.append(rec); break
                    time.sleep(20)
                else:
                    fails = 0
                    ao = parse_aod(body)
                    pin = ao["pinned"] or {}
                    rec.update({"bb_price": pin.get("price"), "seller_id": pin.get("seller_id"), "sold_by": pin.get("sold_by"), "ships_from": pin.get("ships_from"), "fulfil": pin.get("fulfil"),
                                "we_win": (pin.get("seller_id") == ME) if pin.get("seller_id") else None, "offers_n": len(ao["offers"]), "aod": ao["offers"][:15]})
                    if not pin.get("price") and not ao["offers"]:
                        rec["note"] = "no offers (unavailable?)"
                    elif rec.get("we_win") is False and dp_budget > 0:
                        dp_budget -= 1
                        pg.goto("https://www.amazon.com/dp/%s?th=1&psc=1" % a, timeout=60000, wait_until="domcontentloaded"); pg.wait_for_timeout(900)
                        h = pg.content(); bytes_ += len(h); d = parse_dp(h)
                        if d.get("captcha"):
                            rec["err"] = "captcha"; print("%s captcha - stopping this run" % a); rows.append(rec); break
                        rec.update({x: d.get(x) for x in ("left", "bought_month", "rating", "reviews", "choice")})
            except Exception as e:
                rec["err"] = str(e)[:100]
            rows.append(rec)
            if k % 20 == 0: print("  %d/%d  price=%s seller=%s  (%.1f MB so far)" % (k + 1, len(asins), rec.get("bb_price"), rec.get("sold_by"), bytes_ / 1048576.0)); sys.stdout.flush()
            time.sleep(random.uniform(1.5, 3.5))
        b.close()
    os.makedirs(S, exist_ok=True)
    with open(os.path.join(S, "webbb.jsonl"), "a") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    with open(os.path.join(S, "webbb_latest.tsv"), "w") as fh:
        fh.write("asin\tbb_price\tseller_id\tsold_by\tships_from\tleft\toffers_n\tbought_month\trating\treviews\twe_win\terr\n")
        for r in rows:
            fh.write("\t".join("" if r.get(c) is None else str(r.get(c)) for c in ["asin", "bb_price", "seller_id", "sold_by", "ships_from", "left", "offers_n", "bought_month", "rating", "reviews", "we_win", "err"]) + "\n")
    ok = [r for r in rows if r.get("bb_price")]
    print("web Buy Box: %d ASINs read, %d with a price, we win %d, errors %d" % (len(rows), len(ok), sum(1 for r in ok if r.get("we_win")), sum(1 for r in rows if r.get("err"))))


if __name__ == "__main__":
    try:
        run(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    except Exception as e:
        print("bb_web failed (ignored): %r" % e)
