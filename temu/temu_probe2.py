"""Temu probe 2 - cheap, browserless routes (plain HTTPS with a Chrome TLS fingerprint via curl_cffi).
Tests, on whatever exit the workflow set up (runner IP / Proton VPN / Cloudflare WARP socks):
  A. product pages (SEO URL temu.com/-g-<id>.html and goods.html?goods_id=) -> is the product data in the HTML?
  B. homepage HTML -> does it carry the feed products?
  C. free search engines (DuckDuckGo html, Bing) for "site:temu.com <query>" -> product IDs without Temu's login-walled search
Nothing is bought, no login, no images (HTML only).
Env: TEMU_QUERY, TEMU_SOCKS (e.g. socks5h://127.0.0.1:40000 for WARP; empty = direct), TEMU_IDS (comma list of goods ids)
"""
import json, os, re, time, urllib.parse
from curl_cffi import requests as cr

QUERY = os.environ.get("TEMU_QUERY", "dog shirt")
SOCKS = os.environ.get("TEMU_SOCKS", "").strip()
IDS = [i for i in os.environ.get("TEMU_IDS", "601102364449217,603242230592430").split(",") if i]
PX = {"http": SOCKS, "https": SOCKS} if SOCKS else None
tot = {"bytes": 0}


def get(url, imp="chrome", referer=None):
    h = {"Accept-Language": "en-US,en;q=0.9"}
    if referer: h["Referer"] = referer
    t0 = time.time()
    try:
        r = cr.get(url, impersonate=imp, proxies=PX, timeout=40, headers=h, allow_redirects=True)
    except Exception as e:
        return None, {"err": str(e)[:160], "secs": round(time.time() - t0, 1)}
    tot["bytes"] += len(r.content)
    return r, {"status": r.status_code, "final": r.url[:150], "kb": round(len(r.content) / 1024), "secs": round(time.time() - t0, 1)}


def product_facts(html):
    f = {}
    m = re.search(r"<title>(.*?)</title>", html, re.S); f["title"] = (m.group(1).strip()[:120] if m else None)
    f["login_wall"] = ("login.html" in html[:4000]) or ("Sign in / Register" in html)
    f["verify_wall"] = "bgn_verification" in html[:20000]
    for k in ("goodsName", "goods_name", "salePrice", "minOnSalePrice", "linePrice", "priceStr", "skuList", "rawData", "ld+json", "og:title", "product:price"):
        f[k] = html.count(k)
    ld = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S)
    for blk in ld:
        try:
            d = json.loads(blk)
        except Exception:
            continue
        for d2 in (d if isinstance(d, list) else [d]):
            if isinstance(d2, dict) and d2.get("@type") in ("Product", "ProductGroup"):
                off = d2.get("offers") or {}
                if isinstance(off, list): off = off[0] if off else {}
                f["ld_product"] = {"name": str(d2.get("name"))[:100], "price": off.get("price") or off.get("lowPrice"), "cur": off.get("priceCurrency"),
                                   "rating": (d2.get("aggregateRating") or {}).get("ratingValue"), "reviews": (d2.get("aggregateRating") or {}).get("reviewCount")}
    mp = re.search(r'property="product:price:amount"\s+content="([^"]+)"', html)
    if mp: f["og_price"] = mp.group(1)
    pr = re.findall(r'"(?:salePrice|minOnSalePrice|price)"\s*:\s*"?(\$?[\d.]+)', html)
    f["price_samples"] = pr[:5]
    return f


def main():
    print("=== TEMU PROBE 2 (browserless)  exit=%s  query=%r" % (SOCKS or "direct", QUERY), flush=True)
    try:
        r, m = get("https://api.ipify.org?format=json"); print("exit ip:", r.text if r is not None else m, flush=True)
    except Exception:
        pass
    # A. product pages
    for gid in IDS[:3]:
        for label, url in (("seo", "https://www.temu.com/-g-%s.html" % gid), ("goods", "https://www.temu.com/goods.html?goods_id=%s" % gid)):
            for imp in ("chrome", "safari_ios"):
                r, meta = get(url, imp, referer="https://www.google.com/")
                out = {"test": "product_" + label, "id": gid, "imp": imp, **meta}
                if r is not None and r.status_code == 200:
                    out.update(product_facts(r.text))
                print(json.dumps(out, default=str)[:700], flush=True)
                time.sleep(2)
    # B. homepage
    r, meta = get("https://www.temu.com/", "chrome")
    out = {"test": "homepage", **meta}
    if r is not None and r.status_code == 200:
        h = r.text
        out["goods_ids_in_html"] = len(set(re.findall(r'goods_id[=":]+(\d{12,})', h)))
        out["verify_wall"] = "bgn_verification" in h[:20000]
        out["price_hits"] = len(re.findall(r'\$\d+\.\d\d', h))
    print(json.dumps(out)[:500], flush=True)
    # C. search engines -> Temu product ids
    q = "site:temu.com " + QUERY
    for label, url in (("ddg", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)),
                       ("bing", "https://www.bing.com/search?q=" + urllib.parse.quote(q) + "&setlang=en-US&cc=US")):
        r, meta = get(url, "chrome")
        out = {"test": "search_" + label, **meta}
        if r is not None and r.status_code == 200:
            ids = []
            for x in re.findall(r'-g-(\d{12,})\.html|goods_id(?:%3D|=)(\d{12,})', r.text):
                i = x[0] or x[1]
                if i not in ids: ids.append(i)
            out["temu_ids"] = len(ids); out["sample"] = ids[:8]
            out["captcha"] = ("captcha" in r.text.lower()[:30000]) or ("anomaly" in r.text.lower()[:30000])
            if ids and label == "ddg":
                IDS.extend([i for i in ids[:2] if i not in IDS])
        print(json.dumps(out)[:600], flush=True)
        time.sleep(2)
    # D. product pages found via search (proves the search -> page chain)
    for gid in IDS[2:4]:
        r, meta = get("https://www.temu.com/-g-%s.html" % gid, "chrome", referer="https://duckduckgo.com/")
        out = {"test": "product_from_search", "id": gid, **meta}
        if r is not None and r.status_code == 200: out.update(product_facts(r.text))
        print(json.dumps(out, default=str)[:700], flush=True)
    print("TOTAL html bytes: %.2f MB" % (tot["bytes"] / 1048576.0), flush=True)


if __name__ == "__main__":
    main()
