"""Fetch AliExpress product videos (official affiliate API gives product_video_url) and store them PRIVATELY in Postgres deals.product_media (bytea). Counts only in log.
Env: ITEMS (AliExpress product ids, space separated), DATABASE_URL, ALIEXPRESS_APP_KEY/SECRET."""
import hashlib, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg, ali_api

cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
cx.execute("create table if not exists deals.product_media (id bigserial primary key, at timestamptz default now(), ali_id text, kind text, src text, size int, sha256 text, data bytea, unique (ali_id, src))")
ids = [i.replace("ali", "").strip() for i in (os.environ.get("ITEMS") or "").split() if i.strip()]
got = 0
for pid in ids:
    try:
        if "=" in pid:   # id=direct CDN video URL (discovered elsewhere): just download and store
            pid, direct = pid.split("=", 1)
            b = urllib.request.urlopen(urllib.request.Request(direct, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
            cx.execute("insert into deals.product_media(ali_id, kind, src, size, sha256, data) values (%s,'video',%s,%s,%s,%s) on conflict (ali_id, src) do nothing", (pid, direct.split("?")[0], len(b), hashlib.sha256(b).hexdigest(), b))
            got += 1; print("media: %s direct download stored %d bytes" % (pid, len(b))); continue
        j = ali_api.call("aliexpress.affiliate.productdetail.get", product_ids=pid, target_currency="USD", target_language="EN", tracking_id=ali_api.TRACK, country="US",
                         fields="product_id,product_title,product_video_url,product_main_image_url,product_small_image_urls")
        resp = j.get("aliexpress_affiliate_productdetail_get_response") or {}
        prods = (((resp.get("resp_result") or {}).get("result") or {}).get("products") or {}).get("product") or []
        if not prods:
            print("media: %s no detail; keys %s" % (pid, str(list(j.keys()))[:80])); continue
        p = prods[0]
        v = p.get("product_video_url")
        if not v:
            try:
                from curl_cffi import requests as cr
                pg = cr.get("https://www.aliexpress.us/item/%s.html" % pid, impersonate="chrome", timeout=60).text
                import re
                ms = re.findall(r'https?:[^"\'\\\s]+?\.mp4[^"\'\\\s]*', pg.replace("\\u002F", "/").replace("\\/", "/"))
                ms = [m.replace("&amp;", "&") for m in ms if "definition=h265" not in m]
                print("media: %s page fetch %d chars, %d mp4 links" % (pid, len(pg), len(ms)))
                v = ms[0] if ms else None
            except Exception as e:
                print("media: %s page fetch ERR %s" % (pid, str(e)[:80]))
        print("media: %s video url present: %s" % (pid, bool(v)))
        if not v:
            try:
                from playwright.sync_api import sync_playwright
                found = []
                with sync_playwright() as pw:
                    import urllib.parse as up
                    pu = os.environ.get("PROXY_URL", "")
                    kw = {}
                    if pu:
                        u = up.urlparse(pu)
                        kw["proxy"] = {"server": "%s://%s:%s" % (u.scheme or "http", u.hostname, u.port), "username": up.unquote(u.username or ""), "password": up.unquote(u.password or "")}
                    br = pw.chromium.launch(**kw)
                    ctx = br.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36", viewport={"width": 1280, "height": 900}, locale="en-US")
                    pgx = ctx.new_page()
                    pgx.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "font", "media", "stylesheet") else route.continue_())
                    pgx.on("response", lambda r: found.append(r.url) if ("video.aliexpress-media.com" in r.url and ".mp4" in r.url) else None)
                    pgx.goto("https://www.aliexpress.us/item/%s.html" % pid, wait_until="domcontentloaded", timeout=60000)
                    pgx.wait_for_timeout(9000)
                    srcs = pgx.evaluate("[...document.querySelectorAll('video')].map(x=>x.currentSrc||x.src).filter(Boolean)")
                    import re as _re
                    html = pgx.content().replace("\\u002F", "/").replace("\\/", "/")
                    srcs += [m.replace("&amp;", "&") for m in _re.findall(r'https?:[^"\'\\\s]+?\.mp4[^"\'\\\s]*', html)]
                    low = html.lower()
                    print("media: %s page html %d chars; captcha/punish markers: %s; has videoUrl key: %s; has item title key: %s" % (pid, len(html), any(k in low for k in ("captcha", "punish", "slide to verify", "unusual traffic")), "videourl" in low or "videoid" in low, "subject" in low))
                    print("media: %s browser sees %d video elements, %d mp4 responses, title ok: %s" % (pid, len(srcs), len(found), bool(pgx.title())))
                    cand = [u for u in srcs + found if "h265" not in u] or (srcs + found)
                    if cand:
                        v = cand[0]
                        b = urllib.request.urlopen(urllib.request.Request(v, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
                        cx.execute("insert into deals.product_media(ali_id, kind, src, size, sha256, data) values (%s,'video',%s,%s,%s,%s) on conflict (ali_id, src) do nothing",
                                   (pid, v.split("?")[0], len(b), hashlib.sha256(b).hexdigest(), b))
                        got += 1
                        print("media: %s stored %d bytes via browser" % (pid, len(b)))
                    br.close()
            except Exception as e:
                print("media: %s browser ERR %s" % (pid, str(e)[:100]))
            continue
        req = urllib.request.Request(v, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
        cx.execute("insert into deals.product_media(ali_id, kind, src, size, sha256, data) values (%s,'video',%s,%s,%s,%s) on conflict (ali_id, src) do nothing",
                   (pid, v, len(b), hashlib.sha256(b).hexdigest(), b))
        got += 1
        print("media: %s stored %d bytes" % (pid, len(b)))
    except Exception as e:
        print("media: %s ERR %s" % (pid, str(e)[:100]))
print("media: %d of %d stored" % (got, len(ids)))
