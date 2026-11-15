"""PUBLISH the AlphaDog Styles shirt-type listings to Amazon US (putListingsItem, live). Owner approved publishing shirts (tees, tanks, women's tanks, polos) on Nov 14 2026.
Never touches prices of other products, never cancels or deletes anything. Hoodies and caps are NOT in the default set (barcode exemption not confirmed).
env: AMZ_PUBLISH_PRODS (default tee,wtank,tank,polo)  AMZ_ONLY (one listing id for a pilot)  Prints no credentials."""
import json, os, sys, urllib.request, collections, time
from concurrent.futures import ThreadPoolExecutor
import spapi, amz_validate as V
MP = spapi.MARKETPLACE
PRODS = set(os.environ.get("AMZ_PUBLISH_PRODS", "tee,wtank,tank,polo").split(","))
ONLY = os.environ.get("AMZ_ONLY", "").strip()
def main():
    c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"
    feed = json.loads(urllib.request.urlopen(V.FEED, timeout=120).read().decode())
    feed = [f for f in feed if f["prod"] in PRODS and (not ONLY or f["id"] == ONLY)]
    print("publishing", len(feed), "listings,", sum(len(f["children"]) for f in feed), "children; products", sorted(PRODS), "only", ONLY or "-"); sys.stdout.flush()
    # the main images must be reachable by Amazon before anything goes live
    probe = [k["img"] for f in feed[:6] for k in f["children"][:: max(1, len(f["children"]) // 3)][:3]][:12]
    bad = 0
    for p in probe:
        try:
            r = urllib.request.urlopen(urllib.request.Request("https://alphadogstyles.com/mk/" + p, headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
            ok = r.status == 200 and "image" in r.headers.get("content-type", "")
        except Exception as e: ok = False
        bad += 0 if ok else 1
    print("image probe: %d/%d reachable" % (len(probe) - bad, len(probe)))
    if bad > len(probe) // 3: print("ABORT: main images not live yet"); sys.exit(1)
    B = {pt: V.Builder(V.load_schema(c, pt), pt) for pt in {f["ptype"] for f in feed}}
    stat = collections.Counter(); errs = collections.Counter(); first = {}
    def put(sk, ptype, attrs):
        try:
            r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, sk), params={"marketplaceIds": MP, "issueLocale": "en_US", "mode": None} if False else {"marketplaceIds": MP, "issueLocale": "en_US"},
                           body={"productType": ptype, "requirements": "LISTING", "attributes": attrs})
        except spapi.SpError as e:
            return "HTTP_ERROR", [("ERROR", str(e)[:160])]
        iss = [(i.get("severity"), "%s %s" % (i.get("code"), (i.get("message") or "")[:140])) for i in r.get("issues", []) if i.get("severity") == "ERROR"]
        return r.get("status"), iss
    for F in feed:
        b = B[F["ptype"]]
        st, iss = put(F["parent_sku"], F["ptype"], b.parent(F)); stat[("PARENT", st)] += 1
        if st != "ACCEPTED" or iss:
            print("PARENT FAILED", F["id"], st, iss[:2]); errs.update(i[1] for i in iss); continue
        done = 0
        def one(k):
            return put(k["sku"], F["ptype"], b.child(F, k)[0])
        with ThreadPoolExecutor(4) as ex:
            for n, (st, iss) in enumerate(ex.map(one, F["children"])):
                stat[("CHILD", st if not iss else "ACCEPTED_WITH_ERRORS")] += 1
                for i in iss: errs[i[1]] += 1; first.setdefault(i[1], F["id"])
                if n == 60 and sum(v for k, v in stat.items() if k[0] == "CHILD" and k[1] != "ACCEPTED") > 12: print("ABORT: too many child errors, stopping"); print(dict(errs)); sys.exit(2)
        print("done", F["id"], len(F["children"]), "children", dict((k[1], v) for k, v in stat.items() if k[0] == "CHILD")); sys.stdout.flush()
    print("\n=== SUMMARY"); [print("  ", k, v) for k, v in sorted(stat.items(), key=str)]
    print("=== ERRORS"); [print("  ", k, v, first.get(k)) for k, v in errs.most_common(15)]
main()
