"""Temu bridge - products + prices from Temu with NO login, NO proxy, NO browser, NO images.

How: Temu serves its pages fully rendered (products + prices in the HTML) to Pinterest's link crawler, so plain HTTPS
with that client header returns the same public data a shopper sees. Runs on a plain GitHub runner IP (free).

  search(query)      -> ~40 products for a keyword (Temu's own search, first page)
  product(goods_id)  -> one product: title, price, currency, stock, rating, reviews, images (urls only)
  best_sellers()     -> Temu best-seller channel (~40) - UNRELIABLE (page sometimes renders empty), not used by default

CLI:  python temu/temu_bridge.py --search "dog shirt|cat mug" --ids 603242230592430,601102364449217 --best --out temu/out/latest.json
"""
import argparse, html as _html, json, os, random, re, sys, time, urllib.parse
from datetime import datetime, timezone
from curl_cffi import requests as cr

BASE = "https://www.temu.com"
HDR = {"User-Agent": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)", "Accept-Language": "en-US,en;q=0.9"}
STATS = {"requests": 0, "bytes": 0, "failed": 0}


PACE = float(os.environ.get("TEMU_PACE", "35"))   # seconds between requests: ~17 per 10 min, well under the ~40-50 that tripped the block
_last = [0.0]


def fetch(url, tries=2):
    """One paced request. Never hammers: waits PACE s since the last request; retries only on network errors."""
    if STATS.get("closed"):
        return None, None
    for k in range(tries):
        wait = PACE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait + random.random() * 5)
        _last[0] = time.time()
        try:
            r = cr.get(url, impersonate="chrome", headers=HDR, timeout=45)
            STATS["requests"] += 1; STATS["bytes"] += len(r.content)
            if r.status_code == 200 and "bgn_verification" not in r.url and "login.html" not in r.url:
                return r.text, r.url
            print("  ! %s -> %s %s" % (url[:90], r.status_code, r.url[:90]), file=sys.stderr)
            break
        except Exception as e:
            print("  ! %s -> %s" % (url[:90], str(e)[:120]), file=sys.stderr)
    STATS["failed"] += 1
    return None, None


def trip(what):
    """Page came back without product data = Temu has closed the door. Stop the whole run (no hammering)."""
    STATS["closed"] = "%s at %s UTC" % (what, datetime.now(timezone.utc).strftime("%H:%M"))
    print("  !! no product data on %s - Temu is blocking; stopping this run" % what, file=sys.stderr)


def raw_data(html):
    """window.rawData = {...} -> dict"""
    m = re.search(r"window\.rawData\s*=\s*", html)
    if not m:
        return None
    s = html[m.end():]
    end = s.find("</script>")
    body = s[:end].strip().rstrip(";").strip()
    try:
        return json.loads(body)
    except Exception:
        # fall back: decode the first JSON value only
        try:
            return json.JSONDecoder().raw_decode(body)[0]
        except Exception:
            return None


def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except Exception:
        return None


def norm_goods(g):
    gid = str(g.get("goodsId") or g.get("goods_id") or "")
    if not gid.isdigit():
        return None
    pi = g.get("priceInfo") or {}
    price = pi.get("price")
    price = price / 100.0 if isinstance(price, (int, float)) else _num(pi.get("priceStr"))
    mk = pi.get("marketPrice")
    mk = mk / 100.0 if isinstance(mk, (int, float)) else _num(pi.get("marketPriceStr"))
    cm = g.get("comment") or {}
    title = g.get("goodsName") or g.get("title") or ""
    return {
        "goods_id": gid,
        "title": _html.unescape(title.strip()),
        "price": price,
        "list_price": mk,
        "currency": pi.get("currency") or "USD",
        "sold": g.get("salesTip") or g.get("salesNum"),
        "rating": cm.get("goodsScore"),
        "reviews": cm.get("commentNumTips"),
        "image": g.get("hdThumbUrl") or g.get("thumbUrl") or g.get("image"),
        "url": "%s/-g-%s.html" % (BASE, gid),
    }


def walk_goods(node, out, seen):
    if isinstance(node, dict):
        if ("goodsId" in node or "goods_id" in node) and ("goodsName" in node or "priceInfo" in node):
            r = norm_goods(node)
            if r and r["goods_id"] not in seen and r["title"]:
                seen.add(r["goods_id"]); out.append(r)
        for v in node.values():
            walk_goods(v, out, seen)
    elif isinstance(node, list):
        for v in node:
            walk_goods(v, out, seen)


def goods_from_html(html):
    out, seen = [], set()
    rd = raw_data(html)
    if rd:
        walk_goods(rd, out, seen)
    if not out:  # fallback: regex over the whole page
        for m in re.finditer(r'"goodsId":"?(\d{10,})"?,"goodsName":"((?:[^"\\]|\\.)*)"', html):
            gid = m.group(1)
            if gid in seen:
                continue
            tail = html[m.end():m.end() + 1500]
            p = re.search(r'"priceInfo":\{"price":(\d+)', tail)
            seen.add(gid)
            out.append({"goods_id": gid, "title": json.loads('"%s"' % m.group(2)), "price": int(p.group(1)) / 100.0 if p else None,
                        "url": "%s/-g-%s.html" % (BASE, gid)})
    return out


def search(query):
    html, final = fetch("%s/search_result.html?search_key=%s" % (BASE, urllib.parse.quote(query)))
    items = goods_from_html(html) if html else []
    if html and not items:
        trip("search %r" % query)
    return items


def best_sellers():
    html, _ = fetch(BASE + "/channel/best-sellers.html")
    return goods_from_html(html) if html else []


def product(gid):
    html, final = fetch("%s/-g-%s.html" % (BASE, gid))
    if not html:
        return {"goods_id": str(gid), "error": "not reachable"}
    rec = {"goods_id": str(gid), "url": final}
    for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(blk)
        except Exception:
            continue
        for d2 in (d if isinstance(d, list) else [d]):
            if not isinstance(d2, dict) or d2.get("@type") not in ("Product", "ProductGroup"):
                continue
            off = d2.get("offers") or {}
            if isinstance(off, list):
                off = off[0] if off else {}
            ar = d2.get("aggregateRating") or {}
            imgs = []
            for im in (d2.get("image") or []):
                imgs.append(im.get("contentURL") if isinstance(im, dict) else im)
            rec.update({
                "title": _html.unescape(d2.get("name") or ""),
                "price": _num(off.get("price") or off.get("lowPrice")),
                "high_price": _num(off.get("highPrice")),
                "currency": off.get("priceCurrency"),
                "in_stock": "InStock" in str(off.get("availability")),
                "rating": _num(ar.get("ratingValue")),
                "reviews": ar.get("reviewCount") or ar.get("ratingCount"),
                "sku": d2.get("sku"),
                "category": d2.get("category"),
                "description": (d2.get("description") or "")[:400],
                "images": [i for i in imgs if i][:6],
            })
    if rec.get("price") is None:
        m = re.search(r'product:price:amount"\s+content="([^"]+)"', html)
        if m:
            rec["price"] = _num(m.group(1))
    if not rec.get("title") and rec.get("price") is None:
        trip("product %s" % gid)
    if rec.get("price") is None:
        rec["note"] = "no price block on this product page (some big-ticket items) - use the price from search results"
    if not rec.get("title"):
        m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        rec["title"] = m.group(1).replace(" - Temu", "") if m else None
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", default="", help='queries separated by |')
    ap.add_argument("--ids", default="", help="goods ids, comma separated")
    ap.add_argument("--best", action="store_true")
    ap.add_argument("--out", default="temu/out/latest.json")
    a = ap.parse_args()
    t0 = time.time()
    res = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "searches": {}, "products": [], "best_sellers": []}
    for q in [x.strip() for x in a.search.split("|") if x.strip()]:
        items = search(q)
        res["searches"][q] = items
        print("\nSEARCH %r -> %d products" % (q, len(items)))
        for it in items[:15]:
            print("  $%-8s %-10s %-4s %-10s %s  %s" % (it.get("price"), it.get("sold") or "", it.get("rating") or "", it.get("goods_id"), (it.get("title") or "")[:70], ""))
    for gid in [x.strip() for x in a.ids.split(",") if x.strip()]:
        p = product(gid)
        res["products"].append(p)
        print("\nPRODUCT %s -> $%s %s stock=%s rating=%s reviews=%s  %s" % (gid, p.get("price"), p.get("currency"), p.get("in_stock"), p.get("rating"), p.get("reviews"), (p.get("title") or "")[:70]))
    if a.best:
        res["best_sellers"] = best_sellers()
        print("\nBEST SELLERS -> %d" % len(res["best_sellers"]))
        for it in res["best_sellers"][:10]:
            print("  $%-8s %-10s %s" % (it.get("price"), it.get("sold") or "", (it.get("title") or "")[:80]))
    res["stats"] = dict(STATS, mb=round(STATS["bytes"] / 1048576.0, 2), secs=round(time.time() - t0, 1))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print("\nSTATS", json.dumps(res["stats"]))


if __name__ == "__main__":
    main()
