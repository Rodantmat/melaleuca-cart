"""Does each SKU / ASIN still exist on Amazon? Asks Amazon directly (read-only) and writes state/sku_check.tsv.
Sources: merchant listings report (all statuses), FBA planning report, Listings Items API per SKU, Catalog API per ASIN."""
import json, os, sys, time
import spapi

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state")
MK = "ATVPDKIKX0DER"
WATCH = [s for s in (sys.argv[1:] or []) if s]


def table(txt):
    L = txt.splitlines()
    if not L: return []
    h = L[0].split("\t")
    return [dict(zip(h, l.split("\t"))) for l in L[1:] if l.strip()]


def main():
    c = spapi.load_creds(HERE)
    seller = c.get("SELLER_ID", "")
    if not seller:
        try: seller = open(os.path.join(STATE, "seller.txt")).read().strip()
        except Exception: seller = ""
    if not seller:
        print("no seller id (state/seller.txt missing)"); return 2
    st, txt = spapi.report(c, "GET_MERCHANT_LISTINGS_ALL_DATA")
    lst = {r.get("seller-sku"): r for r in table(txt)} if st == "DONE" else {}
    print("merchant listings report:", st, len(lst), "rows")
    st2, txt2 = spapi.report(c, "GET_FBA_INVENTORY_PLANNING_DATA")
    plan = {r.get("sku"): r for r in table(txt2)} if st2 == "DONE" else {}
    print("planning report:", st2, len(plan), "rows")
    skus = sorted(set(lst) | set(plan) | set(WATCH))
    out = [["sku", "listing_report_status", "listing_report_asin", "planning_asin", "planning_available", "planning_inbound", "api_exists", "api_status", "api_asin", "api_issues", "catalog_asin_exists", "name"]]
    cat_cache = {}
    for i, sku in enumerate(skus):
        l, p = lst.get(sku, {}), plan.get(sku, {})
        ex, stt, asin, iss = "", "", "", ""
        try:
            r = spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sku),
                           params={"marketplaceIds": MK, "includedData": "summaries,issues"}, quiet=True)
            sm = (r.get("summaries") or [{}])[0]
            ex, stt, asin = "yes", ",".join(sm.get("status") or []), sm.get("asin", "")
            iss = " | ".join("%s:%s" % (x.get("severity"), (x.get("message") or "")[:70]) for x in (r.get("issues") or [])[:3])
        except spapi.SpError as e:
            ex = "NO (404)" if e.code == 404 else "error %s" % e.code
        a = asin or l.get("asin1") or p.get("asin") or ""
        ce = ""
        if a and (sku in WATCH or ex != "yes"):
            if a not in cat_cache:
                try:
                    spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": MK, "includedData": "summaries"}, quiet=True)
                    cat_cache[a] = "yes"
                except spapi.SpError as e:
                    cat_cache[a] = "NO (404)" if e.code == 404 else "error %s" % e.code
            ce = cat_cache[a]
        name = (l.get("item-name") or p.get("product-name") or "")[:60]
        out.append([sku, l.get("status", ""), l.get("asin1", ""), p.get("asin", ""), p.get("available", ""), p.get("inbound-quantity", ""),
                    ex, stt, asin, iss, ce, name])
        time.sleep(0.25)
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "sku_check.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join("\t".join(str(x) for x in r) for r in out) + "\n")
    bad = [r for r in out[1:] if r[6] != "yes"]
    print("checked %d SKUs; %d not found / not readable" % (len(out) - 1, len(bad)))
    for r in out[1:]:
        if r[0] in WATCH or r[6] != "yes":
            print("  ", " | ".join(str(x) for x in r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
