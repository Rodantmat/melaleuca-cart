"""Probe: Dollar Tree + Marshalls readability from a plain GitHub runner (normal shopper client, no login, no proxy, HTML only, spaced)."""
import json, re, time, urllib.parse
from curl_cffi import requests as cr

H = {"Accept-Language": "en-US,en;q=0.9"}
WORDS = ["kitchen gadgets", "storage bins", "drawer organizer"]


def get(url, imp="chrome", ref=None, accept=None):
    h = dict(H)
    if ref: h["Referer"] = ref
    if accept: h["Accept"] = accept
    try:
        r = cr.get(url, impersonate=imp, headers=h, timeout=40)
        return r
    except Exception as e:
        print("  ERR", url[:80], str(e)[:100]); return None


def info(site, label, r, extra=None):
    if r is None:
        return
    t = r.text
    low = t[:80000].lower()
    block = [k for k in ("captcha", "access denied", "perimeterx", "px-captcha", "akamai", "incapsula", "are you a robot", "unusual traffic", "blocked", "cf-challenge", "just a moment") if k in low]
    d = {"site": site, "page": label, "status": r.status_code, "final": r.url[:100], "kb": len(r.content) // 1024, "block": block,
         "dollar_prices": len(re.findall(r'\$\s?\d+\.\d\d', t)), "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:70]}
    if extra: d.update(extra(t))
    print(json.dumps(d)[:800], flush=True)


def dt_extra(t):
    names = re.findall(r'"(?:name|productName|displayName)"\s*:\s*"([^"]{8,90})"', t)
    prices = re.findall(r'"(?:price|salePrice|listPrice|unitPrice)"\s*:\s*"?\$?([\d.]+)', t)
    cases = re.findall(r'(?:case of|case pack|pack of|qty)\s*[:\-]?\s*(\d{1,4})', t, re.I)
    forms = re.findall(r'<form[^>]+action="([^"]*search[^"]*)"', t, re.I)[:3]
    apis = sorted(set(re.findall(r'https?://[a-z0-9.-]*dollartree[a-z0-9.-]*/[a-z0-9/_-]*api[a-z0-9/_-]*', t, re.I)))[:6]
    return {"names": names[:3], "prices": prices[:6], "case_hits": cases[:5], "search_forms": forms, "api_urls": apis}


def mm_extra(t):
    names = re.findall(r'"(?:name|productName|displayName|title)"\s*:\s*"([^"]{8,90})"', t)
    prices = re.findall(r'"(?:price|salePrice|listPrice|currentPrice)"\s*:\s*"?\$?([\d.]+)', t)
    compare = re.findall(r'(?:Compare At|Comp\. Value)[^$]{0,40}\$\s?([\d.]+)', t, re.I)
    forms = re.findall(r'<form[^>]+action="([^"]*search[^"]*)"', t, re.I)[:3]
    prods = len(set(re.findall(r'/us/store/jump/product/[^"\s]+', t)))
    return {"names": names[:3], "prices": prices[:6], "compare_at": compare[:4], "search_forms": forms, "product_links": prods}


print("===== DOLLAR TREE", flush=True)
info("dollartree", "home", get("https://www.dollartree.com/"), dt_extra); time.sleep(8)
for w in WORDS:
    q = urllib.parse.quote(w)
    for label, u in (("search_a", "https://www.dollartree.com/searchresults?Ntt=%s" % q), ("search_b", "https://www.dollartree.com/search?q=%s" % q)):
        info("dollartree", label + " " + w, get(u, ref="https://www.dollartree.com/"), dt_extra); time.sleep(8)
for label, u in (("cat_kitchen", "https://www.dollartree.com/kitchen-dining"), ("cat_storage", "https://www.dollartree.com/storage-organization")):
    info("dollartree", label, get(u, ref="https://www.dollartree.com/"), dt_extra); time.sleep(8)

print("\n===== MARSHALLS", flush=True)
info("marshalls", "home", get("https://www.marshalls.com/us/store/index.jsp"), mm_extra); time.sleep(8)
for w in WORDS:
    q = urllib.parse.quote(w)
    info("marshalls", "search " + w, get("https://www.marshalls.com/us/store/shop/?_dyncharset=utf-8&Ntt=%s" % q, ref="https://www.marshalls.com/"), mm_extra); time.sleep(8)
info("marshalls", "cat_home", get("https://www.marshalls.com/us/store/shop/home/_/N-1186417548", ref="https://www.marshalls.com/"), mm_extra)
