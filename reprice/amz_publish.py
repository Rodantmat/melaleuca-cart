"""PUBLISH the AlphaDog Styles shirt-type listings to Amazon US (putListingsItem, live). Owner approved publishing shirts (tees, tanks, women's tanks, polos) on Nov 14 2026.
Never touches prices of other products, never cancels or deletes anything. Hoodies and caps were added Nov 17 2026 after Amazon approved their product ID exemptions.
env: AMZ_PUBLISH_PRODS (default tee,wtank,tank,polo)  AMZ_ONLY (one listing id for a pilot)  Prints no credentials."""
import json, os, sys, urllib.request, collections, time
from concurrent.futures import ThreadPoolExecutor
import spapi, amz_validate as V
MP = spapi.MARKETPLACE
PRODS = set(os.environ.get("AMZ_PUBLISH_PRODS", "tee,wtank,tank,polo,hoodie,cap").split(","))   # hoodies and caps: product ID exemption approved Nov 17 2026 (validated, no 8560)
ONLY = os.environ.get("AMZ_ONLY", "").strip()
def main():
    c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
    feed = json.loads(urllib.request.urlopen(os.environ.get("AMZ_FEED_URL", V.FEED) + "?x=%d" % os.getpid(), timeout=120).read().decode())
    feed = [f for f in feed if f["prod"] in PRODS and (not ONLY or f["id"] == ONLY)]
    SK = {x.strip() for x in os.environ.get("AMZ_SKUS", "").split(",") if x.strip()}
    if SK:
        for f in feed: f["children"] = [k for k in f["children"] if k["sku"] in SK]
    PREVIEW = os.environ.get("AMZ_PREVIEW") == "1"       # check-only: sends mode=VALIDATION_PREVIEW, nothing is created
    if PREVIEW:
        for f in feed: f["children"] = f["children"][:: max(1, len(f["children"]) // 6)][:6]
    print("publishing", len(feed), "listings,", sum(len(f["children"]) for f in feed), "children; products", sorted(PRODS), "only", ONLY or "-"); sys.stdout.flush()
    # the main images must be reachable by Amazon before anything goes live
    probe = [x for f in feed[:6] for k in f["children"][:: max(1, len(f["children"]) // 12)][:12] for x in [k["img"]] + list(k.get("others") or [])][:40]
    bad = 0
    for p in probe:
        try:
            r = urllib.request.urlopen(urllib.request.Request("https://alphadogstyles.com/mk/" + p, headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
            ok = r.status == 200 and "image" in r.headers.get("content-type", "")
        except Exception as e: ok = False
        bad += 0 if ok else 1
    print("image probe: %d/%d reachable" % (len(probe) - bad, len(probe)))
    if bad > len(probe) // 3 and not PREVIEW: print("ABORT: main images not live yet"); sys.exit(1)
    B = {pt: V.Builder(V.load_schema(c, pt), pt) for pt in {f["ptype"] for f in feed}}
    stat = collections.Counter(); errs = collections.Counter(); first = {}
    if PREVIEW:
        for pt, bb in B.items():
            try: print("THEMES", pt, [t for t in V.enum_of(bb.p["variation_theme"])[0] if "STYLE" in t][:40])
            except Exception as e: print("THEMES", pt, "n/a", e)
    def put(sk, ptype, attrs, tries=3):
        st, iss = put1(sk, ptype, attrs)
        while st == "HTTP_ERROR" and "Unable to Retrieve" in str(iss) and tries > 1:     # transient Amazon-side failure: same request passes on retry
            time.sleep(20); tries -= 1; st, iss = put1(sk, ptype, attrs)
        return st, iss
    def put1(sk, ptype, attrs):
        try:
            r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, sk), params={"marketplaceIds": MP, "issueLocale": "en_US", **({"mode": "VALIDATION_PREVIEW"} if PREVIEW else {})},
                           body={"productType": ptype, "requirements": "LISTING", "attributes": attrs})
        except spapi.SpError as e:
            return "HTTP_ERROR", [("ERROR", " ".join(str(e).split())[:700])]
        iss = [(i.get("severity"), "%s %s" % (i.get("code"), (i.get("message") or "")[:300])) for i in r.get("issues", []) if i.get("severity") == "ERROR"]
        return r.get("status"), iss
    for F in feed:
        b = B[F["ptype"]]
        st, iss = put(F["parent_sku"], F["ptype"], b.parent(F)); stat[("PARENT", st)] += 1
        if st not in ("ACCEPTED", "VALID") or iss:
            print("PARENT FAILED", F["id"], st, iss[:2]); errs.update(i[1] for i in iss); continue
        done = 0
        def one(k):
            return put(k["sku"], F["ptype"], b.child(F, k)[0])
        with ThreadPoolExecutor(4) as ex:
            for n, (st, iss) in enumerate(ex.map(one, F["children"])):
                stat[("CHILD", st if not iss else "WITH_ERRORS")] += 1
                if PREVIEW and iss: print("PREVIEW-ERR", F["children"][n]["sku"], st, [i[1][:600] for i in iss][:3])
                for i in iss: errs[i[1]] += 1; first.setdefault(i[1], F["id"])
                if n == 60 and sum(v for k, v in stat.items() if k[0] == "CHILD" and k[1] not in ("ACCEPTED", "VALID")) > 12: print("ABORT: too many child errors, stopping"); print(dict(errs)); sys.exit(2)
        print("done", F["id"], len(F["children"]), "children", dict((k[1], v) for k, v in stat.items() if k[0] == "CHILD")); sys.stdout.flush()
    print("\n=== SUMMARY"); [print("  ", k, v) for k, v in sorted(stat.items(), key=str)]
    print("=== ERRORS"); [print("  ", k, v, first.get(k)) for k, v in errs.most_common(15)]
main()
