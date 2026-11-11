"""Apify as a cooldown-free source (official Apify API, the user's own token in secret APIFY_TOKEN).
  python temu/apify_source.py --check                       -> account plan, credits used, proxy groups available
  python temu/apify_source.py --ali  "garlic press|..." --max 60   -> AliExpress search via memo23/aliexpress-scraper (~$0.8 / 1,000)
  python temu/apify_source.py --temu "garlic press|..." --max 40   -> Temu search via yugenox/temu-scraper (~$2 / 1,000, needs UNBLOCKER proxy)
Rows are normalised to the temu_bridge format (goods_id, title, price, list_price, sold, rating, reviews, image, url) + source."""
import argparse, json, os, sys, time, urllib.request

API = "https://api.apify.com/v2"
TOKEN = os.environ.get("APIFY_TOKEN") or os.environ.get("APIFY_API_TOKEN") or ""
ACT_ALI = os.environ.get("APIFY_ALI_ACTOR", "memo23~aliexpress-scraper")
ACT_TEMU = os.environ.get("APIFY_TEMU_ACTOR", "yugenox~temu-scraper")


def call(method, path, body=None, timeout=60):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(API + path + sep + "token=" + TOKEN, method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def run_actor(actor, inp, wait_s=600):
    run = call("POST", "/acts/%s/runs" % actor, inp)["data"]
    rid, ds = run["id"], run["defaultDatasetId"]
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(10)
        run = call("GET", "/actor-runs/%s" % rid)["data"]
        if run["status"] not in ("READY", "RUNNING"):
            break
    items = call("GET", "/datasets/%s/items?clean=true&format=json" % ds, timeout=120) or []
    usage = run.get("usageTotalUsd")
    print("  apify %s: status %s, %d rows, cost $%s, %.0f s" % (actor, run["status"], len(items), usage, time.time() - t0), flush=True)
    return items, run


def _num(x):
    try:
        return float(str(x).replace("US $", "").replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def ali_search(queries, max_items=60):
    """The actor stops at 100 rows per run, so queries go in small groups (group x max_items <= 100)."""
    g = max(1, 100 // max(1, max_items))
    items, run = [], None
    for i in range(0, len(queries), g):
        part, run = run_actor(ACT_ALI, {"searchQueries": queries[i:i + g], "maxItems": min(100, max_items * len(queries[i:i + g])), "country": "US", "currency": "USD",
                                        "sortBy": "default", "scrapeDetails": False, "includeReviews": False,
                                        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}})
        items += part
    out = []
    for r in items:
        pid = str(r.get("productId") or "")
        if not pid:
            continue
        out.append({"source": "aliexpress", "goods_id": "ali" + pid, "title": r.get("title") or "", "price": r.get("salePriceValue") or _num(r.get("salePrice")),
                    "list_price": _num(r.get("originalPrice")), "sold": r.get("soldCountValue") or r.get("soldCount"), "rating": r.get("rating"),
                    "reviews": r.get("reviewCount"), "image": r.get("image"), "url": r.get("productUrl"), "kw": r.get("sourceQuery")})
    return out, run


def temu_search(queries, max_items=40):
    items, run = run_actor(ACT_TEMU, {"searchQueries": queries, "region": "US", "maxResults": max_items})
    out = []
    for r in items:
        gid = str(r.get("goods_id") or "")
        if not gid:
            continue
        out.append({"source": "temu-apify", "goods_id": gid, "title": r.get("title") or "", "price": _num(r.get("price")), "list_price": _num(r.get("market_price")),
                    "sold": r.get("sales_num") or r.get("sales_tip"), "rating": r.get("rating"), "reviews": r.get("review_count_text"),
                    "image": r.get("thumb_url"), "url": r.get("link_url"), "kw": r.get("search_query")})
    return out, run


ACT_AMZ = os.environ.get("APIFY_AMZ_ACTOR", "qianyii~amazon-product-scraper")


def amazon_info(asins):
    """Ratings + review counts for ASINs (Amazon product pages block the runner even through the proxy). ~$0.01 per ASIN, so callers cache."""
    asins = list(dict.fromkeys(a for a in asins if a))
    if not asins:
        return {}
    items, _run = run_actor(ACT_AMZ, {"asins": asins, "country": "us", "action": "product"}, wait_s=900)
    out = {}
    if items:
        print("  amazon actor fields: %s" % sorted(items[0].keys())[:40])
    for r in items:
        a = r.get("asin") or r.get("ASIN") or r.get("parent_asin")
        if not a:
            continue
        rc = r.get("rating_count") or r.get("reviews_count") or r.get("reviewsCount") or r.get("review_count")
        out[a] = {"rating": _num(r.get("rating") or r.get("stars")), "reviews": int(_num(rc)) if _num(rc) is not None else None,
                  "bought_month": r.get("bought_past_month") or r.get("bought_in_past_month") or r.get("boughtInPastMonth")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--ali", default="")
    ap.add_argument("--temu", default="")
    ap.add_argument("--amz", default="")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--out", default="/tmp/apify_out.json")
    a = ap.parse_args()
    if not TOKEN:
        print("no APIFY_TOKEN"); sys.exit(1)
    if a.check:
        me = call("GET", "/users/me")["data"]
        plan = me.get("plan") or {}
        print("apify account: plan %s, monthly credits $%s, proxy groups: %s" % (plan.get("id"), plan.get("monthlyUsageCreditsUsd"),
              [g.get("name") for g in ((me.get("proxy") or {}).get("groups") or [])]))
        try:
            lim = call("GET", "/users/me/limits")["data"]
            print("usage this cycle: $%s of $%s" % ((lim.get("current") or {}).get("monthlyUsageUsd"), (lim.get("limits") or {}).get("maxMonthlyUsageUsd")))
        except Exception as e:
            print("limits:", str(e)[:120])
    res = {}
    if a.ali:
        rows, run = ali_search([q for q in a.ali.split("|") if q], a.max)
        res["ali"] = rows
        for r in rows[:6]:
            print("   ALI $%-7s sold %-8s rating %-4s %s" % (r["price"], r["sold"], r["rating"], r["title"][:70]))
    if a.temu:
        rows, run = temu_search([q for q in a.temu.split("|") if q], a.max)
        res["temu"] = rows
        for r in rows[:6]:
            print("   TEMU $%-7s sold %-8s rating %-4s %s" % (r["price"], r["sold"], r["rating"], r["title"][:70]))
    if a.amz:
        info = amazon_info([x for x in a.amz.split("|") if x])
        print("  amazon_info: %d asins -> %s" % (len(info), [(v["rating"], v["reviews"], v["bought_month"]) for v in info.values()][:5]))
    json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
