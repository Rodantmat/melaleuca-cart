"""Find Temu SEO pages that carry goodsList without login: robots/sitemaps, link patterns, category/search pages over plain HTTP,
and where (if anywhere) the price sits in a product page. Runner IP, HTML only."""
import json, os, re, collections, urllib.parse
from curl_cffi import requests as cr

H = {"Accept-Language": "en-US,en;q=0.9"}
Q = os.environ.get("TEMU_QUERY", "dog shirt")


def get(u, imp="safari_ios", ref=None):
    h = dict(H)
    if ref: h["Referer"] = ref
    try:
        r = cr.get(u, impersonate=imp, timeout=40, headers=h)
        return r
    except Exception as e:
        print("ERR", u, str(e)[:120]); return None


def goods(html):
    return re.findall(r'"goodsId":"?(\d{10,})"?,"goodsName":"([^"]{0,90})', html)


def report(label, u, imp="safari_ios", ref="https://www.google.com/"):
    r = get(u, imp, ref)
    if r is None: return None
    h = r.text
    g = goods(h)
    print(json.dumps({"page": label, "imp": imp, "status": r.status_code, "final": r.url[:140], "kb": len(r.content) // 1024,
                      "goodsList_items": len(g), "prices": len(re.findall(r'"priceStr":"\$', h)),
                      "login": "login.html" in r.url, "verify": "bgn_verification" in r.url, "sample": g[:3]})[:700], flush=True)
    return h


# 1. robots + sitemaps
r = get("https://www.temu.com/robots.txt", "chrome")
if r is not None:
    print("ROBOTS status", r.status_code); print("\n".join(l for l in r.text.splitlines() if l.lower().startswith(("sitemap", "allow", "disallow")))[:2500])
    for sm in re.findall(r'(?i)sitemap:\s*(\S+)', r.text)[:4]:
        s = get(sm, "chrome")
        if s is not None:
            locs = re.findall(r"<loc>(.*?)</loc>", s.text)
            print("SITEMAP", sm, s.status_code, len(s.content), "locs", len(locs), locs[:12])

# 2. homepage link patterns
home = get("https://www.temu.com/", "safari_ios")
if home is not None:
    links = set(re.findall(r'(?:href=\\?"|"linkUrl":")((?:https://www\.temu\.com)?(?:\\u002F|/)[^"\\ ]{3,160})', home.text))
    pats = collections.Counter()
    ex = {}
    for l in links:
        l = l.replace("\\u002F", "/")
        p = re.sub(r"\d{3,}", "N", l.split("?")[0])
        p = re.sub(r"/[a-z0-9-]{8,}-", "/SLUG-", p)
        pats[p] += 1; ex.setdefault(p, l)
    for p, n in pats.most_common(40):
        print("LINKPAT %3d %-70s e.g. %s" % (n, p[:70], ex[p][:150]))
    cats = [l.replace("\\u002F", "/") for l in links if "-o3-" in l or "/channel/" in l or "/w/" in l or "/subject" in l or "kuiper" in l]
    print("CANDIDATES", cats[:15])
    for c in cats[:4]:
        u = c if c.startswith("http") else "https://www.temu.com" + c
        report("cand", u)

# 3. keyword / category style URLs
slug = Q.replace(" ", "-")
for label, u in (("search", "https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(Q)),
                 ("search_gsb", "https://www.temu.com/search_result.html?search_key=%s&search_method=google_search_box" % urllib.parse.quote(Q)),
                 ("w_slug", "https://www.temu.com/w/%s.html" % slug),
                 ("w_slug2", "https://www.temu.com/w/%s" % slug),
                 ("kuiper", "https://www.temu.com/kuiper/%s.html" % slug),
                 ("best", "https://www.temu.com/channel/best-sellers.html"),
                 ("lightning", "https://www.temu.com/attendance/lightning-deals-us-73277-7-a-psurl.html"),
                 ("new", "https://www.temu.com/channel/new-arrivals.html")):
    for imp in ("safari_ios", "chrome"):
        report(label, u, imp)

# 4. product page: any price-like keys?
p = get("https://www.temu.com/-g-603242230592430.html", "safari_ios", "https://www.google.com/")
if p is not None:
    h = p.text
    keys = collections.Counter(re.findall(r'"([A-Za-z]*[Pp]rice[A-Za-z]*)"\s*:', h))
    print("PRODUCT price-like keys:", keys.most_common(20))
    for k in list(keys)[:4]:
        i = h.find('"%s"' % k); print("PCTX", k, h[max(0, i - 150):i + 200].replace("\n", " "))
    print("PRODUCT goodsList items:", len(goods(h)), goods(h)[:3])
