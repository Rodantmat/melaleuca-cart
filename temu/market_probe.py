"""Probe: how easy are AliExpress and SHEIN to read from a plain GitHub runner (no login, no proxy, HTML only, normal shopper client)?
For each: search page -> products/prices in the HTML? product page -> price? blocks after N spaced requests?"""
import json, re, time, urllib.parse
from curl_cffi import requests as cr

H = {"Accept-Language": "en-US,en;q=0.9"}
WORDS = ["garlic press", "drawer organizer", "silicone spatula", "shower caddy", "dog poop bag holder", "cable organizer"]


def get(url, imp="chrome", ref=None):
    h = dict(H)
    if ref:
        h["Referer"] = ref
    t = time.time()
    try:
        r = cr.get(url, impersonate=imp, headers=h, timeout=40)
        return r, round(time.time() - t, 1)
    except Exception as e:
        return None, str(e)[:100]


def blockinfo(r):
    t = r.text[:60000].lower()
    keys = [k for k in ("captcha", "punish", "x5secdata", "baxia", "slide to verify", "geetest", "access denied", "risk", "verify you are human",
                        "unusual traffic", "akamai", "_____tmd_____") if k in t]
    return keys


# ---------- AliExpress
def ali_items(h):
    ids = re.findall(r'"productId"\s*:\s*"?(\d{10,})', h) or re.findall(r'/item/(\d{10,})\.html', h)
    prices = re.findall(r'"formattedPrice"\s*:\s*"([^"]+)"', h) or re.findall(r'"salePrice"\s*:\s*\{[^}]*"formattedPrice"\s*:\s*"([^"]+)"', h)
    sold = re.findall(r'"tradeDesc"\s*:\s*"([^"]+)"', h)
    titles = re.findall(r'"displayTitle"\s*:\s*"([^"]{8,120})"', h)
    return list(dict.fromkeys(ids)), prices, sold, titles


def ali():
    print("\n===== ALIEXPRESS", flush=True)
    first_id = None
    for i, w in enumerate(WORDS):
        for host in ("www.aliexpress.us", "www.aliexpress.com") if i == 0 else ("www.aliexpress.us",):
            u = "https://%s/w/wholesale-%s.html?SearchText=%s" % (host, w.replace(" ", "-"), urllib.parse.quote(w))
            r, secs = get(u)
            if r is None:
                print(json.dumps({"site": "ali", "q": w, "host": host, "err": secs})); continue
            ids, prices, sold, titles = ali_items(r.text)
            print(json.dumps({"site": "ali", "req": i + 1, "q": w, "host": host, "status": r.status_code, "final": r.url[:90], "kb": len(r.content) // 1024, "secs": secs,
                              "ids": len(ids), "prices": len(prices), "sold": sold[:3], "price_sample": prices[:4], "title_sample": titles[:2], "block": blockinfo(r)})[:700], flush=True)
            if ids and not first_id:
                first_id = ids[0]
        time.sleep(10)
    if first_id:
        for imp in ("chrome", "safari_ios"):
            r, secs = get("https://www.aliexpress.us/item/%s.html" % first_id, imp)
            if r is None:
                print("product err", secs); continue
            h = r.text
            pr = re.findall(r'"(?:formatedActivityPrice|formatedPrice|minActivityAmount|salePrice)"\s*:\s*"?([^",}]+)', h)[:6]
            ld = re.findall(r'"price"\s*:\s*"?([\d.]+)"?\s*,\s*"priceCurrency"', h)[:2]
            print(json.dumps({"site": "ali", "product": first_id, "imp": imp, "status": r.status_code, "final": r.url[:90], "kb": len(r.content) // 1024,
                              "price_keys": pr, "ld_price": ld, "orders": re.findall(r'"(?:tradeCount|formatTradeCount)"\s*:\s*"?([^",}]+)', h)[:2],
                              "rating": re.findall(r'"averageStar"\s*:\s*"?([\d.]+)', h)[:1], "block": blockinfo(r)})[:700], flush=True)
            time.sleep(8)


# ---------- SHEIN
def shein():
    print("\n===== SHEIN", flush=True)
    first = None
    r, secs = get("https://us.shein.com/")
    if r is not None:
        print(json.dumps({"site": "shein", "page": "home", "status": r.status_code, "final": r.url[:90], "kb": len(r.content) // 1024, "block": blockinfo(r),
                          "goods_ids": len(set(re.findall(r'"goods_id"\s*:\s*"?(\d{5,})', r.text)))}), flush=True)
    time.sleep(10)
    for i, w in enumerate(WORDS):
        u = "https://us.shein.com/pdsearch/%s/" % urllib.parse.quote(w)
        r, secs = get(u, ref="https://us.shein.com/")
        if r is None:
            print(json.dumps({"site": "shein", "q": w, "err": secs})); continue
        h = r.text
        gids = list(dict.fromkeys(re.findall(r'"goods_id"\s*:\s*"?(\d{5,})', h)))
        prices = re.findall(r'"salePrice"\s*:\s*\{[^}]*"usdAmountWithSymbol"\s*:\s*"([^"]+)"', h) or re.findall(r'"amountWithSymbol"\s*:\s*"([^"]+)"', h)
        names = re.findall(r'"goods_name"\s*:\s*"([^"]{8,120})"', h)
        print(json.dumps({"site": "shein", "req": i + 1, "q": w, "status": r.status_code, "final": r.url[:90], "kb": len(r.content) // 1024, "secs": secs,
                          "goods": len(gids), "prices": len(prices), "price_sample": prices[:4], "name_sample": names[:2], "block": blockinfo(r)})[:700], flush=True)
        if gids and not first:
            first = gids[0]
        time.sleep(10)
    if first:
        r, secs = get("https://us.shein.com/p-%s.html" % first)
        if r is not None:
            print(json.dumps({"site": "shein", "product": first, "status": r.status_code, "final": r.url[:90], "kb": len(r.content) // 1024,
                              "prices": re.findall(r'"amountWithSymbol"\s*:\s*"([^"]+)"', r.text)[:4], "block": blockinfo(r)})[:600], flush=True)


ali()
shein()
