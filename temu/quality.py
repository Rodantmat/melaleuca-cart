"""Pro-seller quality score for a dossier (private: stored only in deals.dealsheet.data->'quality').
Rules from published seller research: price $20-70, COGS <=25-30% of price, fees <=35%, net margin >=20-25% after 15% PPC + 3% returns,
demand >=300 units/mo, review moat (top listings 200-1500 good, 3000+ bad), weak incumbents (<4.4 stars) = opening, new entrants ranking = not locked."""


def score(d, g=None):
    m = d.get("model") or {}
    P = m.get("our_price") or 0
    pros, cons, s = [], [], 50
    if not P:
        return {"score": 0, "pros": [], "cons": ["no price"]}
    if P < 15: s -= 25; cons.append("price $%.0f under $15: fees/ads eat it" % P)
    elif P < 20: s -= 8; cons.append("price under $20")
    elif P <= 70: s += 10; pros.append("price $%.0f in the $20-70 sweet spot" % P)
    else: s -= 5; cons.append("price over $70: more capital per unit")
    cogs = (m.get("landed_cost") or 0) / P
    if cogs <= 0.25: s += 12; pros.append("landed cost %.0f%% of price" % (100 * cogs))
    elif cogs <= 0.32: s += 4
    else: s -= 12; cons.append("landed cost %.0f%% of price (>32%%)" % (100 * cogs))
    fee = (m.get("fees_total") or 0) / P
    if fee > 0.38: s -= 12; cons.append("Amazon fees %.0f%% of price" % (100 * fee))
    net = (m.get("profit_unit_before_ads") or 0) / P - 0.15 - 0.03
    if net >= 0.25: s += 15; pros.append("net margin ~%.0f%% after 15%% PPC + 3%% returns" % (100 * net))
    elif net >= 0.15: s += 5
    else: s -= 20; cons.append("net margin only ~%.0f%% after PPC and returns" % (100 * net))
    mu = d.get("market_units_month") or 0
    if mu >= 1500: s += 10; pros.append("market ~%d units/mo" % mu)
    elif mu >= 500: s += 5
    elif mu < 250: s -= 15; cons.append("market only ~%d units/mo" % mu)
    mr = d.get("max_reviews")
    if mr is None: cons.append("reviews unknown")
    elif mr > 3000: s -= 20; cons.append("review moat: leader %d reviews" % mr)
    elif mr <= 1500: s += 8; pros.append("leader only %d reviews" % mr)
    rt = d.get("avg_rating")
    if rt and rt < 4.4: s += 8; pros.append("incumbents avg %.1f stars: room to win on quality" % rt)
    if g:
        new = [t for t in (g.get("top") or []) if str(t.get("asin", "")).startswith(("B0G", "B0H", "B0F")) and t.get("rank") and t["rank"] < 30000]
        if new: s += 8; pros.append("%d recent-ASIN look-alikes ranking: market not locked" % len(new))
        if g.get("prime_advantage"): s += 6; pros.append("no Prime twin: FBA/Prime edge")
        if g.get("verdict") == "FAIL": s -= 40
    return {"score": max(0, min(100, s)), "pros": pros, "cons": cons}
