"""Repricing orchestrator.  usage: python run.py [snapshot|shadow|live]
 snapshot : read everything, write state/snapshot.json, decide nothing
 shadow   : decide for every product, write state/decisions.jsonl, change NOTHING          (default)
 live     : like shadow, but applies decisions ONLY if ALL of these hold:
            env REPRICE_LIVE=1  AND  config.json live_enabled=true  AND  sku in allowlist  AND  no kill file  AND  per-run/day caps not exceeded
            every write = re-read price -> VALIDATION_PREVIEW -> PATCH -> re-read -> rollback if the price is not what we sent."""
import copy, datetime as dt, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spapi, engine, amazon_pricing as AP

STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
MK = "ATVPDKIKX0DER"
now = dt.datetime.utcnow()


def log(*a):
    print(*a); sys.stdout.flush()


def jload(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def f(x):
    try:
        v = float(str(x).replace("$", "").replace(",", ""))
        return v if math.isfinite(v) else None
    except Exception:
        return None


def read_tsv(p):
    L = open(p, encoding="utf-8", errors="replace").read().splitlines()
    if not L:
        return []
    h = L[0].split("\t")
    return [dict(zip(h, l.split("\t"))) for l in L[1:]]


def history_stats():
    """per ASIN(sku): sold price percentiles and unit counts from the stored order lines"""
    by = {}
    for fn in sorted(os.listdir(STATE)) if os.path.isdir(STATE) else []:
        if not fn.startswith("orders_"):
            continue
        for r in read_tsv(os.path.join(STATE, fn)):
            if (r.get("order-status") or "").lower().startswith("cancel"):
                continue
            q, p = f(r.get("quantity")), f(r.get("item-price"))
            d = (r.get("purchase-date") or "")[:10]
            if not q or not p or q <= 0:
                continue
            by.setdefault(r.get("sku"), []).append((d, q, p / q))
    return by


def fetch_foep(c, skus, pause=31):
    """Amazon's own 'price that would win the Featured Offer' per sku (batches of 40).  Returns {sku: price}; any failure -> missing (engine ignores it)."""
    out = {}
    skus = sorted(skus)
    for i in range(0, len(skus), 40):
        body = {"requests": [{"uri": "/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", "method": "GET", "marketplaceId": MK, "sku": k} for k in skus[i:i + 40]]}
        try:
            r = spapi.call(c, "POST", "/batches/products/pricing/2022-05-01/offer/featuredOfferExpectedPrice", body=body, quiet=True)
        except Exception as e:
            log("  foep batch failed (%s) - skipped" % str(e)[:80]); continue
        for x in r.get("responses", []):
            try:
                b = x.get("body") or {}
                sku = b.get("sku") or (x.get("request") or {}).get("sku")
                res = (b.get("featuredOfferExpectedPriceResults") or [{}])[0]
                if res.get("resultStatus") == "VALID_FOEP":
                    out[sku] = float(res["featuredOfferExpectedPrice"]["listingPrice"]["amount"])
            except Exception:
                continue
        if i + 40 < len(skus):
            time.sleep(pause)
    return out


def infer_seller(c, costs, plan):
    """own seller id = the FBA offer whose price equals our price on most of our ASINs (cached in state/seller.txt)"""
    p = os.path.join(STATE, "seller.txt")
    if os.path.exists(p) and open(p).read().strip():
        return open(p).read().strip()
    votes, rows = {}, [(r["asin"], f((plan.get(k) or {}).get("your-price"))) for k, r in costs.items()]
    rows = [x for x in rows if x[1]][:40]
    for i in range(0, len(rows), 20):
        chunk = rows[i:i + 20]
        body = {"requests": [{"asin": a, "marketplaceId": MK, "includedData": ["lowestPricedOffers"],
                              "lowestPricedOffersInputs": [{"itemCondition": "New", "offerType": "Consumer"}],
                              "method": "GET", "uri": "/products/pricing/2022-05-01/items/competitiveSummary"} for a, _ in chunk]}
        r = spapi.call(c, "POST", "/batches/products/pricing/2022-05-01/items/competitiveSummary", body=body)
        mine = dict(chunk)
        for x in r.get("responses", []):
            b = x.get("body") or {}
            for lo in b.get("lowestPricedOffers") or []:
                offs = [o for o in lo.get("offers") or [] if o.get("fulfillmentType") == "AFN"]
                if len(offs) == 1 and abs(offs[0]["listingPrice"]["amount"] - mine.get(b.get("asin"), -1)) < 0.005:
                    votes[offs[0]["sellerId"]] = votes.get(offs[0]["sellerId"], 0) + 1
        if i + 20 < len(rows):
            time.sleep(31)
    if votes:
        best = max(votes, key=votes.get)
        open(p, "w").write(best)
        return best
    return ""


def flags_ok(d):
    """automatic raises only when the engine raised no warning about the product"""
    return not (d.get("flags") or [])


def norm_change(x):
    """state record -> engine format {ts(datetime), old, new, dir, base_v}; also reads the first version (from/to/action)"""
    y = dict(x)
    if "old" not in y and "from" in y: y["old"] = y.pop("from")
    if "new" not in y and "to" in y: y["new"] = y.pop("to")
    if "dir" not in y:
        a = y.pop("action", "")
        y["dir"] = "up" if (y.get("new") or 0) > (y.get("old") or 0) else "down"
    y["ts"] = dt.datetime.fromisoformat(x["ts"])
    return y


def listing(c, seller, sku):
    return spapi.call(c, "GET", "/listings/2021-08-01/items/%s/%s" % (seller, sku),
                      params={"marketplaceIds": MK, "includedData": "summaries,attributes,issues"}, quiet=True)


def current_price(item):
    try:
        po = item["attributes"]["purchasable_offer"]
        return float(po[0]["our_price"][0]["schedule"][0]["value_with_tax"]), po
    except Exception:
        return None, None


def set_price(c, seller, sku, new, po_old, ptype):
    po = copy.deepcopy(po_old)
    po[0]["our_price"][0]["schedule"][0]["value_with_tax"] = new
    body = {"productType": ptype, "patches": [{"op": "replace", "path": "/attributes/purchasable_offer", "value": po}]}
    path = "/listings/2021-08-01/items/%s/%s" % (seller, sku)
    v = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK, "mode": "VALIDATION_PREVIEW"}, body=body)
    if v.get("status") not in ("VALID", "ACCEPTED") or v.get("issues"):
        if any(i.get("severity") == "ERROR" for i in v.get("issues", [])) or v.get("status") != "VALID":
            return False, "validation: %s" % json.dumps(v)[:300]
    r = spapi.call(c, "PATCH", path, params={"marketplaceIds": MK}, body=body)
    return r.get("status") in ("ACCEPTED", "VALID"), json.dumps(r)[:300]


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "shadow").lower()
    conf = jload(os.path.join(HERE, "config.json"), {})
    cfg = dict(engine.DEFAULTS); cfg.update(conf.get("cfg") or {})
    c = spapi.load_creds(HERE)
    seller = c.get("SELLER_ID") or c.get("seller_id") or ""
    costs = {r["sku"]: r for r in read_tsv(os.path.join(HERE, "costs.tsv"))}
    killed = os.path.exists(os.path.join(STATE, "KILL")) or os.path.exists(os.path.join(HERE, "KILL"))
    live_ok = (mode == "live" and os.environ.get("REPRICE_LIVE") == "1" and conf.get("live_enabled") is True and not killed)
    log("mode=%s live_writes_allowed=%s killed=%s skus=%d" % (mode, live_ok, killed, len(costs)))

    hist = history_stats()
    sk = jload(os.path.join(STATE, "skustate.json"), {})
    # live Buy Box data
    asins = sorted({r["asin"] for r in costs.values()})
    api = lambda cr, m, p, body=None: spapi.call(cr, m, p, body=body)
    live = AP.fetch(api, c, asins, log)

    txt = spapi.report(c, "GET_FBA_INVENTORY_PLANNING_DATA")[1]
    plan = {}
    L = txt.splitlines()
    if L:
        h = L[0].split("\t")
        for l in L[1:]:
            r = dict(zip(h, l.split("\t"))); plan[r.get("sku")] = r
    foep = fetch_foep(c, [k for k in costs if k in plan])
    log("Amazon target prices (FOEP) read for %d products" % len(foep))
    if plan:
        open(os.path.join(STATE, "planning_latest.tsv"), "w", encoding="utf-8").write(txt)
    if not plan:
        log("no planning data -> stop (nothing decided)"); return 2
    if not seller:
        seller = infer_seller(c, costs, plan)
        log("seller id %s" % ("found" if seller else "NOT found - live price reads/writes disabled"))
    if not seller:
        live_ok = False

    out, changed_run, snaps, raised_run = [], 0, [], 0
    day_key = now.strftime("%Y-%m-%d")
    sk.setdefault("_day", {}); changed_today = sk["_day"].get(day_key, 0)
    for sku, row in sorted(costs.items()):
        asin = row["asin"]
        cost = max(f(row["cost"]) or 0, f(row.get("orig_ws")) or 0) or None      # worst case: never price below what a unit could really have cost
        p = plan.get(sku)
        ov = (conf.get("overrides") or {}).get(sku, {})
        if not p or ov.get("pause"):
            continue
        s = sk.setdefault(sku, {"changes": [], "last_change": None, "frozen_until": None, "last_applied": None})
        fees_total, inv_price = f(row.get("inv_fees")), f(row.get("inv_price"))
        fba = max(0.0, (fees_total - 0.15 * inv_price)) if fees_total and inv_price else None
        if fba is None:
            continue
        try:
            item = listing(c, seller, sku) if seller else {}
        except spapi.SpError as e:
            if e.code == 404:
                continue                      # no such listing (closed / renamed sku): never touch
            raise
        price, po = current_price(item)
        if price is None:
            price = f(p.get("your-price"))
        lv = live.get(asin) or {}
        h = hist.get(sku, [])
        cut = lambda k: sum(q for d, q, _ in h if d >= (now - dt.timedelta(days=k)).strftime("%Y-%m-%d"))
        sold = sorted(pp for _, q, pp in h for _ in range(int(min(q, 5))))
        hh = None
        if len(sold) >= 6:
            hh = {"n": len(sold), "p_low": sold[int(.07 * (len(sold) - 1))], "p_mid": sold[len(sold) // 2], "p_high": sold[int(.95 * (len(sold) - 1))]}
        snap = {"sku": sku, "price": price, "cost": cost, "fba_fee": fba,
                "on_hand": f(p.get("available")) or 0, "inbound": f(p.get("inbound-quantity")) or 0,
                "units_7": f(p.get("units-shipped-t7")) or 0, "units_30": f(p.get("units-shipped-t30")) or 0, "units_90": f(p.get("units-shipped-t90")) or 0,
                "days_since_sale": None, "aged_units": sum(f(p.get("inv-age-" + k)) or 0 for k in ("181-to-270-days", "271-to-365-days", "366-to-455-days", "456-plus-days")),
                "bb": lv.get("bb"), "we_hold_bb": (lv.get("bb") is None) or (price is not None and price <= lv["bb"] * 1.005),
                "low_fba": lv.get("low_afn"), "low_new": lv.get("low_new"), "foep": foep.get(sku), "hist": hh,
                "last_change": s["last_change"] and norm_change(s["last_change"]),
                "changes": [norm_change(x) for x in s["changes"]],
                "frozen_until": s["frozen_until"] and dt.datetime.fromisoformat(s["frozen_until"]),
                "manual_seen": bool(s["last_applied"] and price and abs(price - s["last_applied"]) > 0.005)}
        if h:
            snap["days_since_sale"] = (now.date() - dt.date.fromisoformat(max(d for d, _, _ in h))).days
        # overrides: min/max price
        try:
            d = engine.decide(snap, cfg, now)
        except Exception as e:
            d = {"action": "hold", "reason": "engine error %r - held" % e}
        np_ = d.get("price")
        if np_ is not None:
            if ov.get("min"): np_ = max(np_, float(ov["min"]))
            if ov.get("max"): np_ = min(np_, float(ov["max"]))
            d["price"] = round(np_, 2)
        rec = {"ts": now.isoformat(), "sku": sku, "asin": asin, "price": price, "bb": lv.get("bb"), "action": d["action"], "new": d.get("price"), "reason": d.get("reason"), "flags": d.get("flags"), "applied": False}
        if d.get("freeze_days"):
            s["frozen_until"] = (now + dt.timedelta(days=d["freeze_days"])).isoformat()
        if s["last_applied"] is None or snap["manual_seen"]:
            s["last_applied"] = price
        if d["action"] in ("down", "up", "to_floor", "revert") and d.get("price") and price and abs(d["price"] - price) >= 0.005:
            ar = conf.get("auto_raise") or {}
            is_up = d["action"] == "up"
            allowed = (sku in (conf.get("allowlist") or [])) or (is_up and ar.get("enabled") is True and raised_run < ar.get("max_per_run", 4) and (flags_ok(d)))
            can = live_ok and allowed and po and changed_run < conf.get("max_changes_per_run", 8) and changed_today < conf.get("max_changes_per_day", 20)
            if can:
                ptype = (item.get("summaries") or [{}])[0].get("productType", "PRODUCT")
                try:
                    cur2, _ = current_price(listing(c, seller, sku))
                except spapi.SpError:
                    cur2 = None
                if cur2 is not None and abs(cur2 - price) < 0.005:
                    ok, msg = set_price(c, seller, sku, d["price"], po, ptype)
                    time.sleep(8)
                    chk, _ = current_price(listing(c, seller, sku))
                    if ok and chk is not None and abs(chk - d["price"]) < 0.005:
                        rec["applied"] = True; changed_run += 1; changed_today += 1
                        if is_up: raised_run += 1
                        s["last_applied"] = d["price"]
                        ev = {"ts": now.isoformat(), "old": price, "new": d["price"], "dir": "up" if d["price"] > price else "down", "base_v": d.get("base_v")}
                        s["changes"] = (s["changes"] + [ev])[-30:]; s["last_change"] = ev
                    else:
                        ok2, m2 = set_price(c, seller, sku, price, po, ptype)   # roll back
                        rec["reason"] += " | WRITE NOT CONFIRMED, rolled back (%s)" % ("ok" if ok2 else m2)
                else:
                    rec["reason"] += " | price changed meanwhile - skipped"
            else:
                rec["reason"] += " | SHADOW (not applied)"
        out.append(rec)
        snaps.append([now.strftime("%Y-%m-%d %H:%M"), sku, asin, price, lv.get("bb"), lv.get("low_afn"), lv.get("low_new"), lv.get("n_offers"), foep.get(sku), snap["units_7"], snap["on_hand"]])
    sk["_day"] = {day_key: changed_today}
    json.dump(sk, open(os.path.join(STATE, "skustate.json"), "w"), indent=1, default=str)
    with open(os.path.join(STATE, "decisions.jsonl"), "a") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    sp = os.path.join(STATE, "snapshots.tsv")
    new = not os.path.exists(sp)
    with open(sp, "a") as fh:
        if new: fh.write("time\tsku\tasin\town_price\tbuybox\tlow_fba\tlow_new\tn_offers\tfoep\tunits_7d\ton_hand\n")
        for r in snaps: fh.write("\t".join("" if v is None else str(v) for v in r) + "\n")
    acts = {}
    for r in out:
        acts[r["action"]] = acts.get(r["action"], 0) + 1
    log("decided %d products: %s ; applied this run: %d" % (len(out), acts, changed_run))
    for r in out:
        if r["action"] != "hold":
            log("  %s %s %s -> %s  %s" % (r["sku"], r["action"], r["price"], r["new"], r["reason"][:110]))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
