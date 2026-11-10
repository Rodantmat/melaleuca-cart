"""Pinterest-crawler view of Temu: full product JSON-LD, and do search/category pages render products for it?
Plus: what URLs do search engines actually return for Temu (to fix the id regex). Runner IP, HTML only."""
import json, os, re, time, urllib.parse
from curl_cffi import requests as cr

Q = os.environ.get("TEMU_QUERY", "dog shirt")
PIN = {"User-Agent": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)", "Accept-Language": "en-US,en;q=0.9"}


def g(u, h=PIN):
    return cr.get(u, impersonate="chrome", timeout=40, headers=h)


r = g("https://www.temu.com/-g-603242230592430.html")
for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', r.text, re.S):
    if '"Product"' in blk or '"Offer"' in blk:
        print("LDPRODUCT", blk[:2500])
print("META", re.findall(r'<meta[^>]+(?:product|og):[^>]+>', r.text)[:12])

for label, u in (("search", "https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(Q)),
                 ("category_pets", "https://www.temu.com/pet-supplies-o3-320.html"),
                 ("category_mens", "https://www.temu.com/mens-clothing-o3-1197.html"),
                 ("best", "https://www.temu.com/channel/best-sellers.html"),
                 ("home", "https://www.temu.com/")):
    try:
        x = g(u); t = x.text
        ids = set(re.findall(r'-g-(\d{12,})\.html', t)) | set(re.findall(r'"goodsId":"?(\d{12,})', t))
        lds = [b for b in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', t, re.S) if '"ItemList"' in b or '"Product"' in b]
        print(json.dumps({"page": label, "status": x.status_code, "final": x.url[:110], "kb": len(x.content) // 1024, "goods_ids": len(ids),
                          "prices": len(re.findall(r'"price(?:Str)?":"?\$?\d', t)), "ld_itemlist": len(lds), "ld_head": lds[0][:500] if lds else None,
                          "title": (re.search(r"<title>(.*?)</title>", t, re.S) or [None, None])[1]})[:900], flush=True)
    except Exception as e:
        print(label, "ERR", str(e)[:150])
    time.sleep(1.5)

for name, u in (("ddg_html", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote("site:temu.com " + Q)),
                ("bing", "https://www.bing.com/search?q=" + urllib.parse.quote("site:temu.com " + Q) + "&cc=US&setlang=en"),
                ("yahoo", "https://search.yahoo.com/search?p=" + urllib.parse.quote("site:temu.com " + Q))):
    x = cr.get(u, impersonate="chrome", timeout=40, headers={"Accept-Language": "en-US,en;q=0.9"})
    t = urllib.parse.unquote(urllib.parse.unquote(x.text))
    urls = []
    for m in re.findall(r'https?://(?:www\.)?temu\.com/[^"\s<>&]{3,200}', t):
        if m not in urls: urls.append(m)
    print("SE", name, x.status_code, "temu urls:", len(urls), urls[:10], flush=True)
    if not urls:
        print("   text head:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x.text))[:400])
    time.sleep(2)
