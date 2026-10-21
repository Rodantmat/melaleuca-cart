"""Logged-out probe of the public amazon.com pages (no seller account, no API key): can we read who owns the Buy Box and the offer list?"""
import os, re, sys, time, urllib.request, urllib.parse, json
OUT = "/tmp/so"; os.makedirs(OUT, exist_ok=True)
ASINS = ["B001TNTWC4", "B0030JJNBK", "B01JKSBEKC", "B08PSS11NS"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
proxy = os.environ.get("PROXY_URL", "").strip()

def fetch(url, use_proxy):
    h = [urllib.request.HTTPCookieProcessor()]
    if use_proxy and proxy:
        h.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    op = urllib.request.build_opener(*h)
    req = urllib.request.Request(url, headers=H)
    try:
        with op.open(req, timeout=45) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "ERR %r" % e

for mode in (False, True):
    if mode and not proxy:
        print("no PROXY_URL"); continue
    for a in ASINS:
        for kind, url in (("aod", "https://www.amazon.com/gp/product/ajax/aodAjaxMain/ref=dp_aod_NEW_mobile?asin=%s&pc=dp&experienceId=aodAjaxMain" % a),
                          ("dp", "https://www.amazon.com/dp/%s" % a)):
            st, body = fetch(url, mode)
            cap = bool(re.search(r"captcha|Robot Check|api-services-support", body, re.I))
            n_off = len(re.findall(r'id="aod-offer"', body))
            sold = re.findall(r'aod-offer-soldBy.*?>\s*([^<>]{2,60}?)\s*<', body, re.S)[:3]
            print("proxy=%s %s %s status=%s len=%d captcha=%s offers=%d soldBy=%s" % (mode, a, kind, st, len(body), cap, n_off, sold))
            open(OUT + "/%s_%s_%s.html" % ("px" if mode else "direct", a, kind), "w").write(body[:400000])
            time.sleep(3)
