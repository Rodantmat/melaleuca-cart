"""Deal sheet: deep, realistic dossier for the best candidates already stored in the private Postgres (schema deals).
Per product: every competing listing (price, rank, est. monthly sales, reviews, rating, sellers, size/weight), real Amazon fees at OUR price,
a full landed-cost model (duty, freight, inbound, label, storage, returns), and three sales scenarios with ads and a 12-month cash curve.
Read-only on Amazon. Results go ONLY to Postgres (table deals.dealsheet) - the public log gets counts only.
Env: DATABASE_URL, APIFY_TOKEN (optional), TOP (default 12), REFS (optional space-separated reference ASINs), UNDERCUT (default 0.15).
"""
import json, math, os, sys, statistics, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
sys.path.insert(0, HERE)
import psycopg, spapi, deal_finder as df, validate as va

UNDERCUT = float(os.environ.get("UNDERCUT", "0.15"))
TOP = int(os.environ.get("TOP", "12"))
# ---- cost assumptions (all printed into the dossier so they can be challenged) ----
A = {
    "wholesale_factor_ali": 0.85,   # factory (Alibaba) price vs the AliExpress shown sale price; confirm with a real quote
    "duty_pct": 0.25,               # US tariff + duty on China-made goods, % of factory price (varies by HTS code - confirm)
    "freight_per_lb": 0.45, "freight_min": 0.50,     # sea/LCL freight per unit
    "inbound_fixed": 0.40, "inbound_per_lb": 0.20,   # FBA inbound placement fee + shipping to the warehouse
    "label_pack": 0.60,             # own-brand label, polybag, FNSKU label
    "storage_rate_cuft_month": 1.20,  # blend of $0.78 (Jan-Sep) and $2.40 (Oct-Dec) standard size
    "months_on_shelf": 1.5,
    "return_rate": 0.06,            # Home & Kitchen 4-8%
    "unsellable_share": 0.25,       # of returned units cannot be resold
    "one_time": 80.0,               # sample order, listing photos, GTIN exemption paperwork
    "unit_cap": 300,                # a new seller never assumed above this per month
}
SCEN = {  # share of the whole market a brand-new own listing wins: months 1-3 / 4-6 / 7-12
    "conservative": (0.015, 0.03, 0.05),
    "base":         (0.03, 0.06, 0.10),
    "optimistic":   (0.05, 0.10, 0.15),
}
ACOS = (0.40, 0.25, 0.15)  # ad spend as % of revenue in months 1-3 / 4-6 / 7-12


def to_lb(v):
    try:
        x, u = float(v["value"]), (v.get("unit") or "").lower()
    except Exception:
        return None
    return x / 16 if u.startswith("ounce") else x * 2.2046 if u.startswith("kilo") else x / 453.6 if u.startswith("gram") else x


def to_in(v):
    try:
        x, u = float(v["value"]), (v.get("unit") or "").lower()
    except Exception:
        return None
    return x / 2.54 if u.startswith("cent") else x / 25.4 if u.startswith("milli") else x * 12 if u.startswith("feet") else x


def catalog_one(c, asin):
    try:
        r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + asin, params={"marketplaceIds": df.MK, "includedData": "summaries,salesRanks,attributes,dimensions"}, quiet=True, tries=4)
    except Exception as e:
        print("  catalog ERR", str(e)[:80]); return None
    p = df._parse_item(r)
    d = (r.get("dimensions") or [{}])[0]
    box = d.get("package") or d.get("item") or {}
    L, W, H = (to_in(box.get(k)) for k in ("length", "width", "height"))
    p["weight_lb"] = to_lb(box.get("weight") or {})
    p["cuft"] = round(L * W * H / 1728, 3) if L and W and H else None
    p["dims_in"] = [round(x, 1) for x in (L, W, H)] if L and W and H else None
    time.sleep(0.6)
    return p


def pick(cx):
    refs = (os.environ.get("REFS") or "").split()
    if refs:
        q = "select distinct on (ref_asin) ref_asin, row from deals.markets where ref_asin = any(%s) order by ref_asin, run_id desc"
        return cx.execute(q, (refs,)).fetchall()
    q = """select ref_asin, row from (select distinct on (ref_asin) ref_asin, row, (row->>'u20_profit_month')::numeric pm
             from deals.markets where row->>'fees_src'='spapi' and (row->>'u20_roi')::numeric >= 0.30 and row->>'verdict' in ('GO','WATCH')
             order by ref_asin, (row->>'u20_profit_month')::numeric desc) t order by pm desc limit %s"""
    return cx.execute(q, (TOP,)).fetchall()


def model(P, fee_total, src_unit, weight_lb, cuft, market_units):
    ref_fee = round(0.15 * P, 2)
    fba = round(max(fee_total - ref_fee, 0), 2)
    fob = round(src_unit * A["wholesale_factor_ali"], 2)
    duty = round(fob * A["duty_pct"], 2)
    w = weight_lb or 1.0
    freight = round(max(A["freight_min"], A["freight_per_lb"] * w), 2)
    inbound = round(A["inbound_fixed"] + A["inbound_per_lb"] * w, 2)
    landed = round(fob + duty + freight + inbound + A["label_pack"], 2)
    storage = round((cuft or 0.25) * A["storage_rate_cuft_month"] * A["months_on_shelf"], 2)
    returns = round(A["return_rate"] * (2 * fba + 0.2 * ref_fee + A["unsellable_share"] * landed), 2)
    unit_before_ads = round(P - fee_total - landed - storage - returns, 2)
    out = {"our_price": P, "referral_fee": ref_fee, "fba_fee": fba, "fees_total": round(fee_total, 2), "factory_price": fob, "duty": duty, "freight": freight,
           "inbound": inbound, "label_pack": A["label_pack"], "landed_cost": landed, "storage_per_unit": storage, "returns_per_unit": returns,
           "profit_unit_before_ads": unit_before_ads, "scenarios": {}}
    for name, shares in SCEN.items():
        cum, months, peak_units = -A["one_time"], [], []
        for m in range(12):
            ph = 0 if m < 3 else 1 if m < 6 else 2
            u = min(A["unit_cap"], market_units * shares[ph]) if market_units else 0
            ads = ACOS[ph] * P * u
            profit = u * unit_before_ads - ads
            cum += profit
            months.append({"m": m + 1, "units": round(u), "profit": round(profit)})
        first3_units = sum(x["units"] for x in months[:3])
        ads3 = sum(ACOS[0] * P * x["units"] for x in months[:3])
        capital = round(first3_units * landed + ads3 + A["one_time"])
        be = next((i + 1 for i in range(12) if -A["one_time"] + sum(x["profit"] for x in months[:i + 1]) >= 0), None)
        tot = sum(x["profit"] for x in months)
        out["scenarios"][name] = {"units_m1_3": months[0]["units"], "units_m4_6": months[3]["units"], "units_m7_12": months[6]["units"],
                                  "profit_m1_3": months[0]["profit"], "profit_m4_6": months[3]["profit"], "profit_m7_12": months[6]["profit"],
                                  "profit_12m_after_setup": round(tot - A["one_time"]), "capital_at_risk": capital, "breakeven_month": be,
                                  "roi_12m_on_capital": round((tot - A["one_time"]) / capital, 2) if capital else None}
    return out


def main():
    url = os.environ.get("DATABASE_URL")
    cx = psycopg.connect(url, autocommit=True)
    cx.execute("""create table if not exists deals.dealsheet (id bigserial primary key, run_at timestamptz default now(), ref_asin text, kw text, data jsonb)""")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    rows = pick(cx)
    print("dealsheet: %d candidates picked" % len(rows))
    n = 0
    for ref, r in rows:
        asins = (r.get("asins") or ref).split()
        if ref not in asins:
            asins.insert(0, ref)
        asins = asins[:8]
        cat = {a: catalog_one(c, a) for a in asins}
        cat = {a: v for a, v in cat.items() if v}
        offers = df.offers_batch(c, list(cat))
        revs = va.review_info(list(cat))
        comps = []
        for a, p in cat.items():
            o = offers.get(a) or {}
            price = o.get("bb") or o.get("low") or p.get("list_price")
            units = df.est_monthly_sales(p.get("rank"), p.get("rank_cat"))
            rv = revs.get(a) or {}
            comps.append({"asin": a, "title": (p["title"] or "")[:90], "brand": p.get("brand"), "price": price, "rank": p.get("rank"), "rank_cat": p.get("rank_cat"),
                          "est_units_month": units, "reviews": rv.get("reviews"), "rating": rv.get("rating"), "sellers": o.get("total"), "fba_sellers": o.get("fba"),
                          "amazon_sells": o.get("amazon_sells"), "weight_lb": p.get("weight_lb"), "dims_in": p.get("dims_in")})
        prices = [x["price"] for x in comps if x["price"]]
        if not prices:
            continue
        med = statistics.median(prices)
        P = round(med * (1 - UNDERCUT) - 0.01, 2)
        fees = df.fees_batch(c, [(ref, P)])
        fee_total = fees.get("%s@%.2f" % (ref, P))
        fees_src = "spapi" if fee_total is not None else "guess"
        if fee_total is None:
            fee_total = df.fee_guess(P)
        refc = next((x for x in comps if x["asin"] == ref), comps[0])
        market_units = sum(x["est_units_month"] or 0 for x in comps)
        src_unit = (r.get("temu_price") or 0) * (r.get("pack_ratio") or 1)
        mdl = model(P, fee_total, src_unit, refc.get("weight_lb"), (cat.get(ref) or {}).get("cuft"), market_units)
        gated = va.restricted(c, ref)
        known_rev = [x["reviews"] for x in comps if x["reviews"] is not None]
        ests = [x["est_units_month"] for x in comps if x["est_units_month"]]
        top = max(comps, key=lambda x: x["est_units_month"] or 0)
        flags = []
        if fees_src != "spapi": flags.append("fees are a guess")
        if len(known_rev) < len(comps): flags.append("reviews known for %d of %d competitors" % (len(known_rev), len(comps)))
        if known_rev and max(known_rev) > 3000: flags.append("entrenched leader: %d reviews" % max(known_rev))
        if market_units and top.get("est_units_month") and top["est_units_month"] / market_units > 0.6: flags.append("one listing holds %d%% of market sales" % round(100 * top["est_units_month"] / market_units))
        if any(x["amazon_sells"] for x in comps): flags.append("Amazon itself sells")
        if gated: flags.append("competitor ASIN gated - must create own listing")
        if mdl["fba_fee"] > 8: flags.append("bulky/heavy: high FBA fee, check size tier & storage")
        if r.get("risk_flag"): flags.append("risk keyword: %s" % r["risk_flag"])
        if (r.get("pack_ratio") or 1) not in (1, 1.0): flags.append("pack mismatch: need %s source units per Amazon pack" % r.get("pack_ratio"))
        if not (cat.get(ref) or {}).get("cuft"): flags.append("no dimensions in catalog: storage/freight estimated")
        flags.append("source price is the AliExpress sale/minimum-variant price: get a real factory quote incl. MOQ")
        conf = "HIGH" if fees_src == "spapi" and len(known_rev) == len(comps) and market_units and not r.get("risk_flag") else "MEDIUM" if fees_src == "spapi" else "LOW"
        data = {"product": r.get("temu_title"), "kw": r.get("kw"), "source_url": r.get("temu_url"), "source_orders_sold": r.get("source_sold"), "source_rating": r.get("source_rating"),
                "source_price_shown": r.get("temu_price"), "pack_ratio": r.get("pack_ratio"), "ref_asin": ref, "ref_url": "https://www.amazon.com/dp/" + ref,
                "competitors": comps, "n_listings": len(comps), "n_sellers_total": sum(x["sellers"] or 0 for x in comps),
                "avg_competitor_price": round(statistics.mean(prices), 2), "median_competitor_price": round(med, 2),
                "avg_reviews": round(statistics.mean(known_rev)) if known_rev else None, "max_reviews": max(known_rev) if known_rev else None,
                "avg_rating": round(statistics.mean([x["rating"] for x in comps if x["rating"]]), 2) if any(x["rating"] for x in comps) else None,
                "avg_units_per_listing": round(statistics.mean(ests)) if ests else None, "market_units_month": market_units,
                "fees_src": fees_src, "gated": gated, "model": mdl, "assumptions": A, "scenario_shares": SCEN, "acos_by_phase": ACOS, "confidence": conf, "flags": flags,
                "undercut": UNDERCUT}
        cx.execute("insert into deals.dealsheet(ref_asin, kw, data) values (%s,%s,%s)", (ref, r.get("kw"), json.dumps(data, default=str)))
        n += 1
    print("dealsheet: %d dossiers stored in private Postgres" % n)


if __name__ == "__main__":
    main()
