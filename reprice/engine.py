"""
Pricing engine - PURE functions (no network, no files): the same code is run by the simulations, the tests, the shadow run and the live run.

Goal (owner's words): sell at the highest price that really sells; when a product sits (drought / surplus), step the price down gradually and safely
towards a realistic minimum profit so stock rotates and money can be reinvested; never lose money; never make a mess of the store.

One SKU in -> one decision out:   decide(snap, cfg) -> {"action": hold|down|up|to_floor|revert, "price": new price or None, "reason": text, "flags": [...]}

Safety rules that can never be broken by any input (they are checked by tests.py and by the stress simulation):
  S1  never below the floor (cost + fees + minimum profit; or the history floor), never above the ceiling
  S2  one step is at most STEP_DOWN_MAX / STEP_UP of the price (and at most MAX_DROP_30D / MAX_RISE_30D within 30 days)
  S3  cooldown between two changes of the same SKU; a SKU that changed MAX_CHANGES_14D times in 14 days is frozen
  S4  missing / insane data (no price, no cost, competitor below the floor by a mile, Buy Box far from history) -> HOLD, never guess
  S5  a manual change by the owner is respected (SKU frozen for MANUAL_FREEZE_DAYS)
  S6  no stock -> never lower the price (nothing to sell), and a price below the floor is only ever corrected UPWARDS
"""
import math
from datetime import datetime, timedelta

DEFAULTS = {
    "REF_RATE": 0.15,            # referral fee used to size the floor (conservative: the highest Amazon charges for these categories)
    "MIN_ABS_PROFIT": 0.75,      # $ per unit, never less (normal floor)
    "MIN_ROI": 0.20,             # OWNER 2026-11-04: floor = 20% profit on top of what he pays (cost), after fees
    "SLOW1_DAYS": 90, "SLOW1_ROI": 0.10,   # OWNER: no sale for 90 days -> may go down to 10% profit
    "SLOW2_DAYS": 120, "SLOW2_ROI": 0.05, # ... and to 5% profit; never lower (never lose money)
    "SLOW_MIN_ABS": 0.25,        # $ per unit minimum on the slow tiers
    "HIST_OFF_DAYS": 30,         # the history floor stops protecting the price once a product has not sold for 30 days
    "HIST_MIN_UNITS": 6,         # units needed in the last 365 days before the history is trusted
    "HIST_FLOOR_PCT": 0.07,      # the history floor = this percentile of the unit prices that really sold
    "STEP_DOWN": 0.03,           # normal step down (3% of the price)
    "STEP_DOWN_MAX": 0.04,       # severe drought / aged stock (OWNER: drops very mild and gradual)
    "STEP_UP": 0.05,             # OWNER: raise aggressively, drop gradually
    "STEP_UP_ALONE": 0.08,       # nobody else sells it: big steps (example: 25 -> 39.99), each checked by the 7-day sales test
    "MAX_RISE_30D_ALONE": 0.30,
    "CEIL_MULT_ALONE": 1.60,
    "COOLDOWN_UP_ALONE_H": 72,
    "ZERO_STOCK_FOLLOW": True,
    "MAX_RISE_ZERO_STOCK": 0.60,   # nothing to sell now, so a big move costs no sales: follow the rival box up to this far in 30 days
    "UNDER_BB": 0.03,            # zero stock: raise to this many dollars under the rival Buy Box price
    "RIVAL_WAIT_MAX_DAYS": 10,   # OWNER: wait for a cheap rival's last units to sell - but never longer than this in a row
    "NO_BOX_STEP": 0.12,         # in stock, nobody else sells it, Amazon shows NO Buy Box and our price is above the history ceiling (price suppression): step down this much per change toward the ceiling
    "RIVAL_FLOOD_STEP": 0.05,    # OWNER 2026-11-09: a cheaper rival with a big stock will not run out soon - step toward his price (never below our floor) instead of waiting for him
    "RIVAL_FLOOD_MIN_DOS": 25,   # ... but only with more than this many days of our own stock to move (with scarce stock keep the margin)
    "RIVAL_RAISE_STEP": 0.10,    # OWNER 2026-11-09: the Buy Box owner is nearly sold out - raise decently now so the price is already higher when he is gone
    "RIVAL_RAISE_MAX_ETA": 14,   # ... when he is gone within this many days (or has 3 units or fewer)
    "MIN_STEP": 0.10,            # $ - smaller moves are not worth a price change
    "COOLDOWN_DOWN_H": 48,
    "COOLDOWN_UP_H": 96,
    "MAX_CHANGES_14D": 3,
    "MAX_DROP_30D": 0.20,
    "MAX_RISE_30D": 0.15,
    "MANUAL_FREEZE_DAYS": 5,
    "DROUGHT_MIN_DAYS": 14,      # a product that sells ~1/day is in a drought after 10 days without sale
    "DROUGHT_MULT": 3.0,         # ... one that sells 1/month after 2.5 normal gaps (75 d), capped at DROUGHT_MAX
    "DROUGHT_MAX": 30,           # OWNER: no sale for 30 days -> start lowering (gently)
    "DOS_MIN_DROP": 45,          # a drought only lowers the price when there is more than 30 days of stock to move
    "BIG_GAP": 0.08,             # market at least 8% above our price -> raise in a bigger step
    "STEP_UP_BIG": 0.10,
    "DOS_HIGH": 75,              # days of supply above which stock is a surplus
    "DOS_LOW": 25,               # below this the product sells out soon -> room to raise
    "UP_MIN_UNITS_30": 4,        # evidence needed before raising
    "COMP_GAP_UP": 0.03,         # raise only if the next competitor is at least 3% above us (or alone)
    "PROBE_EVAL_DAYS": 7,
    "PROBE_DROP": 0.60,          # after a raise, if the sales speed falls below 60% of before -> go back
    "PROBE_FREEZE_DAYS": 21,
    "ANOMALY_LOW": 0.50,         # a Buy Box below 50% of the usual price is not followed (could be an error / a troll)
    "ANOMALY_HIGH": 2.00,
    "AGED_UNITS_URGENT": 1,      # units older than 180 days make the drought severe
    "MAX_PRICE_MULT_OVER_HIST": 1.10,   # ceiling = this x the 95th percentile of what really sold
    # ---- MATCH: another seller owns the Buy Box, we are clearly above it, our sales fell AND we hold enough stock to be worth the margin
    "MATCH_ENABLED": False,    # simulated: gain ~0 on the calibrated market (see sim_ab.py) -> kept OFF until real Buy Box data (bbwin.jsonl) proves otherwise
    "MATCH_MIN_GAP": 0.05,       # we are at least 5% above the price that wins
    "MATCH_MIN_DOS": 30,         # days of supply needed: with scarce stock it is better to keep the margin than to sell the last units cheap
    "MATCH_MIN_STOCK": 4,
    "MATCH_UNDERPERF": 0.70,     # 30-day sales speed below 70% of the 90-day speed
    "MATCH_MIN_U90": 4,          # the product must have a real sales history
}


def cfg_with(over=None):
    c = dict(DEFAULTS)
    c.update(over or {})
    return c


def _r2(x):
    return round(x + 1e-9, 2)


def _f(x, d=None):
    try:
        if x is None or x == "":
            return d
        v = float(x)
        return d if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return d


def _roi_for(snap, cfg):
    """profit rate the floor protects: 20% normally; 10% / 5% only for stock that has not sold for 90 / 120 days"""
    dss = _f(snap.get("days_since_sale"))
    on_hand = _f(snap.get("on_hand"), 0.0)
    if dss is not None and on_hand > 0:
        if dss >= cfg["SLOW2_DAYS"]:
            return cfg["SLOW2_ROI"], cfg["SLOW_MIN_ABS"]
        if dss >= cfg["SLOW1_DAYS"]:
            return cfg["SLOW1_ROI"], cfg["SLOW_MIN_ABS"]
    return cfg["MIN_ROI"], cfg["MIN_ABS_PROFIT"]


def _price_for_profit(cost, fba, fixed, prof, r):
    return (cost + fba + fixed + prof) / (1.0 - r)


def floors(snap, cfg, with_hist=True):
    """(hard_floor, floor, ceiling).
       hard_floor = the lowest price ever allowed = cost + fees + the slowest-tier profit (5%): never lose money, any price below it is lifted.
       floor      = cost + fees + 20% of cost (10% / 5% for stock unsold 90 / 120 days); the history floor (7th percentile of past sold prices) also
                    protects the price, but only while the product still sells (not after HIST_OFF_DAYS without a sale)."""
    cost = _f(snap.get("cost"))
    if not cost or cost <= 0:
        return None, None, None
    fba = _f(snap.get("fba_fee"), 0.0)
    fixed = _f(snap.get("fee_fixed"), 0.0)            # closing fees etc.
    r = cfg["REF_RATE"]
    hard = _price_for_profit(cost, fba, fixed, max(cfg["SLOW_MIN_ABS"], cfg["SLOW2_ROI"] * cost), r)
    roi, ab = _roi_for(snap, cfg)
    normal = _price_for_profit(cost, fba, fixed, max(ab, roi * cost), r)
    normal = max(normal, hard)
    hist_floor = None
    hp = snap.get("hist") or {}
    dss = _f(snap.get("days_since_sale"))
    if with_hist and hp.get("n", 0) >= cfg["HIST_MIN_UNITS"] and _f(hp.get("p_low")) and not (dss is not None and dss >= cfg["HIST_OFF_DAYS"] and _f(snap.get("on_hand"), 0.0) > 0):
        hist_floor = hp["p_low"]
    floor = max(normal, hist_floor) if hist_floor else normal
    ceil = None
    if hp.get("n", 0) >= cfg["HIST_MIN_UNITS"] and _f(hp.get("p_high")):
        ceil = hp["p_high"] * cfg["MAX_PRICE_MULT_OVER_HIST"]
    return _r2(hard), _r2(floor), (_r2(ceil) if ceil else None)


def _hours_since(ts, now):
    if not ts:
        return 1e9
    return (now - ts).total_seconds() / 3600.0


def _count_changes(changes, now, days):
    return sum(1 for c in changes or [] if (now - c["ts"]) <= timedelta(days=days))


def decide(snap, cfg=None, now=None):
    """snap keys (all optional except sku, price):
         sku, price (own current price), cost, fba_fee, fee_fixed,
         on_hand, inbound, units_7, units_30, units_90, in_stock_days_30, in_stock_days_7, days_since_sale, aged_units (181+ days),
         bb (Buy Box price), we_hold_bb (bool/None), low_fba (cheapest OTHER FBA offer), low_new, foep (price that would win the Buy Box), n_offers,
         hist {n, p_low, p_mid, p_high}, last_change {ts, old, new, dir, base_v}, changes [ {ts, old, new} ... ], frozen_until, manual_seen (bool)
    """
    cfg = cfg or DEFAULTS
    now = now or datetime.utcnow()
    flags = []
    price = _f(snap.get("price"))

    def hold(reason, **kw):
        d = {"action": "hold", "price": None, "reason": reason, "flags": flags}
        d.update(kw)
        return d

    if not price or price <= 0:
        return hold("no current price")
    safety, floor, ceil = floors(snap, cfg)
    if floor is None:
        return hold("no cost known for this product (cannot protect the profit)")
    on_hand = _f(snap.get("on_hand"), 0.0)
    inbound = _f(snap.get("inbound"), 0.0)
    if snap.get("frozen_until") and snap["frozen_until"] > now:
        return hold("frozen until %s (%s)" % (snap["frozen_until"].strftime("%Y-%m-%d"), snap.get("frozen_why", "")), floor=floor, ceil=ceil)
    if snap.get("manual_seen"):
        return hold("price was changed by hand - respected", floor=floor, ceil=ceil, freeze_days=cfg["MANUAL_FREEZE_DAYS"], freeze_why="manual change")

    # ---- S6 / S1: a price below the safety floor is corrected upwards, whatever else is going on
    if price < safety - 0.005:
        return {"action": "to_floor", "price": _r2(safety),
                "reason": "price %.2f is below the minimum-profit floor %.2f" % (price, safety), "flags": ["below_floor"]}

    changes = snap.get("changes") or []
    lc = snap.get("last_change")
    n14 = _count_changes(changes, now, 14)
    since_last_h = _hours_since(lc["ts"] if lc else None, now)

    # ---- sales speed
    u30, u7, u90 = _f(snap.get("units_30"), 0.0), _f(snap.get("units_7"), 0.0), _f(snap.get("units_90"), 0.0)
    isd30 = max(1.0, _f(snap.get("in_stock_days_30"), 30.0) or 30.0)
    isd7 = max(1.0, _f(snap.get("in_stock_days_7"), 7.0) or 7.0)
    v30 = u30 / isd30
    v7 = u7 / isd7
    v90 = u90 / 90.0
    v = v30 if u30 > 0 else v90
    dos = (on_hand / v) if v > 0 else (999.0 if on_hand > 0 else 0.0)
    dss = _f(snap.get("days_since_sale"))
    if dss is None:
        dss = 0.0 if u7 > 0 else (7.0 if u30 > 0 else 60.0)
    gap = (1.0 / v) if v > 0 else 60.0
    drought_after = min(cfg["DROUGHT_MAX"], max(cfg["DROUGHT_MIN_DAYS"], cfg["DROUGHT_MULT"] * gap))
    aged = _f(snap.get("aged_units"), 0.0)
    in_drought = on_hand > 0 and dss >= drought_after and dos > cfg["DOS_MIN_DROP"]
    surplus = on_hand > 0 and dos > cfg["DOS_HIGH"]
    severe = on_hand > 0 and (dss >= 2 * drought_after or (aged >= cfg["AGED_UNITS_URGENT"] and (in_drought or surplus)))

    # ---- market facts, with sanity checks (S4)
    bb, low_fba, foep = _f(snap.get("bb")), _f(snap.get("low_fba")), _f(snap.get("foep"))
    ref = (snap.get("hist") or {}).get("p_mid") or price
    anomalous = False
    for nm, val in (("bb", bb), ("low_fba", low_fba), ("foep", foep)):
        if val and (val < ref * cfg["ANOMALY_LOW"] or val > ref * cfg["ANOMALY_HIGH"]):
            flags.append("anomalous_" + nm)
            anomalous = True
            if nm == "bb": bb = None
            if nm == "low_fba": low_fba = None
            if nm == "foep": foep = None
    we_hold = snap.get("we_hold_bb")

    # ---- probe evaluation: a raise that made the sales speed collapse is undone
    if lc and lc.get("dir") == "up" and lc.get("base_v") is not None and since_last_h >= cfg["PROBE_EVAL_DAYS"] * 24 and since_last_h < 21 * 24:
        if on_hand > 0 and v7 < cfg["PROBE_DROP"] * lc["base_v"] and lc["base_v"] > 0.05:
            back = max(lc["old"], safety)
            if back < price - 0.005:
                return {"action": "revert", "price": _r2(back), "reason": "after the raise to %.2f the sales speed fell to %.0f%% of before - back to %.2f" % (
                    price, 100 * v7 / lc["base_v"], back), "flags": ["probe_failed"], "freeze_days": cfg["PROBE_FREEZE_DAYS"], "freeze_why": "failed price test"}

    # ---- S3 frozen by too many changes
    if n14 >= cfg["MAX_CHANGES_14D"]:
        return hold("already changed %d times in 14 days - resting" % n14, floor=floor, ceil=ceil)

    # =============================================================== DOWN
    if on_hand > 0 and (in_drought or surplus):
        if since_last_h < cfg["COOLDOWN_DOWN_H"]:
            return hold("waiting after the last change (%.0f h of %d h)" % (since_last_h, cfg["COOLDOWN_DOWN_H"]), floor=floor, ceil=ceil)
        if snap.get("rival_wait") and dss < cfg["SLOW1_DAYS"]:        # the Buy Box owner is nearly sold out: his box (and his low price) disappears by itself - keep our margin
            rw = snap["rival_wait"]
            return hold("waiting for the Buy Box owner's last units (%s)" % (rw.get("why") or "few left"), floor=floor, ceil=ceil)
        deep = severe
        lowest_allowed = floors(snap, cfg, with_hist=False)[1] if deep else floor      # severe cases may cross the history floor, never the profit floor of their tier
        if price <= lowest_allowed + 0.005:
            flags.append("at_floor")
            return hold("at the minimum-profit floor %.2f while stock sits (%s) - consider removal / bundle" % (lowest_allowed, "severe" if deep else "drought"), floor=floor, ceil=ceil, alert="stuck_at_floor")
        step = cfg["STEP_DOWN_MAX"] if severe else cfg["STEP_DOWN"]
        step_amt = max(cfg["MIN_STEP"], price * step)
        target = price - step_amt
        why = "%s: %s%.0f days without sale (limit %.0f), %.0f days of supply" % ("severe" if severe else "drought/surplus", "", dss, drought_after, min(dos, 999))
        # the market tells where the price that moves the product is: the price that wins the Buy Box, or the cheapest FBA competitor
        market_target = None
        if foep and foep < price - cfg["MIN_STEP"]:
            market_target = foep
        elif low_fba and low_fba < price - cfg["MIN_STEP"]:
            market_target = low_fba
        if market_target and market_target >= lowest_allowed:
            target = max(market_target, price - step_amt)      # towards the market, but never more than one step
            why += "; market price %.2f" % market_target
        target = max(target, lowest_allowed)
        # S2: 30 day budget - the price may not fall more than MAX_DROP_30D below the highest price of the last 30 days
        c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
        top30 = max([price] + [c["old"] for c in c30] + [c["new"] for c in c30])
        target = max(target, top30 * (1 - cfg["MAX_DROP_30D"] * (1.5 if deep else 1.0)))
        target = _r2(target)
        if target >= price - 0.005 or price - target < min(cfg["MIN_STEP"], 0.02 * price):
            return hold("no room to lower further within the limits", floor=floor, ceil=ceil)
        return {"action": "down", "price": target, "reason": why, "flags": flags + (["severe"] if severe else []), "floor": floor, "ceil": ceil, "severe": bool(severe), "dss": dss, "dos": dos, "rival_flood": bool(snap.get("rival_flood")),
                "impact": round(on_hand * (_f(snap.get("cost"), 0.0) or 0.0) * (2.0 if severe else 1.0), 2)}

    # =============================================================== MATCH (win the Buy Box back, only when it pays)
    if cfg.get("MATCH_ENABLED") and on_hand >= cfg["MATCH_MIN_STOCK"] and not anomalous and not (in_drought or surplus) and we_hold is False:
        wtype = snap.get("bb_type")
        ref = None
        if wtype == "M":                       # a merchant-fulfilled winner mostly takes non-Prime shoppers: Prime customers compare us with the FBA offers
            ref = low_fba
        elif bb:
            ref = bb
        if ref and price > ref * (1 + cfg["MATCH_MIN_GAP"]) and u90 >= cfg["MATCH_MIN_U90"] and v90 > 0 and v30 < cfg["MATCH_UNDERPERF"] * v90 \
                and dos >= cfg["MATCH_MIN_DOS"]:
            if since_last_h < cfg["COOLDOWN_DOWN_H"]:
                return hold("waiting after the last change (%.0f h of %d h)" % (since_last_h, cfg["COOLDOWN_DOWN_H"]), floor=floor, ceil=ceil)
            if price <= floor + 0.005:
                return hold("above the winner (%.2f) but already at the minimum-profit floor %.2f" % (ref, floor), floor=floor, ceil=ceil, alert="stuck_at_floor")
            step_amt = max(cfg["MIN_STEP"], price * cfg["STEP_DOWN"])
            target = max(ref, price - step_amt, floor)
            c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
            top30 = max([price] + [c["old"] for c in c30] + [c["new"] for c in c30])
            target = _r2(max(target, top30 * (1 - cfg["MAX_DROP_30D"])))
            if target < price - 0.005 and price - target >= min(cfg["MIN_STEP"], 0.02 * price):
                return {"action": "down", "price": target, "match": True,
                        "reason": "Buy Box owned by another %s seller at %.2f, we are %.0f%% above, sales at %.0f%% of the 90-day speed, %.0f days of supply: step toward it" % (
                            "FBM" if wtype == "M" else "FBA", ref, 100 * (price / ref - 1), 100 * v30 / v90, min(dos, 999)),
                        "flags": flags + ["match"], "floor": floor, "ceil": ceil, "severe": False, "dss": dss, "dos": dos}

    # =============================================================== ZERO STOCK: price follows the rival Buy Box, so the next units sell high
    # OWNER 2026-11-04: "if there's zero available, but the prices on the buy box are higher, raise the price close to the buy box prices, or a little bit under"
    if cfg.get("ZERO_STOCK_FOLLOW", True) and on_hand <= 0 and u90 >= 1 and bb and not anomalous and bb > price + cfg["MIN_STEP"]:
        if since_last_h >= cfg["COOLDOWN_UP_H"]:
            target = bb - cfg["UNDER_BB"]
            if ceil:
                target = min(target, ceil * cfg["CEIL_MULT_ALONE"])
            c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
            base_ = min([price] + [c["old"] for c in c30])
            target = _r2(min(target, base_ * (1 + cfg["MAX_RISE_ZERO_STOCK"])))
            if target >= price + cfg["MIN_STEP"] - 1e-9:
                return {"action": "up", "price": target, "reason": "no stock, rival Buy Box at %.2f: price follows it (%.2f) so the next units sell higher" % (bb, target),
                        "flags": flags, "base_v": None, "floor": floor, "ceil": ceil, "zero_stock": True, "impact": round(max(u90 / 3.0, 1.0) * (target - price), 2)}

    # OWNER 2026-11-09 (no stacked raises): after a raise, the next raise waits until something sold at the new price
    unsold_raise = bool(lc and lc.get("dir") == "up" and since_last_h < 1e8 and dss * 24 >= since_last_h)

    # =============================================================== RIVAL NEARLY SOLD OUT: raise decently now, so the price is already up when he is gone
    rw = snap.get("rival_wait")
    if rw and on_hand > 0 and not anomalous and not (in_drought or surplus):
        eta_, left_ = _f(rw.get("eta")), _f(rw.get("left"))
        soon = (eta_ is not None and eta_ <= cfg["RIVAL_RAISE_MAX_ETA"]) or (left_ is not None and left_ <= 3)
        if soon and since_last_h >= cfg["COOLDOWN_UP_H"] and not unsold_raise:
            np_ = _f(rw.get("next_price"))                 # cheapest other seller above the owner: never go above him (he would take the Buy Box when the owner is gone)
            target = price * (1 + cfg["RIVAL_RAISE_STEP"])
            if np_ and np_ > price:
                target = min(target, np_ - 0.01)
            if ceil:
                target = min(target, ceil)
            c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
            if c30:
                target = min(target, min(c["old"] for c in c30) * (1 + cfg["MAX_RISE_30D"]))
            target = _r2(target)
            if target >= price + cfg["MIN_STEP"] - 1e-9:
                return {"action": "up", "price": target, "reason": "Buy Box owner nearly sold out (%s): raise ahead of it to %.2f%s" % (rw.get("why") or "few left", target, (", below the next seller at %.2f" % np_) if np_ else ""),
                        "flags": flags + ["rival_low"], "base_v": v, "floor": floor, "ceil": ceil, "rival_raise": True,
                        "impact": round(max(v, v90, 0.05) * 30 * (target - price), 2)}

    # =============================================================== RIVAL WITH A BIG STOCK AND A LOWER PRICE: step toward him, never below the floor
    rf = snap.get("rival_flood")
    if rf and on_hand > 0 and not anomalous and not (in_drought or surplus) and dos >= cfg["RIVAL_FLOOD_MIN_DOS"] and we_hold is not True:
        if since_last_h < cfg["COOLDOWN_DOWN_H"]:
            return hold("waiting after the last change (%.0f h of %d h)" % (since_last_h, cfg["COOLDOWN_DOWN_H"]), floor=floor, ceil=ceil)
        if price <= floor + 0.005:
            return hold("rival with a big stock is cheaper but we are at the minimum-profit floor %.2f" % floor, floor=floor, ceil=ceil, alert="stuck_at_floor")
        rp = _f(rf.get("price"))
        step_amt = max(cfg["MIN_STEP"], price * cfg["RIVAL_FLOOD_STEP"])
        target = max(price - step_amt, floor)
        if rp and rp < price:
            target = max(target, rp)
        c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
        top30 = max([price] + [c["old"] for c in c30] + [c["new"] for c in c30])
        target = _r2(max(target, top30 * (1 - cfg["MAX_DROP_30D"])))
        if target < price - 0.005 and price - target >= min(cfg["MIN_STEP"], 0.02 * price):
            return {"action": "down", "price": target, "reason": "rival Buy Box owner is cheaper and has a big stock (%s): step toward his price %s, %.0f days of our supply" % (rf.get("why") or "plenty", ("%.2f" % rp) if rp else "", min(dos, 999)),
                    "flags": flags + ["rival_flood"], "floor": floor, "ceil": ceil, "severe": False, "dss": dss, "dos": dos, "rival_flood": True,
                    "impact": round(on_hand * (_f(snap.get("cost"), 0.0) or 0.0), 2)}

    # =============================================================== UP
    if (on_hand > 0 or inbound > 0) and u30 >= cfg["UP_MIN_UNITS_30"] and not in_drought and not surplus and not anomalous:
        if since_last_h < cfg["COOLDOWN_UP_H"]:
            return hold("waiting after the last change", floor=floor, ceil=ceil)
        if unsold_raise:
            return hold("the last raise to %.2f has not sold yet - waiting for a sale before the next step" % price, floor=floor, ceil=ceil)
        room_ok = False
        target = None
        comp = low_fba or None
        n_riv = snap.get("n_rivals")                   # sellers other than us with a New offer (Amazon offers list + the web page); None = unknown
        alone = (n_riv is not None and n_riv == 0)
        if alone:
            comp = None
        if bb and we_hold is False and not alone:
            return hold("another seller owns the Buy Box - no raise", floor=floor, ceil=ceil)
        if alone and dos > 0:                           # nobody else sells it: raise hard, the 7-day sales test undoes a mistake
            if since_last_h < cfg["COOLDOWN_UP_ALONE_H"]:
                return hold("waiting after the last change", floor=floor, ceil=ceil)
            target = price * (1 + cfg["STEP_UP_ALONE"])
            room_ok = True
        elif dos <= cfg["DOS_LOW"]:                       # sells out soon: stop giving margin away
            step = cfg["STEP_UP"]
            ref = min([x for x in (foep, bb, low_fba) if x] or [0])
            if ref and ref >= price * (1 + cfg["BIG_GAP"]):      # the market (Amazon's own target price / Buy Box / cheapest rival) is well above us: bigger step
                step = cfg["STEP_UP_BIG"]
            target = price * (1 + step)
            if foep and foep > price:                           # Amazon's own estimate of the winning price is a ceiling for the raise
                target = min(target, foep)
            room_ok = True
        elif v >= 0.15 and dos <= cfg["DOS_HIGH"] / 2:  # healthy seller with a normal stock: test a higher price
            target = price * (1 + cfg["STEP_UP"] * 0.7)
            room_ok = True
        if room_ok:
            top = ceil
            if comp:                                    # never above the next competitor (we would lose the Buy Box)
                if comp < price * (1 + cfg["COMP_GAP_UP"]):
                    return hold("competitor too close above - no raise", floor=floor, ceil=ceil)
                target = min(target, comp - 0.01)
            if top:
                target = min(target, top * (cfg["CEIL_MULT_ALONE"] if alone else 1.0))
            c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
            if c30:
                base = min(c["old"] for c in c30)
                target = min(target, base * (1 + (cfg["MAX_RISE_30D_ALONE"] if alone else cfg["MAX_RISE_30D"])))
            target = _r2(target)
            if target >= price + cfg["MIN_STEP"] - 1e-9:
                return {"action": "up", "price": target, "reason": ("alone on the listing, sells %.2f/day: test %.2f" % (v, target)) if alone else "sells well (%.2f/day, %.0f days of supply, Buy Box held): test %.2f" % (v, min(dos, 999), target),
                        "flags": flags, "base_v": v, "floor": floor, "ceil": ceil, "alone": bool(alone), "impact": round(max(v, v90) * 30 * (target - price), 2)}
    if price > (ceil or 1e9) + 0.005 and snap.get("no_box") and on_hand > 0 and not anomalous:
        # Amazon shows no Buy Box at all (we are the only offer and the price is far above what ever sold): units can't sell. Step toward the ceiling, never below the profit floor.
        if since_last_h < cfg["COOLDOWN_DOWN_H"]:
            return hold("no Buy Box at %.2f (above the %.2f ceiling) - waiting after the last change (%.0f h of %d h)" % (price, ceil, since_last_h, cfg["COOLDOWN_DOWN_H"]), floor=floor, ceil=ceil)
        target = _r2(max(price * (1 - cfg["NO_BOX_STEP"]), ceil, floor))
        if target < price - 0.005:
            return {"action": "down", "price": target, "reason": "no Buy Box shown (only offer, price %.2f is above the %.2f ceiling): step toward the ceiling so the stock can sell" % (price, ceil),
                    "flags": flags + ["no_box"], "floor": floor, "ceil": ceil, "severe": False, "dss": dss, "dos": dos, "no_box": True,
                    "impact": round(on_hand * (_f(snap.get("cost"), 0.0) or 0.0) * 2.0, 2)}
    if price > (ceil or 1e9) + 0.005:
        return hold("price above the ceiling %.2f (history) - watch" % ceil, floor=floor, ceil=ceil, alert="above_ceiling")
    return hold("steady (%.2f/day, %.0f days of supply, last sale %.0f d ago)" % (v, min(dos, 999), dss), floor=floor, ceil=ceil)


def realistic_profit(price, cost, fba_fee, ref_rate=0.15, fee_fixed=0.0):
    """profit per unit at a price (conservative referral)"""
    return price - cost - fba_fee - fee_fixed - ref_rate * price
