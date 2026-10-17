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
    "MIN_ABS_PROFIT": 0.75,      # $ per unit, never less
    "MIN_ROI": 0.10,             # and never less than 10% of the unit cost
    "HIST_MIN_UNITS": 6,         # units needed in the last 365 days before the history is trusted
    "HIST_FLOOR_PCT": 0.07,      # the history floor = this percentile of the unit prices that really sold
    "STEP_DOWN": 0.03,           # normal step down (3% of the price)
    "STEP_DOWN_MAX": 0.06,       # severe drought / aged stock
    "STEP_UP": 0.03,
    "MIN_STEP": 0.10,            # $ - smaller moves are not worth a price change
    "COOLDOWN_DOWN_H": 48,
    "COOLDOWN_UP_H": 96,
    "MAX_CHANGES_14D": 3,
    "MAX_DROP_30D": 0.20,
    "MAX_RISE_30D": 0.15,
    "MANUAL_FREEZE_DAYS": 5,
    "DROUGHT_MIN_DAYS": 14,      # a product that sells ~1/day is in a drought after 10 days without sale
    "DROUGHT_MULT": 3.0,         # ... one that sells 1/month after 2.5 normal gaps (75 d), capped at DROUGHT_MAX
    "DROUGHT_MAX": 120,
    "DOS_MIN_DROP": 45,          # a drought only lowers the price when there is more than 30 days of stock to move
    "BIG_GAP": 0.08,             # market at least 8% above our price -> raise in a bigger step
    "STEP_UP_BIG": 0.05,
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


def floors(snap, cfg):
    """(safety_floor, floor, ceiling).  safety = cost + fees + minimum profit  (never crossed);  floor = max(safety, history floor)."""
    cost = _f(snap.get("cost"))
    if not cost or cost <= 0:
        return None, None, None
    fba = _f(snap.get("fba_fee"), 0.0)
    fixed = _f(snap.get("fee_fixed"), 0.0)            # closing fees etc.
    prof = max(cfg["MIN_ABS_PROFIT"], cfg["MIN_ROI"] * cost)
    r = cfg["REF_RATE"]
    safety = (cost + fba + fixed + prof) / (1.0 - r)
    hist_floor = None
    hp = snap.get("hist") or {}
    if hp.get("n", 0) >= cfg["HIST_MIN_UNITS"] and _f(hp.get("p_low")):
        hist_floor = hp["p_low"]
    floor = max(safety, hist_floor) if hist_floor else safety
    ceil = None
    if hp.get("n", 0) >= cfg["HIST_MIN_UNITS"] and _f(hp.get("p_high")):
        ceil = hp["p_high"] * cfg["MAX_PRICE_MULT_OVER_HIST"]
    return _r2(safety), _r2(floor), (_r2(ceil) if ceil else None)


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
        deep = severe
        lowest_allowed = safety if deep else floor
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
        return {"action": "down", "price": target, "reason": why, "flags": flags + (["severe"] if severe else []), "floor": floor, "ceil": ceil}

    # =============================================================== UP
    if (on_hand > 0 or inbound > 0) and u30 >= cfg["UP_MIN_UNITS_30"] and not in_drought and not surplus and not anomalous:
        if since_last_h < cfg["COOLDOWN_UP_H"]:
            return hold("waiting after the last change", floor=floor, ceil=ceil)
        room_ok = False
        target = None
        comp = low_fba or None
        if bb and we_hold is False:
            return hold("another seller owns the Buy Box - no raise", floor=floor, ceil=ceil)
        if dos <= cfg["DOS_LOW"]:                       # sells out soon: stop giving margin away
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
                target = min(target, top)
            c30 = [c for c in changes if (now - c["ts"]) <= timedelta(days=30)]
            if c30:
                base = min(c["old"] for c in c30)
                target = min(target, base * (1 + cfg["MAX_RISE_30D"]))
            target = _r2(target)
            if target >= price + cfg["MIN_STEP"] - 1e-9:
                return {"action": "up", "price": target, "reason": "sells well (%.2f/day, %.0f days of supply, Buy Box held): test %.2f" % (v, min(dos, 999), target),
                        "flags": flags, "base_v": v, "floor": floor, "ceil": ceil}
    if price > (ceil or 1e9) + 0.005:
        return hold("price above the ceiling %.2f (history) - watch" % ceil, floor=floor, ceil=ceil, alert="above_ceiling")
    return hold("steady (%.2f/day, %.0f days of supply, last sale %.0f d ago)" % (v, min(dos, 999), dss), floor=floor, ceil=ceil)


def realistic_profit(price, cost, fba_fee, ref_rate=0.15, fee_fixed=0.0):
    """profit per unit at a price (conservative referral)"""
    return price - cost - fba_fee - fee_fixed - ref_rate * price
