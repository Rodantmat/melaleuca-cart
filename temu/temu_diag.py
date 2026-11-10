"""Why do later requests come back empty? Per-request detail + recovery timing + header variants.
Env TEMU_SOCKS optional (WARP). HTML only."""
import json, os, re, time, urllib.parse
from curl_cffi import requests as cr

SOCKS = os.environ.get("TEMU_SOCKS", "").strip()
PX = {"http": SOCKS, "https": SOCKS} if SOCKS else None
UAS = {
    "pin1": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)",
    "pin2": "Pinterest/0.2 (+http://www.pinterest.com/)",
    "pin3": "Mozilla/5.0 (compatible; Pinterestbot/1.0; +http://www.pinterest.com/bot.html)",
}
T0 = time.time()


def hit(label, url, ua="pin1", imp="chrome"):
    t = time.time()
    try:
        r = cr.get(url, impersonate=imp, proxies=PX, timeout=45, headers={"User-Agent": UAS[ua], "Accept-Language": "en-US,en;q=0.9"})
        h = r.text
        n = len(set(re.findall(r'"goodsId":"?(\d{12,})', h)))
        ld = '"@type":"Product"' in h
        title = (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:50]
        print(json.dumps({"t": round(t - T0), "label": label, "ua": ua, "imp": imp, "status": r.status_code, "final": r.url[:80], "kb": len(r.content) // 1024,
                          "goods": n, "ld_product": ld, "rawData": "window.rawData" in h, "title": title,
                          "cookies": list(r.cookies.keys())[:6]}), flush=True)
        return n or ld
    except Exception as e:
        print(json.dumps({"t": round(t - T0), "label": label, "err": str(e)[:120]}), flush=True)


S = lambda q: "https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(q)
P = lambda g: "https://www.temu.com/-g-%s.html" % g

print("=== exit", SOCKS or "runner", flush=True)
# 1. burst: 6 requests, 3 s apart
for q in ("dog hoodie", "cat mug", "phone case", "yoga mat", "dog leash", "garden hose"):
    hit("burst", S(q)); time.sleep(3)
# 2. are products blocked too? other UA variants / impersonations?
hit("product", P("603242230592430"))
for ua in ("pin2", "pin3"):
    hit("ua_variant", S("cat mug"), ua)
for imp in ("safari_ios", "firefox"):
    hit("imp_variant", S("cat mug"), "pin1", imp)
# 3. recovery: retry the same search every 60 s for up to 8 min
for k in range(8):
    time.sleep(60)
    ok = hit("recover_60s_x%d" % (k + 1), S("cat mug"))
    if ok:
        # after recovery, how many in a row with 20 s spacing?
        for q in ("phone case", "yoga mat", "dog leash", "garden hose", "led strip lights"):
            time.sleep(20); hit("spaced20", S(q))
        break
