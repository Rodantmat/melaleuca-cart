"""Temu -> Amazon deal finder (read-only on Amazon: catalog search, Buy Box/offers, fee estimates - nothing is listed or changed).

For every cheap Temu item:
  1. find the matching Amazon listings (SP-API catalog keyword search, title similarity)
  2. read the live Buy Box / offers (reprice/amazon_pricing.py parser) -> COMPETITIVE / ABANDONED (no offers at all)
  3. estimate Amazon fees (SP-API fees estimate, FBA; falls back to referral 15% + size-tier FBA guess)
  4. profit = Amazon price - fees - Temu cost x (1 + tax) - inbound;  ROI = profit / landed cost
     ABANDONED listings have no live price -> report the break-even and target (ROI_MIN) price + list price if Amazon has one
Inputs: --from-json (a temu_bridge.py output) and/or --search "kw1|kw2" (pulls Temu live, paced).
Output: CSV + JSON ranked (best ROI first), printed top table.
"""
import argparse, csv, json, math, os, re, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
sys.path.insert(0, HERE)
import spapi, amazon_pricing  # noqa: E402

MK = spapi.MARKETPLACE
TAX = float(os.environ.get("TEMU_TAX", "0.0775"))        # San Diego sales tax on the Temu order
INBOUND = float(os.environ.get("INBOUND_PER_UNIT", "0.75"))  # shipping the unit into FBA
ROI_MIN = float(os.environ.get("ROI_MIN", "0.30"))
MAX_TEMU = float(os.environ.get("MAX_TEMU_PRICE", "25"))
SIM_MIN = float(os.environ.get("SIM_MIN", "0.30"))
WHOLESALE_F = float(os.environ.get("WHOLESALE_FACTOR", "0.60"))    # Alibaba unit price ~ Temu price x this
FREIGHT = float(os.environ.get("FREIGHT_PER_UNIT", "1.00"))         # Alibaba freight + duties per unit (estimate)
# generic products only: no printed apparel / POD-style items, no brands, characters or licences
EXCLUDE = re.compile(r"\b(t-?shirts?|tees?|hoodies?|sweatshirts?|jumpsuit|mugs?|tumblers?|posters?|canvas|wall art|metal sign|signs?|stickers?|"
                     r"keychains?|flag|banner|blanket with|print(ed)? (t|tee|shirt)|graphic|slogan|quote|funny|christmas|halloween|"
                     r"disney|marvel|pokemon|hello kitty|barbie|nfl|nba|mlb|harry potter|star wars|nike|adidas|apple|iphone|samsung|"
                     r"stanley|yeti|owala|lego|sanrio|minecraft|bluey|jesus|christian)\b", re.I)
# extra Amazon paperwork even with liability insurance: CPC (children's), hazmat review (lithium), ingestible/cosmetic rules
RISK = re.compile(r"\b(lithium|li-ion|batter(y|ies) included|baby|infant|toddler|kids?|children|toys?|"
                  r"supplement|edible|cosmetic|serum|cream|lotion|helmet|life jacket|smoke detector|carbon monoxide)\b", re.I)
PER_KW = int(os.environ.get("PER_KW", "20"))                       # first N Temu results per keyword (Temu's own ranking)


def keyword_chunk(spec):
    """'chunk:2/4' -> [(category, keyword)] from temu/keywords.txt"""
    rows = []
    for ln in open(os.path.join(HERE, "keywords.txt")):
        ln = ln.strip()
        if ln and not ln.startswith("#") and "|" in ln:
            c_, k_ = [x.strip() for x in ln.split("|", 1)]; rows.append((c_, k_))
    n, m = [int(x) for x in spec.split(":", 1)[1].split("/")]
    size = -(-len(rows) // m)
    return rows[(n - 1) * size:n * size]


_UNUSED_DEFAULT_KWS = ("kitchen gadgets|vegetable chopper|silicone kitchen utensils|drawer organizer|fridge organizer|spice rack organizer|"
               "under sink organizer|cable organizer|closet organizer|shoe rack|bathroom organizer|shower caddy|cleaning brush|"
               "lint remover|reusable food storage|oil sprayer|garlic press|measuring cups|can opener|ice cube tray|"
               "car organizer|phone stand|desk organizer|travel organizer|jewelry organizer|makeup organizer|storage bins|"
               "hangers|clothes drying rack|pet hair remover")
STOP = set("a an and the for with of in on to by from at as is it this that your you our pc pcs 1pc 2pcs piece pieces set pack "
           "new 2d flat not 3d style design gift gifts women's men's womens mens unisex suitable perfect ideal use".split())


def toks(s):
    s = (s or "").lower().replace("&#39;", "'")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [t for t in s.split() if t not in STOP and len(t) > 1 and not re.fullmatch(r"\d+(pc|pcs)?", t)]


def sim(a, b):
    A, B = set(toks(a)), set(toks(b))
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B)) ** 0.5 / float(min(len(A), len(B))) ** 0.5   # cosine-like overlap


def query_for(title):
    return " ".join(toks(title)[:7])


def catalog_search(c, q):
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items", params={"keywords": q, "marketplaceIds": MK, "includedData": "summaries,salesRanks,attributes", "pageSize": 10}, quiet=True, tries=4)
    except Exception as e:
        print("  catalog ERR %s" % str(e)[:120]); return []
    out = []
    for it in r.get("items") or []:
        sm = (it.get("summaries") or [{}])[0]
        rank = None
        for sr in it.get("salesRanks") or []:
            for d in (sr.get("displayGroupRanks") or []) + (sr.get("classificationRanks") or []):
                if d.get("rank") and (rank is None or d["rank"] < rank[0]):
                    rank = (d["rank"], d.get("title"))
        lp = None
        for x in ((it.get("attributes") or {}).get("list_price") or []):
            try:
                lp = float(x.get("value_with_tax") or x.get("value")); break
            except Exception:
                pass
        out.append({"asin": it.get("asin"), "title": sm.get("itemName") or "", "brand": sm.get("brand") or sm.get("brandName"),
                    "rank": rank[0] if rank else None, "rank_cat": rank[1] if rank else None, "list_price": lp})
    return out


def fees_batch(c, pairs):
    """pairs [(asin, price)] -> {asin: total fees} via getMyFeesEstimates (batch of 20)."""
    res = {}
    for i in range(0, len(pairs), 20):
        chunk = pairs[i:i + 20]
        body = [{"FeesEstimateRequest": {"MarketplaceId": MK, "IsAmazonFulfilled": True, "Identifier": "%s@%.2f" % (a, p),
                                         "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": round(p, 2)}}},
                 "IdType": "ASIN", "IdValue": a} for a, p in chunk]
        try:
            r = spapi.call(c, "POST", "/products/fees/v0/feesEstimate", body=body, quiet=True, tries=4)
            for x in (r if isinstance(r, list) else r.get("payload") or []):
                fr = x.get("FeesEstimateResult") or x
                ident = ((fr.get("FeesEstimateIdentifier") or {}).get("IdValue"))
                tot = (((fr.get("FeesEstimate") or {}).get("TotalFeesEstimate") or {}).get("Amount"))
                if ident and tot is not None:
                    res[ident] = float(tot)
        except Exception as e:
            print("  fees ERR %s" % str(e)[:160])
        time.sleep(2.2)
    return res


def fee_guess(price):
    return round(max(0.30, 0.15 * price) + (3.22 if price < 10 else 3.86), 2)   # referral + small/large-standard FBA guess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", default="")
    ap.add_argument("--search", default="")
    ap.add_argument("--out", default="/tmp/deals")
    ap.add_argument("--per-item", type=int, default=1)
    a = ap.parse_args()
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    temu = []
    if a.from_json:
        d = json.load(open(a.from_json))
        for q, items in (d.get("searches") or {}).items():
            for it in items:
                it["kw"] = q; temu.append(it)
    if a.search:
        import temu_bridge
        pairs = keyword_chunk(a.search) if a.search.startswith("chunk:") else [("-", x.strip()) for x in a.search.split("|") if x.strip()]
        print("Temu keywords: %d (%s)" % (len(pairs), ", ".join(k for _, k in pairs)))
        for cat, q in pairs:
            for it in temu_bridge.search(q)[:PER_KW]:
                it["kw"] = q; it["cat"] = cat; temu.append(it)
            if temu_bridge.STATS.get("closed"):
                print("Temu blocked (%s) - continuing with what was pulled" % temu_bridge.STATS["closed"]); break
    seen, items = set(), []
    for it in temu:
        if it["goods_id"] in seen or not it.get("price") or it["price"] > MAX_TEMU or EXCLUDE.search(it.get("title") or ""):
            continue
        seen.add(it["goods_id"]); items.append(it)
    print("Temu items to check: %d (price <= $%.0f)" % (len(items), MAX_TEMU))

    # 1. match
    rows, asins = [], set()
    for n, it in enumerate(items, 1):
        q = query_for(it["title"])
        cands = catalog_search(c, q)
        for cd in cands:
            cd["sim"] = round(sim(it["title"], cd["title"]), 2)
        cands = sorted([x for x in cands if x["sim"] >= SIM_MIN], key=lambda x: -x["sim"])[:a.per_item]
        if not cands:
            rows.append({"temu": it, "amz": None})
        for cd in cands:
            rows.append({"temu": it, "amz": cd}); asins.add(cd["asin"])
        if n % 25 == 0:
            print("  matched %d/%d items, %d ASINs" % (n, len(items), len(asins)))
        time.sleep(0.6)
    print("Amazon candidates: %d ASINs" % len(asins))

    # 2. live offers
    live = amazon_pricing.fetch(spapi.call, c, sorted(asins), log=print) if asins else {}

    # 3. fees at the live price (competitive) or at the list price / 3x Temu (abandoned)
    pairs = []
    for r in rows:
        if not r["amz"]:
            continue
        L = live.get(r["amz"]["asin"]) or {}
        price = L.get("bb") or L.get("low_new") or r["amz"].get("list_price")
        r["status"] = "COMPETITIVE" if (L.get("bb") or L.get("n_offers")) else "ABANDONED"
        r["amz_price"] = round(price, 2) if price else None
        r["fee_price"] = r["amz_price"] or round(max(9.99, r["temu"]["price"] * 3), 2)
        pairs.append((r["amz"]["asin"], r["fee_price"]))
    fees = fees_batch(c, sorted(set(pairs)))

    # 4. profit
    out = []
    for r in rows:
        t, m = r["temu"], r["amz"]
        cost = round(t["price"] * (1 + TAX) + INBOUND, 2)
        rec = {"cat": t.get("cat"), "risk_flag": (RISK.search(t["title"]) or [None])[0], "kw": t.get("kw"), "temu_id": t["goods_id"], "temu_title": t["title"][:120], "temu_price": t["price"], "landed_cost": cost, "temu_url": t["url"]}
        if not m:
            rec.update({"status": "NO MATCH"}); out.append(rec); continue
        L = live.get(m["asin"]) or {}
        fee = fees.get("%s@%.2f" % (m["asin"], r["fee_price"]))
        fee_src = "spapi" if fee is not None else "guess"
        if fee is None:
            fee = fee_guess(r["fee_price"])
        # break-even and target price solve p - fee(p) = cost (fee scales ~ with price)
        fixed = fee - 0.15 * r["fee_price"]          # FBA + other fixed fees; referral ~15% scales with price
        be = round((cost + fixed) / 0.85, 2)
        target = round((cost * (1 + ROI_MIN) + fixed) / 0.85, 2)
        rec.update({"status": r["status"], "asin": m["asin"], "amz_title": m["title"][:120], "brand": m.get("brand"), "match": m["sim"],
                    "sales_rank": m.get("rank"), "rank_cat": m.get("rank_cat"), "amz_price": r["amz_price"], "list_price": m.get("list_price"),
                    "offers": L.get("n_offers", 0), "fba_offers": L.get("n_afn", 0), "fees": round(fee, 2), "fees_src": fee_src,
                    "breakeven_price": be, "target_price": target, "amz_url": "https://www.amazon.com/dp/" + m["asin"]})
        wcost = round(t["price"] * WHOLESALE_F + FREIGHT + INBOUND, 2)
        rec["wholesale_cost_est"] = wcost
        rec["target_price_wholesale"] = round((wcost * (1 + ROI_MIN) + fixed) / 0.85, 2)
        if r["amz_price"]:
            p = r["amz_price"] - fee - cost
            pw = r["amz_price"] - fee - wcost
            rec.update({"profit": round(p, 2), "roi": round(p / cost, 2), "profit_wholesale": round(pw, 2), "roi_wholesale": round(pw / wcost, 2)})
        out.append(rec)
    out.sort(key=lambda x: (-(x.get("roi_wholesale") or -9), x.get("status") != "ABANDONED"))
    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    tag = a.search.replace(":", "").replace("/", "of") if a.search.startswith("chunk:") else "latest"
    json.dump({"run_at": stamp, "params": {"tax": TAX, "inbound": INBOUND, "roi_min": ROI_MIN, "max_temu": MAX_TEMU, "sim_min": SIM_MIN}, "rows": out},
              open(os.path.join(a.out, "deals_%s.json" % tag), "w"), indent=1)
    cols = ["status", "roi_wholesale", "profit_wholesale", "wholesale_cost_est", "roi", "profit", "temu_price", "landed_cost", "amz_price", "fees", "fees_src", "breakeven_price", "target_price", "target_price_wholesale", "list_price",
            "offers", "fba_offers", "sales_rank", "rank_cat", "match", "risk_flag", "cat", "kw", "temu_title", "amz_title", "brand", "asin", "amz_url", "temu_url", "temu_id"]
    with open(os.path.join(a.out, "deals_%s.csv" % tag), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    good = [x for x in out if (x.get("roi_wholesale") or -1) >= ROI_MIN]
    ab = [x for x in out if x.get("status") == "ABANDONED"]
    print("\nRESULT: %d generic Temu items, %d matched rows, %d profitable at est. wholesale (ROI >= %.0f%%), %d of them also at Temu price, %d abandoned listings" % (
        len(items), sum(1 for x in out if x.get("asin")), len(good), ROI_MIN * 100, sum(1 for x in good if (x.get("roi") or -1) >= ROI_MIN), len(ab)))
    print("\nTOP PROFITABLE (competitive listings) - ROI at est. Alibaba cost / at Temu price:")
    for x in good[:25]:
        print("  ROIw %4.0f%% (+$%-5.2f) ROItemu %4.0f%%  temu $%-6.2f -> amz $%-6.2f fees $%-5.2f offers %-2s rank %-8s match %.2f  %s | %s" % (
            x["roi_wholesale"] * 100, x["profit_wholesale"], x["roi"] * 100, x["temu_price"], x["amz_price"], x["fees"], x["offers"], x.get("sales_rank") or "-", x["match"], ("[%s] " % x["risk_flag"] if x.get("risk_flag") else "") + x["temu_title"][:42], x["amz_title"][:42]))
    print("\nABANDONED LISTINGS (no offers) - price you need on Amazon (at Temu cost / at est. wholesale):")
    for x in sorted(ab, key=lambda x: (x.get("sales_rank") or 9e9))[:20]:
        print("  temu $%-6.2f -> target $%-6.2f / $%-6.2f list $%-6s rank %-8s brand %-12s match %.2f  %s | %s" % (
            x["temu_price"], x["target_price"], x["target_price_wholesale"], x.get("list_price") or "-", x.get("sales_rank") or "-", (x.get("brand") or "-")[:12], x["match"], x["temu_title"][:40], x["amz_title"][:40]))


if __name__ == "__main__":
    main()
