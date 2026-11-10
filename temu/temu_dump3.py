"""Price by product id and product ids by keyword, browserless.
1. product page as seen by link-preview crawlers (they often get price meta for link cards)
2. free search engines -> Temu product ids for a keyword
Runner IP, HTML only."""
import json, os, re, time, urllib.parse
from curl_cffi import requests as cr

Q = os.environ.get("TEMU_QUERY", "dog shirt")
GID = "603242230592430"
UAS = {
    "safari": None,
    "facebook": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "whatsapp": "WhatsApp/2.23.20.0",
    "twitter": "Twitterbot/1.0",
    "slack": "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "discord": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "telegram": "TelegramBot (like TwitterBot)",
    "pinterest": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)",
}


def facts(h):
    f = {"kb": len(h) // 1024}
    f["dollar"] = re.findall(r'\$\d{1,4}\.\d\d', h)[:6]
    f["priceStr"] = re.findall(r'"priceStr":"([^"]+)"', h)[:4]
    f["og_price"] = re.findall(r'(?:product:price:amount|og:price:amount)"\s*content="([^"]+)"', h)[:2]
    f["ld_offers"] = re.findall(r'"offers"\s*:\s*\{[^}]{0,200}', h)[:2]
    f["minPrice"] = re.findall(r'"(?:minPrice|maxPrice|salePrice|minOnSalePrice|sale_price)"\s*:\s*"?([\d.]+)', h)[:4]
    m = re.search(r'<meta property="og:title" content="([^"]+)"', h); f["og_title"] = m.group(1)[:80] if m else None
    m = re.search(r'<meta property="og:image" content="([^"]+)"', h); f["og_image"] = bool(m)
    return f


print("=== 1. product %s as different clients" % GID, flush=True)
for name, ua in UAS.items():
    h = {"Accept-Language": "en-US,en;q=0.9"}
    if ua: h["User-Agent"] = ua
    try:
        r = cr.get("https://www.temu.com/-g-%s.html" % GID, impersonate="safari_ios" if not ua else "chrome", timeout=40, headers=h)
        print(json.dumps({"client": name, "status": r.status_code, "final": r.url[:90], **facts(r.text)})[:600], flush=True)
    except Exception as e:
        print(name, "ERR", str(e)[:120])
    time.sleep(1.5)

print("\n=== 2. search engines -> temu ids for %r" % Q, flush=True)
q = "temu " + Q
engines = {
    "ddg_html": "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote("site:temu.com " + Q),
    "ddg_lite": "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote("site:temu.com " + Q),
    "mojeek": "https://www.mojeek.com/search?q=" + urllib.parse.quote("site:temu.com " + Q),
    "yahoo": "https://search.yahoo.com/search?p=" + urllib.parse.quote("site:temu.com " + Q),
    "brave": "https://search.brave.com/search?q=" + urllib.parse.quote("site:temu.com " + Q),
    "startpage": "https://www.startpage.com/do/search?q=" + urllib.parse.quote("site:temu.com " + Q),
    "bing": "https://www.bing.com/search?q=" + urllib.parse.quote("site:temu.com " + Q) + "&cc=US&setlang=en",
}
for name, u in engines.items():
    try:
        r = cr.get(u, impersonate="chrome", timeout=40, headers={"Accept-Language": "en-US,en;q=0.9"})
        t = urllib.parse.unquote(urllib.parse.unquote(r.text))
        ids = []
        for i in re.findall(r'temu\.com/[^"\s<>]*?-g-(\d{12,})\.html', t) + re.findall(r'goods_id=(\d{12,})', t):
            if i not in ids: ids.append(i)
        titles = re.findall(r'temu\.com/([a-z0-9-]{10,80})-g-\d{12,}\.html', t)[:3]
        print(json.dumps({"engine": name, "status": r.status_code, "kb": len(r.content) // 1024, "temu_ids": len(ids), "ids": ids[:6], "slugs": titles,
                          "blocked_hint": any(w in r.text.lower()[:40000] for w in ("captcha", "unusual traffic", "are you a robot", "anomaly"))})[:600], flush=True)
    except Exception as e:
        print(name, "ERR", str(e)[:120])
    time.sleep(2)
