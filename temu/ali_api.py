"""Official AliExpress Affiliate API (aliexpress.affiliate.product.query) as a source. Secrets: ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET (+ optional ALIEXPRESS_TRACKING_ID).
  python temu/ali_api.py --test "garlic press"   -> prints response shape/errors only (counts, no secrets)"""
import hashlib, hmac, json, os, sys, time, urllib.parse, urllib.request

URL = "https://api-sg.aliexpress.com/sync"
KEY, SECRET = os.environ.get("ALIEXPRESS_APP_KEY", ""), os.environ.get("ALIEXPRESS_APP_SECRET", "")
TRACK = os.environ.get("ALIEXPRESS_TRACKING_ID", "default")


def call(method, **p):
    q = {"app_key": KEY, "timestamp": str(int(time.time() * 1000)), "sign_method": "sha256", "method": method}
    q.update({k: str(v) for k, v in p.items()})
    base = "".join(k + q[k] for k in sorted(q))
    q["sign"] = hmac.new(SECRET.encode(), base.encode(), hashlib.sha256).hexdigest().upper()
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(q).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _num(x):
    try:
        return float(str(x).replace("US $", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def search(keyword, pages=1, size=50):
    out = []
    for pg in range(1, pages + 1):
        j = call("aliexpress.affiliate.product.query", keywords=keyword, page_no=pg, page_size=size, target_currency="USD", target_language="EN",
                 ship_to_country="US", tracking_id=TRACK, sort="LAST_VOLUME_DESC", fields="product_id,product_title,target_sale_price,target_original_price,lastest_volume,evaluate_rate,product_main_image_url,product_detail_url")
        resp = j.get("aliexpress_affiliate_product_query_response") or {}
        prods = (((resp.get("resp_result") or {}).get("result") or {}).get("products") or {}).get("product") or []
        if not prods:
            if pg == 1:
                print("  ali_api: no products; response keys:", list(j.keys())[:4], str(j)[:300])
            break
        for r in prods:
            out.append({"source": "aliexpress", "goods_id": "ali%s" % r.get("product_id"), "title": r.get("product_title") or "", "price": _num(r.get("target_sale_price")),
                        "list_price": _num(r.get("target_original_price")), "sold": r.get("lastest_volume"), "rating": r.get("evaluate_rate"), "reviews": None,
                        "image": r.get("product_main_image_url"), "url": r.get("product_detail_url"), "kw": keyword})
    return out


if __name__ == "__main__":
    if not KEY or not SECRET:
        print("ALIEXPRESS_APP_KEY / SECRET missing"); sys.exit(1)
    kw = sys.argv[2] if len(sys.argv) > 2 else "garlic press"
    rows = search(kw)
    print("ali_api: %d products for test keyword" % len(rows))
    for r in rows[:3]:
        print("  $%s sold %s %s" % (r["price"], r["sold"], r["title"][:60]))
