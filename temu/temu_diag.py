"""Quick state check: crawler view vs normal shopper view (homepage feed), one request each. HTML only."""
import json, re
from curl_cffi import requests as cr
for label, url, h, imp in (
    ("crawler_search", "https://www.temu.com/search_result.html?search_key=dog%20shirt", {"User-Agent": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)"}, "chrome"),
    ("crawler_product", "https://www.temu.com/-g-603242230592430.html", {"User-Agent": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)"}, "chrome"),
    ("shopper_home", "https://www.temu.com/", {}, "safari_ios"),
    ("shopper_product", "https://www.temu.com/-g-603242230592430.html", {}, "safari_ios")):
    h["Accept-Language"] = "en-US,en;q=0.9"
    r = cr.get(url, impersonate=imp, headers=h, timeout=45); t = r.text
    print(json.dumps({"test": label, "status": r.status_code, "final": r.url[:70], "kb": len(r.content)//1024,
        "goods": len(set(re.findall(r'"goodsId":"?(\d{12,})', t))), "priceStr": len(re.findall(r'"priceStr":"\$', t)),
        "ld_price": re.findall(r'"price":"([\d.]+)","priceCurrency"', t)[:1], "og_title": bool(re.search(r'og:title', t))}), flush=True)
