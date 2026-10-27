"""
melaleuca_fill.py - fills the Melaleuca cart of one account with the order of its Excel tab (button "Auto-Fill Cart").

  python melaleuca_fill.py 7                 tab number 7 (as in credentials.env / feed\\mel_tabs.txt); the plan is feed\\cart_plan_7.tsv
  python melaleuca_fill.py 7 --dry           only works out what would be added (no cart change)

SAFE BY DESIGN: it never pays and never places the order. It stops on the checkout screen and leaves the browser open for you.
"""
import os, sys, json, re, time, math, datetime, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)

NUM = re.compile(r"^\d+$")
STOP = {"and", "the", "of", "with", "a", "pack", "set", "oz", "fl", "ml", "regular", "size", "plus"}
ALIAS = {"antiperspirant": "ap", "antiperspirants": "ap", "deodorant": "deo", "deodorants": "deo", "scented": "", "scent": "", "flavor": "", "flavour": ""}
CLEAN_PACKS = {3: "34911", 4: "34913", 5: "34914"}      # EcoSense Cleaners Customizable 3 / 4 / 5-Pack (item numbers read from the store)


REG = "us"                      # "us" or "ca": every region keeps its own saved catalog (item numbers differ between the two stores)
DAY = 86400


def cpath(name):
    return os.path.join(FEED, "%s_%s.json" % (name, REG))


def cload(name, ttl_days):
    """saved answers of the store: {key: {"t": time, "v": value}}; entries older than ttl_days are dropped"""
    try:
        d = json.load(open(cpath(name), encoding="utf-8"))
    except Exception:
        return {}
    now = time.time()
    return {k: e for k, e in d.items() if isinstance(e, dict) and now - float(e.get("t", 0)) < ttl_days * DAY}


def csave(name, d):
    try:
        os.makedirs(FEED, exist_ok=True)
        json.dump(d, open(cpath(name), "w", encoding="utf-8"))
    except Exception:
        pass


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------------------------------------ plan file
def f2(x, d=0.0):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return d


def load_plan(path):
    plan = {"tab": "", "n": 0, "credit": 10.42, "lines": [], "total": None, "groups": {}, "members": [], "cleanpack": {}}
    for ln in open(path, encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        k = p[0]
        if k == "TAB":
            plan["tab"], plan["n"] = p[1], int(f2(p[2]))
        elif k == "CREDIT":
            plan["credit"] = f2(p[1], 10.42)
        elif k == "L" and len(p) >= 15:
            p += [""] * (16 - len(p))
            plan["lines"].append({"row": int(f2(p[1])), "asin": p[2], "name": p[3], "note": p[4], "qty": int(round(f2(p[5]))), "pts": f2(p[6]),
                                  "type": p[7], "group": p[8], "setn": int(round(f2(p[9]))), "melid": p[10], "packsku": p[11], "offsku": p[12],
                                  "offtype": p[13], "ws": f2(p[14]), "offunits": int(round(f2(p[15], 0)))})
        elif k == "TOTAL":
            plan["total"] = {"units": f2(p[1]), "ws": f2(p[2]), "pts": f2(p[3])}
        elif k == "G":
            p += [""] * (7 - len(p))
            plan["groups"][p[1]] = {"what": p[2], "pack": p[3], "units": int(f2(p[4])), "slots": p[5], "label": p[6]}
        elif k == "M":
            plan["members"].append(p[1:5])
        elif k == "CLEANPACK":
            plan["cleanpack"][int(f2(p[1]))] = (f2(p[2]), f2(p[3]))
    return plan


# ------------------------------------------------------------------------------------------------ names
def toks(s):
    s = (s or "").lower().replace("&", " and ").replace("™", "").replace("®", "")
    out = set()
    for w in re.split(r"[^a-z0-9]+", s):
        w = ALIAS.get(w, w)
        if w and w not in STOP and not re.fullmatch(r"\d+(oz|ml|l|g)?", w):
            out.add(w)
    return out


ALIAS.update({"iced": "ice", "tea": "tea", "splash": "splash", "h2o": "splash"})


def weights_for(titles):
    """a word that only one choice has counts a lot, a word most choices share (fluoride, packets) counts little"""
    df = {}
    for t in titles:
        for w in toks(t):
            df[w] = df.get(w, 0) + 1
    return {w: 1.0 / n for w, n in df.items()}


def name_score(product_name, choice_title, weights=None):
    a, b = toks(product_name), toks(choice_title)
    if not b or not a:
        return 0.0
    if weights is None:
        inter = len(a & b)
        return (inter / len(b)) * 0.75 + (inter / len(a)) * 0.25
    wt = lambda t: weights.get(t, 1.0)
    got = sum(wt(t) for t in b if t in a)
    tot = sum(wt(t) for t in b)
    return got / tot * 0.97 + 0.03 * len(a & b) / len(a)


# ------------------------------------------------------------------------------------------------ store pages
def grab_json_list(h, key):
    i = h.find('"%s":[{' % key)
    if i < 0:
        return []
    j = h.find("[", i)
    d = 0
    for k in range(j, len(h)):
        if h[k] == "[":
            d += 1
        elif h[k] == "]":
            d -= 1
            if d == 0:
                try:
                    return json.loads(h[j:k + 1])
                except Exception:
                    return []
    return []


def parse_info(h):
    """the choices (slots) and accessories of a product / pack page"""
    conf = []
    for c in grab_json_list(h, "Configurations"):
        ch = []
        for x in c.get("Choices") or []:
            m = re.search(r"products/(\d+)h", x.get("ShelfImage") or x.get("PdpImage") or "")
            ch.append({"title": x.get("Title") or "", "sku": m.group(1) if m else None, "refiner": x.get("FacetRefinerId")})
        conf.append({"type": c.get("Type"), "title": c.get("Title"), "sku": c.get("Sku"), "feature": (c.get("Targets") or [None])[0],
                     "req": int(c.get("TotalRequired") or 0), "choices": ch})
    acc = []
    for a in grab_json_list(h, "Accessories"):
        pr = a.get("PriceRange") or {}
        acc.append({"sku": str(a.get("Sku")), "title": a.get("Title") or (a.get("Image") or {}).get("Alt") or "", "price": pr.get("RawMinPreferredPrice"), "pts": pr.get("RawMinPoints")})
    return {"conf": conf, "acc": acc}


def assign_choices(units, conf):
    """units = [(name, melid)] ; conf = the slots of a pack ('Choose' slots + FIXED contents). Returns (configurations list for the cart, problems, choices).
    Some Canadian packs differ from the US ones: they hold FIXED products you cannot change (e.g. the Cleaning Wipes 5-Pack = Sol-U-Guard + MelaMagic +
    Tough & Tender fixed, and only 2 free choices). A unit of the plan that the pack already holds as a fixed product is covered by it and does not use a
    free choice; whatever the pack holds that the plan did not ask for is reported, because it ends up in the cart."""
    statics = [c for c in conf if c.get("type") == "Static" and (c.get("title") or "").strip() and not any(w in c["title"].lower() for w in ACC_WORDS)]
    has_free = any(c.get("type") == "FSKU" for c in conf)
    covered, extra = set(), []
    if statics and has_free:
        for c in statics:
            best = None
            for ui, (nm, mel) in enumerate(units):
                if ui in covered:
                    continue
                sc = 10.0 if (mel and NUM.match(mel) and str(c.get("sku")) == mel) else name_score(nm, c.get("title") or "")
                if sc >= 0.6 and (best is None or sc > best[0]):
                    best = (sc, ui)
            if best:
                covered.add(best[1])
            else:
                extra.append(c.get("title") or str(c.get("sku")))
    if not covered and not extra:
        return _assign_choices(units, conf)
    rest = [u for ui, u in enumerate(units) if ui not in covered]
    out, problems, chosen = _assign_choices(rest, conf)
    if extra:
        problems.append("this store's pack also holds FIXED products that are not in the plan: %s - they come with the pack and cannot be changed (the plan has %d unit(s) of the pack, the store gives those instead)" % (", ".join(extra), len(units)))
    chosen = chosen + [(units[ui][0], "(fixed in the pack)", 1.0) for ui in sorted(covered)]
    return out, problems, chosen


def _assign_choices(units, conf):
    """units = [(name, melid)] ; conf = the 'Choose' slots of a pack. Returns (configurations list for the cart, problems)"""
    fs = [c for c in conf if c["type"] == "FSKU"]
    cap = [c["req"] for c in fs]
    cands, cands2 = [], []
    wts = [weights_for([ch["title"] for ch in c["choices"]]) for c in fs]
    for ui, (nm, mel) in enumerate(units):
        for ci, c in enumerate(fs):
            for ch in c["choices"]:
                if mel and NUM.match(mel) and ch["sku"] == mel:
                    sc = 10.0
                else:
                    sc = name_score(nm, ch["title"], wts[ci])
                    if re.match(r"\s*HE\b", ch["title"]) and not re.search(r"\bHE\b|high.efficiency", nm, re.I):
                        sc -= 0.01          # "Regular" and "HE" versions of one scent: the sheet means the regular one unless it says HE
                if sc >= 0.3:
                    cands2.append((sc, ui, ci, ch))
                if sc >= 0.5:
                    cands.append((sc, ui, ci, ch))
    cands.sort(key=lambda t: -t[0])
    got, used, problems = {}, set(), []
    for sc, ui, ci, ch in cands:
        if ui in used or cap[ci] <= 0 or not ch["sku"]:
            continue
        # a clearly worse second choice with the same score would be ambiguous: accepted, the report shows the choice made
        got[ui] = (ci, ch, sc)
        used.add(ui)
        cap[ci] -= 1
    for ui, (nm, mel) in enumerate(units):       # weak match (0.3..0.5): accept the single best choice when it is clearly ahead
        if ui in got:
            continue
        weak = sorted([(sc, ci, ch) for sc, u, ci, ch in cands2 if u == ui and cap[ci] > 0 and ch["sku"]], key=lambda t: -t[0])
        if weak and weak[0][0] >= 0.3 and (len(weak) == 1 or weak[0][0] - weak[1][0] >= 0.2):
            got[ui] = (weak[0][1], weak[0][2], weak[0][0]); used.add(ui); cap[weak[0][1]] -= 1
    out = []
    for ui, (nm, mel) in enumerate(units):
        if ui not in got:
            problems.append("no choice found for '%s' (%s)%s" % (nm, mel, (" - this store's pack holds only %d choices, the sheet has %d products in it (the store pack differs from the US one): add the missing ones by hand" % (sum(c["req"] for c in fs), len(units))) if sum(c["req"] for c in fs) < len(units) else ""))
    # two DIFFERENT products of the sheet that landed on the same choice: the store pack does not offer one of them (e.g. a flavour that no longer exists in it)
    bychoice = {}
    for ui, (ci, ch, sc) in got.items():
        bychoice.setdefault((ci, ch["title"]), []).append(units[ui][0])
    for (ci, title), names in bychoice.items():
        dist = sorted(set(names), key=lambda x: (len(toks(x)), x))
        for other in dist[1:]:
            problems.append("SUBSTITUTED: '%s' is not a choice of this pack - the store pack has '%s' (also used for '%s'); change it by hand if you need the exact one" % (other, title, dist[0]))
    per = {}
    for ui, (ci, ch, sc) in got.items():
        per.setdefault(ci, []).append(ch)
    for ci, c in enumerate(fs):
        for ch in per.get(ci, []):
            out.append({"FeatureSku": c["feature"], "SelectedSku": ch["sku"]})
    for c in conf:
        if c["type"] == "Static":
            out.append({"FeatureSku": str(c["sku"]), "SelectedSku": None})
    chosen = [(units[ui][0], got[ui][1]["title"], round(got[ui][2], 2)) for ui in sorted(got)]
    return out, problems, chosen


# ------------------------------------------------------------------------------------------------ families (flavours / scents / sizes)
CATEGORIES = ["supplements", "cleaning-and-laundry", "cleaning-and-laundry/cleaning", "cleaning-and-laundry/laundry", "personal-care", "beauty",
              "healthy-foods-and-drinks", "medicines-and-treatments", "home-fragrance", "essential-oils", "member-savings-pack", "new-products",
              "extra-savings", "featured-this-month", "curated-collections"]


ALL_CARDS = {}          # every card seen: key = first item number -> title, item numbers, price range, points


def family_cards_from(js, out):
    for c in (js.get("Cards") or []) if isinstance(js, dict) else []:
        d = (c.get("InnerData") or {}).get("Data") or {}
        prods = d.get("Products") or []
        try:
            pr = d.get("PriceRange") or {}
            skus = [str(p.get("Sku")) for p in prods] or ([str(d.get("Sku"))] if d.get("Sku") else [])
            if skus:
                ALL_CARDS[skus[0]] = {"title": d.get("Title") or "", "skus": skus, "pmin": pr.get("RawMinPreferredPrice"), "pmax": pr.get("RawMaxPreferredPrice"),
                                      "pts": pr.get("RawMinPoints"), "ptsmax": pr.get("RawMaxPoints")}
        except Exception:
            pass
        if d.get("FamilyID") and len(prods) > 1 and d.get("PdpLink"):
            out[str(d["FamilyID"])] = {"pdp": d["PdpLink"], "skus": [str(p.get("Sku")) for p in prods], "title": d.get("Title")}


def parse_variants(h):
    """every flavour / scent / size of a product page: <script id=data-configurator-pdp> {Data:{Products:[...]}}"""
    m = re.search(r'id="data-configurator-pdp"[^>]*>\s*(\{.*?\})\s*</script>', h, re.S)
    out = []
    if not m:
        return out
    try:
        data = json.loads(m.group(1))
    except Exception:
        return out
    for p in (data.get("Data") or {}).get("Products") or []:
        pr = p.get("PriceRange") or {}
        out.append({"sku": str(p.get("Sku")), "name": p.get("OptionName") or p.get("Name") or "", "size": p.get("Size") or "",
                    "price": pr.get("RawMinPreferredPrice"), "pts": pr.get("RawMinPoints"), "sold": bool(p.get("IsSoldOut") or p.get("IsOffSale"))})
    return out


class Catalog:
    """finds the item number of a flavour / scent / size when the sheet only knows the family (F252, R480H)"""
    def __init__(self, s):
        self.s = s
        self.famc = cload("family_map", 45)          # {"all": {"t":..,"v":{family: ...}}, "cards": {...}}
        self.fam = dict((self.famc.get("all") or {}).get("v") or {})
        self.complete = bool((self.famc.get("all") or {}).get("complete"))
        self.varc = cload("variants", 7)
        self.var = {k: e["v"] for k, e in self.varc.items()}
        self.crawled = False
        ALL_CARDS.update((self.famc.get("cards") or {}).get("v") or {})

    def crawl(self, need):
        if self.crawled:
            return
        if self.complete and self.fam and ALL_CARDS and all(f in self.fam for f in need if f != "manual"):
            log("  catalog from the saved copy: %d families (no need to read the store)" % len(self.fam))
            return
        self.crawled = True
        pg = self.s.page
        for cat in CATEGORIES:
            del self.s.json_log[:]            # the session keeps at most 400 answers: start every category with an empty list
            try:
                pg.goto("%s/productstore/%s?sc_lang=en-US" % (BASE, cat), wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(5000)
            except Exception as e:
                log("  category", cat, "not opened:", str(e)[:60])
                continue
            base = None
            for attempt in (1, 2):
                for u, m, j in self.s.json_log:
                    if "/api/category/search/" in u:
                        base, first = u, j
                if base:
                    break
                pg.wait_for_timeout(5000)
            if base:
                family_cards_from(first, self.fam)
                total = int((first or {}).get("TotalResults") or 0)
                got = len((first or {}).get("Cards") or [])
                if total > got and got:
                    pages = -(-total // got)          # the store hands out 40 cards per page; pageNumber=N returns pages 1..N together
                    r = self.s.fetch(base + "&pageNumber=%d" % pages)
                    family_cards_from(r.get("json") or {}, self.fam)
                del self.s.json_log[:]
            log("  category %s: %d families known" % (cat, len(self.fam)))
        now = time.time()
        self.complete = len(self.fam) >= 75 and len(ALL_CARDS) >= 400          # a crawl that really read the whole store
        csave("family_map", {"all": {"t": now, "v": self.fam, "complete": self.complete}, "cards": {"t": now, "v": ALL_CARDS}})

    def variants(self, fid):
        if fid in self.var:
            return self.var[fid]
        f = self.fam.get(fid)
        out = []
        if f:
            try:
                for _k in range(3):
                    try:
                        self.s.page.goto(BASE + f["pdp"] + ("&" if "?" in f["pdp"] else "?") + "sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                        break
                    except Exception:
                        if _k == 2:
                            raise
                        self.s.page.wait_for_timeout(4000 * (_k + 1))
                self.s.page.wait_for_timeout(2500)
                out = parse_variants(self.s.page.content())
            except Exception as e:
                log("  family page not read:", fid, str(e)[:70])
        self.var[fid] = out
        if out:
            self.varc[fid] = {"t": time.time(), "v": out}
            csave("variants", self.varc)
        return out

    def resolve_manual(self, L):
        """the sheet has no item number for this row ('manual'): find the store card with the same price and points, then the best name"""
        if not ALL_CARDS:
            self.crawl(["manual"])
        q = max(1, L["qty"])
        up, upts = L["ws"] / q, L["pts"] / q
        npk = 1
        mpk = re.search(r"\b(\d+)-Pack\b", L["name"], re.I)
        if mpk and int(mpk.group(1)) > 1:       # "X - 2-Pack" without an item number: the same as N single units of X
            npk = int(mpk.group(1))
            up, upts = up / npk, upts / npk
        hits = []
        pool = ALL_CARDS
        if REG == "ca":
            try:
                us = json.load(open(os.path.join(FEED, "family_map_us.json"), encoding="utf-8")).get("cards", {}).get("v", {})
                ca_skus = {str(x) for c in ALL_CARDS.values() for x in c.get("skus", [])}
                pool = {k: c for k, c in us.items() if any(str(x) in ca_skus for x in c.get("skus", []))}
            except Exception:
                pool = ALL_CARDS
        for k, c in pool.items():
            ps = [x for x in (c.get("pmin"), c.get("pmax")) if x]
            if any(abs(float(x) - up) < 0.006 for x in ps) and (c.get("pts") is None or abs(float(c.get("pts") or 0) - upts) < 0.51 or abs(float(c.get("ptsmax") or 0) - upts) < 0.51):
                hits.append((name_score(L["name"], c["title"]), k, c))
        hits.sort(key=lambda t: -t[0])
        if not hits:
            return None, "no store product costs %.2f with %.0f points" % (up, upts)
        if len(hits) == 1 or hits[0][0] > hits[1][0] + 0.001:
            sc, k, c = hits[0]
            if sc > 0.0 or len(hits) == 1:
                if len(c["skus"]) > 1:
                    return None, "card '%s' has several versions: pick by hand" % c["title"]
                if npk > 1:
                    L["qty"] = q * npk
                return c["skus"][0], "%s (price %.2f, %.0f pts)%s" % (c["title"], up, upts, (" x%d for the %d-pack" % (npk, npk)) if npk > 1 else "")
        elif all(len(h[2]["skus"]) == 1 for h in hits[:2]):
            # nothing in the name tells them apart (e.g. a credit oil 'T36-C5'): same price and points, so the totals are identical - take the first, say so
            c = hits[0][2]
            L.setdefault("warn", []).append("CHECK: '%s' has no name in the store; took '%s' (same price and points as %s)" % (L["name"], c["title"], "; ".join(h[2]["title"] for h in hits[1:3])))
            return c["skus"][0], "%s - AMBIGUOUS, same price/points as %d others, check it" % (c["title"], len(hits) - 1)
        return None, "several store products cost %.2f with %.0f points: %s" % (up, upts, "; ".join(h[2]["title"] for h in hits[:3]))

    def resolve(self, L):
        """-> (sku, why) for a plan line whose Mela ID is F#### or R####L/H"""
        mid = L["melid"]
        m = re.fullmatch(r"([FR])(\d+)([LH]?)", mid or "")
        if not m:
            return self.resolve_manual(L)
        fid = m.group(2)
        if fid not in self.fam:
            self.crawl([fid])
        if fid not in self.fam and self.crawled:           # the store listing came back incomplete: read it once more
            self.crawled = False
            self.crawl([fid])
            if fid not in self.fam:
                return None, "family %s not found in the store" % fid
        vs = [v for v in self.variants(fid) if not v["sold"]] or self.variants(fid)
        if not vs:
            return None, "family %s not found in the store" % fid
        if m.group(1) == "R":
            prices = sorted({v["price"] for v in vs if v["price"]})
            if len(prices) > 1:
                want = prices[0] if m.group(3) == "L" else prices[-1]
                vs2 = [v for v in vs if v["price"] == want]
                vs = vs2 or vs
        wv = weights_for([v["name"] for v in vs])
        sc = sorted(((name_score(L["name"], v["name"], wv), v) for v in vs), key=lambda t: -t[0])
        if len(vs) == 1:
            return vs[0]["sku"], "only variant: " + vs[0]["name"]
        best = sc[0]
        if best[0] < 0.5:
            return None, "no variant of family %s looks like '%s' (best: %s %.2f)" % (fid, L["name"], best[1]["name"], best[0])
        if len(sc) > 1 and sc[1][0] >= best[0] - 0.001:
            return None, "ambiguous: '%s' fits %s and %s equally" % (L["name"], best[1]["name"], sc[1][1]["name"])
        return best[1]["sku"], "%s (%.2f)" % (best[1]["name"], best[0])


# ------------------------------------------------------------------------------------------------ the plan -> cart actions
class Action:
    def __init__(self, kind, sku, qty=1, conf=None, promo=0, label="", rows=None, expect_pts=0.0, expect_ws=0.0, notes=None):
        self.kind, self.sku, self.qty, self.conf, self.promo, self.label = kind, str(sku), qty, conf or [], promo, label
        self.rows, self.expect_pts, self.expect_ws, self.notes = rows or [], expect_pts, expect_ws, notes or []
        self.done, self.line = False, None
        self.extra = []                  # more cart lines that belong to this action (a coupon that was added twice)


FIXED_SKUS = []          # item numbers the sheet had wrong, corrected by name: shown in the final box
IGN_TAIL = {"bottle", "loads", "load", "count", "ct", "ounce", "with"}


def check_single(L, sku, info):
    """the sheet's item number must be the flavour / scent the sheet's NAME says. If another item of the same price and points
    fits the name clearly better (e.g. 'Creamy Vanilla Bean' listed under the Creamy Chocolate item), use that one."""
    try:
        card = None
        for k, c in ALL_CARDS.items():
            if str(sku) in [str(x) for x in c.get("skus", [])]:
                card = c
                break
        parts = [x.strip() for x in L["name"].split(" - ")]
        if not card or len(parts) < 2:
            return sku
        D = toks(" ".join(parts[1:])) - IGN_TAIL
        if len(D) < 2:
            return sku
        have = set(toks(card["title"]))
        try:
            for cf in (info(sku) or {}).get("conf", []):
                for ch in cf.get("choices", []):
                    have |= toks(ch.get("title", ""))
        except Exception:
            pass
        cur = len(D & have) / float(len(D))
        if cur >= 0.999:
            return sku
        q = max(1, L["qty"])
        up, upts = L["ws"] / q, L["pts"] / q
        found = []
        for k, c in ALL_CARDS.items():
            if c is card:
                continue
            ps = [x for x in (c.get("pmin"), c.get("pmax")) if x]
            if not any(abs(float(x) - up) < 0.006 for x in ps):
                continue
            if not (c.get("pts") is None or abs(float(c.get("pts") or 0) - upts) < 0.51 or abs(float(c.get("ptsmax") or 0) - upts) < 0.51):
                continue
            if len(c.get("skus", [])) > 1:
                inf = info(c["skus"][0]) or {}
                for cf in inf.get("conf", []):
                    if cf.get("type") != "Facet":
                        continue
                    for ch in cf.get("choices", []):
                        if ch.get("sku"):
                            found.append((len(D & (toks(ch["title"]) | toks(c["title"]))) / float(len(D)), str(ch["sku"]), ch["title"]))
            else:
                found.append((len(D & toks(c["title"])) / float(len(D)), str(c["skus"][0]), c["title"]))
        found.sort(key=lambda x: -x[0])
        if found and found[0][0] >= cur + 0.1 and (len(found) == 1 or found[0][0] > found[1][0] + 0.001) and found[0][1] != str(sku):
            msg = "'%s': the sheet has item %s (%s), the name fits item %s (%s) better - used that one" % (L["name"][:50], sku, card["title"][:45], found[0][1], found[0][2][:45])
            FIXED_SKUS.append(msg)
            log("  SKU CORRECTED:", msg)
            return found[0][1]
        if cur < 0.5:
            log("  name check: '%s' vs store item %s '%s' - could not find a better one, kept as the sheet says" % (L["name"][:45], sku, card["title"][:45]))
    except Exception as e:
        log("  name check skipped:", str(e)[:80])
    return sku


ACC_WORDS = ("bottle", "sprayer", "pump", "brush", "mop", "dispenser")
AUDIT = []          # packs found unusable for the plan during this run: (pack, reason) -> feed\\pack_audit_fill_<region>.tsv


def pack_mismatch(inf, units):
    """'' when the store pack can hold exactly the products of the plan, else the reason. A pack holds its FREE choices (req) plus FIXED products; the plan's
    units must be exactly those: free capacity + fixed (non accessory) products == units, and every fixed product must be one of the plan's products."""
    conf = inf.get("conf") or []
    free = sum(int(c.get("req") or 0) for c in conf if c.get("type") == "FSKU")
    fixed = [c for c in conf if c.get("type") == "Static" and (c.get("title") or "").strip() and not any(w in c["title"].lower() for w in ACC_WORDS)]
    if not free and not fixed:
        return ""
    if free + len(fixed) != len(units):
        return "the store pack holds %d free choice(s) + %d fixed product(s) but the sheet puts %d products in it" % (free, len(fixed), len(units))
    for c in fixed:
        if not any((m and NUM.match(m) and str(c.get("sku")) == m) or name_score(nm, c.get("title") or "") >= 0.6 for nm, m in units):
            return "the store pack holds the fixed product '%s' that is not among the sheet's products" % c.get("title")
    return ""


def note_audit(pack, reason):
    if not any(a[0] == str(pack) for a in AUDIT):
        AUDIT.append((str(pack), reason))


def write_audit(replace=False):
    """pack audit file: the workbook (Sync_Canada_Points) switches off the sheet sets that use these packs, so the next order is built without them"""
    path = os.path.join(FEED, "pack_audit_fill_%s.tsv" % REG)
    if replace:                      # a full audit is authoritative: packs that are fine now are removed again
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("pack\treason\r\n")
            for a in AUDIT:
                f.write("%s\t%s\r\n" % a)
        return
    if not AUDIT:
        return
    have = set()
    try:
        have = {ln.split("\t")[0] for ln in open(path, encoding="utf-8").read().splitlines()[1:]}
    except Exception:
        pass
    new = [a for a in AUDIT if a[0] not in have]
    if not new and os.path.exists(path):
        return
    with open(path, "a", encoding="utf-8", newline="") as f:
        if f.tell() == 0:
            f.write("pack\treason\r\n")
        for a in new:
            f.write("%s\t%s\r\n" % a)


def audit_pack(inf, size):
    """reason a store pack cannot serve a sheet set of `size` units ('' = fine). Fixed (non accessory) products next to free choices = a 'mixed' pack, which can never be
    'any of these products'; free slots that do not add up to the set size are a different pack than the sheet thinks."""
    conf = inf.get("conf") or []
    free = sum(int(c.get("req") or 0) for c in conf if c.get("type") == "FSKU")
    fixed = [c.get("title") for c in conf if c.get("type") == "Static" and (c.get("title") or "").strip() and not any(w in c["title"].lower() for w in ACC_WORDS)]
    if free and fixed:
        return "fixed contents (%s) next to %d free choice(s)" % ("; ".join(fixed), free)
    if free and size and free != size:
        return "%d free choice(s) but the sheet set has %d units" % (free, size)
    if fixed and size and len(fixed) != size:
        return "%d fixed product(s) but the sheet set has %d units" % (len(fixed), size)
    return ""


def do_audit(fl, say):
    """reads (once, text only - pictures are blocked) every pack the sheet uses and checks its structure: feed\\pack_audit_fill_<region>.tsv + pack_audit_report_<region>.txt"""
    packs = {}
    try:
        for ln in open(os.path.join(FEED, "mel_groups_in.tsv"), encoding="utf-8-sig").read().splitlines()[1:]:
            p = ln.split("\t")
            if len(p) >= 3 and NUM.match(p[1].strip()):
                packs.setdefault(p[1].strip(), []).append((p[0], int(f2(p[2]))))
    except Exception as e:
        say("mel_groups_in.tsv not readable:", e)
    for n, sku in CLEAN_PACKS.items():
        packs.setdefault(sku, []).append(("CLEAN", n))
    say("pack audit (%s store): %d packs" % (REG.upper(), len(packs)))
    lines, bad = [], 0
    try:
        known = {str(x) for c in ((cload("family_map", 3650).get("cards") or {}).get("v") or {}).values() for x in c.get("skus", [])}
    except Exception:
        known = set()
    for sku, uses in sorted(packs.items(), key=lambda t: int(t[0])):
        if known and sku not in known and not all(re.match(r"^F\d+$", u[0]) for u in uses):
            reason = "this item number is not in the %s store's catalog (discontinued / not sold there)" % REG.upper()
            lines.append("%s\tBAD\t%s\t-\t%s" % (sku, ",".join("%s(%d)" % u for u in uses), reason))
            bad += 1
            note_audit(sku, reason)
            say("  PACK %s used by %s CANNOT BE USED: %s" % (sku, ",".join(u[0] for u in uses), reason))
            continue
        inf = fl.info(sku)
        if not inf.get("conf") and not inf.get("acc") and sku in fl.failed:
            lines.append("%s\tNOT READ\t%s" % (sku, ",".join(u[0] for u in uses)))
            say("  %s: page not read (%s)" % (sku, ",".join(u[0] for u in uses)))
            continue
        reasons = [audit_pack(inf, u[1]) for u in uses]
        reason = next((r for r in reasons if r), "")
        conf = inf.get("conf") or []
        desc = "free %d / fixed %d" % (sum(int(c.get("req") or 0) for c in conf if c.get("type") == "FSKU"), len([c for c in conf if c.get("type") == "Static" and (c.get("title") or "").strip()]))
        lines.append("%s\t%s\t%s\t%s\t%s" % (sku, "BAD" if reason else "ok", ",".join("%s(%d)" % u for u in uses), desc, reason))
        if reason:
            bad += 1
            note_audit(sku, reason)
            say("  PACK %s used by %s CANNOT BE USED AS PLANNED: %s" % (sku, ",".join(u[0] for u in uses), reason))
        else:
            say("  pack %s ok (%s; %s)" % (sku, ",".join(u[0] for u in uses), desc))
    write_audit(replace=True)
    with open(os.path.join(FEED, "pack_audit_report_%s.txt" % REG), "w", encoding="utf-8") as f:
        f.write("pack\tresult\tused by\tstructure\treason\n" + "\n".join(lines) + "\n")
    say("pack audit done: %d pack(s) cannot be used as planned%s" % (bad, " - run Generate All Orders: the workbook switches those sets off" if bad else ""))


def build_actions(plan, info, resolve_variant=None):
    """info(sku) -> {'conf','acc'} of a pack page. Returns (actions, offer_lines, problems, notes)"""
    acts, offers, problems, notes = [], [], [], []
    groups = {}
    for L in plan["lines"]:
        if L["qty"] <= 0:
            continue
        if L["type"] == "Special Offers":
            offers.append(L)
            continue
        key = L["group"]
        if L["type"] == "Deal of the Month":
            q = max(1, int(round(L["qty"] / max(1, L["offunits"] or 1))))
            acts.append(Action("single", L["offsku"] or L["melid"], q, label="Deal of the Month: " + L["name"], rows=[L["row"]], expect_pts=L["pts"], expect_ws=L["ws"]))
            continue
        if key and not key.startswith("#"):
            groups.setdefault(key, []).append(L)
            continue
        if key.startswith("#") and L["packsku"]:
            n = max(1, L["setn"] or 2)
            packs = L["qty"] // n
            if packs * n != L["qty"]:
                problems.append("row %d %s: quantity %d does not fit sets of %d" % (L["row"], L["name"], L["qty"], n))
                packs = max(1, packs)
            inf = info(L["packsku"]) or {"conf": [], "acc": []}
            for _ in range(packs):
                conf, pr, ch = assign_choices([(L["name"], L["melid"])] * n, inf["conf"]) if any(c["type"] == "FSKU" for c in inf["conf"]) else ([], [], [])
                problems += ["row %d: %s" % (L["row"], x) for x in pr]
                acts.append(Action("pack", L["packsku"], 1, conf, label="%d-pack: %s" % (n, L["name"]), rows=[L["row"]], expect_pts=L["pts"] / packs, expect_ws=L["ws"] / packs, notes=[("%s -> %s (%s)" % c) for c in ch]))
            note_coupon(L, notes)
            add_accessories(L, inf, acts, notes)
            continue
        # plain products (also coupon lines and '#' sets without a pack product)
        sku = L["melid"]
        if not NUM.match(sku or ""):
            v = resolve_variant(L) if resolve_variant else None
            if v:
                sku = v
            else:
                problems.append("row %d %s: no item number for '%s' (sheet has '%s') - add this one by hand" % (L["row"], L["asin"], L["name"], sku))
                continue
        if NUM.match(L["melid"] or "") and ALL_CARDS:
            sku = check_single(L, sku, info)
        sconf, snotes = [], []
        try:
            si = info(sku)
        except Exception:
            si = None
        if si and si.get("conf"):         # a product with its own choices (e.g. scent of a starter pack)
            sconf, sprob, sch = assign_choices([(L["name"], L["melid"])], si["conf"]) if any(c["type"] == "FSKU" for c in si["conf"]) else ([{"FeatureSku": str(c["sku"]), "SelectedSku": None} for c in si["conf"] if c["type"] == "Static"], [], [])
            problems.extend("row %d: %s" % (L["row"], x) for x in sprob)
            snotes = [("%s -> %s (%s)" % c) for c in sch]
        acts.append(Action("single", sku, L["qty"], sconf, label=L["name"], rows=[L["row"]], expect_pts=L["pts"], expect_ws=L["ws"], notes=snotes))
        if si and si.get("acc"):
            add_accessories(L, si, acts, notes)
        note_coupon(L, notes)
    # ---- mix-and-match groups
    for key, ls in groups.items():
        G = plan["groups"].get(key) or {}
        units = []
        for L in ls:
            units += [L] * L["qty"]
        n = ls[0]["setn"] or G.get("units") or 2
        pack = G.get("pack")
        if n != G.get("units") and key == "CLEAN":
            pack = CLEAN_PACKS.get(n)
            if not pack:
                problems.append("group CLEAN: the item number of the %d-pack of cleaners is not known" % n)
                continue
        tot_pts, tot_ws = sum(L["pts"] for L in ls), sum(L["ws"] for L in ls)
        if not pack:
            # no pack product in the store: the products are added one by one (the set price comes from the cart itself)
            for L in ls:
                sku = L["melid"]
                if not NUM.match(sku or ""):
                    sku = resolve_variant(L) if resolve_variant else None
                if not sku:
                    problems.append("row %d %s: no item number (group %s has no pack)" % (L["row"], L["name"], key))
                    continue
                acts.append(Action("single", sku, L["qty"], label=L["name"], rows=[L["row"]], expect_pts=L["pts"], expect_ws=L["ws"]))
            continue
        if len(units) % n:
            problems.append("group %s: %d units do not fill sets of %d" % (key, len(units), n))
        npk = len(units) // n
        inf = info(pack) or {"conf": [], "acc": []}
        has_choice = any(c["type"] == "FSKU" for c in inf["conf"])
        bad = pack_mismatch(inf, [(L["name"], L["melid"]) for L in units[:n]]) if units else ""
        if bad:
            # the store pack cannot hold what the sheet says: do NOT fill a different pack - the products go in one by one (own packs / singles) and the pack is audited
            problems.append("group %s: PACK %s CANNOT BE USED - %s. The products were added one by one instead (their points may differ from the sheet: run Generate All Orders again, the workbook now switches this set off)." % (key, pack, bad))
            note_audit(pack, bad)
            for L in ls:
                sku = L["melid"]
                if not NUM.match(sku or ""):
                    sku = resolve_variant(L) if resolve_variant else None
                if not sku:
                    problems.append("row %d %s: no item number (group %s pack unusable)" % (L["row"], L["name"], key))
                    continue
                acts.append(Action("single", sku, L["qty"], label=L["name"], rows=[L["row"]], expect_pts=L["pts"], expect_ws=L["ws"]))
            continue
        for i in range(npk):
            chunk = units[i * n:(i + 1) * n]
            if has_choice:
                conf, pr, ch = assign_choices([(L["name"], L["melid"]) for L in chunk], inf["conf"])
                problems += ["group %s: %s" % (key, x) for x in pr]
            else:
                conf, ch = [c for c in [{"FeatureSku": str(c["sku"]), "SelectedSku": None} for c in inf["conf"] if c["type"] == "Static"]], []
            rows = sorted({L["row"] for L in chunk})
            a = Action("pack", pack, 1, conf, label="%s pack %d/%d: %s" % (key, i + 1, npk, ", ".join(sorted({L["name"][-28:] for L in chunk}))),
                       rows=rows, expect_pts=tot_pts / max(npk, 1), expect_ws=tot_ws / max(npk, 1), notes=[("%s -> %s (%s)" % c) for c in ch])
            acts.append(a)
        for L in ls:
            add_accessories(L, inf, acts, notes)
    return acts, offers, problems, notes


def note_coupon(L, notes):
    if L["type"] == "Coupon":
        notes.append("row %d %s: coupon line - the product is added, apply its coupon in the cart (coupons are not applied automatically)" % (L["row"], L["name"]))


def add_accessories(L, inf, acts, notes):
    nt = (L["note"] or "").lower()
    want = []
    if "add bottle" in nt:
        want.append("bottle")
    if "add pump" in nt:
        want.append("pump")
    for w in want:
        best = None
        for a in inf["acc"]:
            t = a["title"].lower()
            if w in t:
                sc = name_score(L["name"], a["title"])
                if best is None or sc > best[0]:
                    best = (sc, a)
        if best and best[0] > 0.2:
            acts.append(Action("single", best[1]["sku"], L["qty"], label="%s for %s" % (best[1]["title"], L["name"]), rows=[L["row"]]))
        else:
            notes.append("row %d %s: note says '%s' but no matching accessory was found - add it by hand" % (L["row"], L["name"], w))


# ------------------------------------------------------------------------------------------------ the store
BASE = "https://www.melaleuca.com"


def cart_items(js):
    """every line of the cart: (line id, sku, qty, title, price, points)"""
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "LineId" in o and ("Sku" in o or "Quantity" in o):
                out.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk((js or {}).get("Data", {}).get("Items"))
    return out


class Filler:
    def __init__(self, s):
        self.s = s
        self.infoc = cload("info", 30)
        self.cache = {k: e["v"] for k, e in self.infoc.items()}
        self.added = []
        self.failed = []

    def info(self, sku):
        sku = str(sku)
        if sku not in self.cache:
            pg = self.s.page
            try:
                for _k in range(3):                   # a dropped connection is tried again (3x) before the item is given up
                    try:
                        pg.goto("%s/products/%s?sc_lang=en-US" % (BASE, sku), wait_until="domcontentloaded", timeout=60000)
                        break
                    except Exception:
                        if _k == 2:
                            raise
                        pg.wait_for_timeout(4000 * (_k + 1))
                pg.wait_for_timeout(2500)
                html = pg.content()
                inf = parse_info(html)
                loaded = len(html) > 60000 and ('"%s"' % sku) in html
                if not inf["conf"] and not inf["acc"]:
                    # special-offer items have no page of their own: the offer dialog reads its choices from /api/shelf?Sku=
                    r = self.s.fetch("%s/api/shelf?Sku=%s&sc_lang=en-US&sc_site=%s" % (BASE, sku, "productstoreCa" if REG == "ca" else "productstoreUs"))
                    if r.get("json"):
                        inf = parse_info(json.dumps(r["json"], separators=(",", ":")))
                self.cache[sku] = inf
                if inf.get("conf") or inf.get("acc") or loaded:
                    self.infoc[sku] = {"t": time.time(), "v": inf}
                    csave("info", self.infoc)
            except Exception as e:
                log("  could not read page of item", sku, str(e)[:80])
                self.failed.append(sku)
                self.cache[sku] = {"conf": [], "acc": []}
        return self.cache[sku]

    def cart(self):
        r = self.s.fetch(self.s.cart_url())
        return r.get("json") or {}

    def summary(self):
        js = self.cart()
        sm = (js.get("Data") or {}).get("Summary") or {}
        return js, sm

    def post(self, a, promo_type=False):
        body = {"Sku": a.sku, "Quantity": a.qty, "Configurations": a.conf, "PromotionId": (a.promo if promo_type else ""),
                "LineType": ("Promotion" if promo_type else "Normal"), "LineId": ("" if not promo_type else None), "Position": None}
        r = self.s.fetch(self.s.cart_url(), "POST", body)
        ok = r.get("status") == 200 and (r.get("json") or {}).get("Success")
        try:
            vals = r["json"]["Data"]["Item"].get("Validation") or []
            bad = [v.get("ValidationCode") for v in vals if v.get("Status") == "Critical"]
            if ok and bad:
                ok = False
                a.notes.append("store refused the item: %s" % ", ".join(bad))
        except Exception:
            pass
        line = None
        if ok:
            try:
                line = r["json"]["Data"]["Item"]["Details"]["LineId"]
            except Exception:
                pass
        else:
            a.notes.append("store said: %s" % (str(r.get("json") or r.get("text"))[:200]))
        a.done, a.line = bool(ok), line
        return ok

    def clear(self):
        js = self.cart()
        n = 0
        for it in cart_items(js):
            self.s.remove_line(it["LineId"])
            n += 1
        return n


def coupon_cards(s):
    """opens the cart page, opens 'Your Coupons' and returns the descriptions of the coupons this account has: ['Save $4.50 on Renew Body Wash', ...]"""
    pg = s.page
    pg.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
    s.settle(5000)
    try:
        tg = pg.locator("button.o-accordion__toggler", has_text="Your Coupons").first
        if tg.count() and tg.get_attribute("aria-expanded") != "true":
            tg.click(timeout=8000)
            pg.wait_for_timeout(2500)
    except Exception:
        pass
    out = []
    cards = pg.locator("article.-cartCoupons")
    for i in range(cards.count()):
        try:
            out.append(cards.nth(i).locator(".m-recentProduct__description").first.inner_text().strip())
        except Exception:
            out.append("")
    return out


def coupon_add(s, card_no, qty, product_name):
    """presses the add button of coupon card number card_no, answers the 'Your Choices' dialog if it appears (choice by name, quantity with its + button),
    otherwise presses the card button qty times. Returns (ok, why)"""
    pg = s.page
    qty = max(1, int(qty))
    pg.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
    s.settle(4000)
    tg = pg.locator("button.o-accordion__toggler", has_text="Your Coupons").first
    try:
        if tg.count() and tg.get_attribute("aria-expanded") != "true":
            tg.click(timeout=8000)
            pg.wait_for_timeout(2000)
    except Exception:
        pass
    btn = pg.locator("article.-cartCoupons").nth(card_no).locator("button.-cartCoupon").first
    btn.scroll_into_view_if_needed(timeout=6000)
    btn.click(timeout=8000)
    pg.wait_for_timeout(3000)
    dlg = pg.locator("[role=dialog]:visible")
    if dlg.count():
        d = dlg.first
        tog = d.locator("button.o-accordion__toggler")
        for t in range(tog.count()):              # every 'Choose: ...' box: the option that looks like the product, else the first one
            try:
                if tog.nth(t).get_attribute("aria-expanded") != "true":
                    tog.nth(t).click(timeout=4000)
                    pg.wait_for_timeout(800)
            except Exception:
                pass
        groups = d.locator("ul.o-configuratorAcc__list")
        for g in range(groups.count()):
            opts = groups.nth(g).locator("button.m-refinerImage")
            best, bi = -1.0, 0
            for o in range(opts.count()):
                sc = name_score(product_name, opts.nth(o).inner_text())
                if sc > best:
                    best, bi = sc, o
            if opts.count():
                opts.nth(bi).click(timeout=4000)
                pg.wait_for_timeout(700)
        plus = d.locator("button", has_text=re.compile(r"^\s*add\s*$"))
        for _ in range(qty - 1):
            if plus.count():
                plus.first.click(timeout=4000)
                pg.wait_for_timeout(500)
        d.locator("button", has_text=re.compile(r"add to cart", re.I)).last.click(timeout=8000)
        pg.wait_for_timeout(4000)
    else:
        for _ in range(qty - 1):
            pg.locator("article.-cartCoupons").nth(card_no).locator("button.-cartCoupon").first.click(timeout=8000)
            pg.wait_for_timeout(3000)
    return True, ""


def run(n, dry=False, lab=False, final=True, audit=False):
    import melaleuca_run as mr
    import melaleuca_scan as ms
    from playwright.sync_api import sync_playwright
    plan_path = os.path.join(FEED, "cart_plan_%d.tsv" % n)
    for a in sys.argv:
        if a.startswith("--plan="):
            plan_path = a[7:]
    plan = load_plan(plan_path) if (not audit or os.path.exists(plan_path)) else {"tab": "", "n": n, "credit": 0, "lines": [], "total": None, "groups": {}, "members": [], "cleanpack": {}}
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    tabs = {}
    for ln in open(os.path.join(FEED, "mel_tabs.txt"), encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 3 and p[0].strip().isdigit():
            tabs[int(p[0])] = (p[1], p[2].strip(), p[3].strip().lower() if len(p) > 3 else "")
    an = n                                           # account used to sign in (the test bench signs in with account 7 for any plan)
    for a in sys.argv:
        if a.startswith("--as="):
            an = int(a[5:])
    name, kind, colour = tabs[an]
    region = env.get("REGION_%d" % an, "").strip().lower() or {"orange": "vancouver", "yellow": "toronto"}.get(colour, "socal" if kind == "2" else "vancouver")
    acct = {"tab": name, "n": an, "user": env["MELA_USER_%d" % an], "pass": env["MELA_PASS_%d" % an], "region": region}
    global REG
    REG = "ca" if region in ("vancouver", "toronto") else "us"
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": int(env.get("STICKY_BASE") or 10000), "headless": not (not lab and env.get("FILL_SHOW", "0") in ("1", "true")),     # the scan uses HEADLESS=1; the filler always shows its window (you pay in it)
           "channel": (env.get("BROWSER", "") or "") if lab else (env.get("FILL_BROWSER", "") or "chrome"), "session_minutes": int(env.get("SESSION_MINUTES", "120") or 0), "debug_dir": os.path.join(FEED, "debug"),
           "fast": True, "early_route": True}
    port = None
    try:
        port = json.load(open(os.path.join(FEED, "ip_%d.json" % an))).get("port")
    except Exception:
        pass
    report = []

    def say(*a):
        t = " ".join(str(x) for x in a)
        report.append(t)
        log(t)
    with sync_playwright() as p:
        s = None
        bad_n = 0
        for attempt in range(1, 9):
            try:
                a2 = dict(acct, geo_level=0 if attempt <= 2 else 1, channel_override=(None if attempt % 2 else "chromium"))
                s = ms.Session(p, a2, an, cfg, port if attempt == 1 else (10000 + an + 100 * attempt))
                s.login()
                break
            except ms.BadLogin:
                bad_n += 1
                if bad_n <= 4 and attempt < 8:       # like the offers scan: the store often answers "Invalid Username or Password" to an IP / browser it does not like (a human check in disguise) -> new IP, other browser, longer pause
                    log("sign-in refused (%d of 4) - trying again on a fresh connection and browser (the same account signs in fine at other times)" % bad_n)
                    try:
                        s.close()
                    except Exception:
                        pass
                    time.sleep(15 + 15 * bad_n)
                    continue
                u_, w_ = str(acct.get("user", "")), str(acct.get("pass", ""))
                mask = lambda x: (x[:2] + "*" * max(0, len(x) - 4) + x[-2:]) if len(x) > 4 else "*" * len(x)
                print("")
                print("=" * 78)
                print(" The store REFUSED the sign-in of tab %d (%s)." % (an, acct.get("tab")))
                print("   user name read from credentials.env : %s   (%d characters)" % (mask(u_), len(u_)))
                print("   password read from credentials.env  : %s   (%d characters)" % (mask(w_), len(w_)))
                odd = [n for n, bad in (("a space at the start or end", u_ != u_.strip() or w_ != w_.strip()),
                                         ("a quote character", any(c in u_ + w_ for c in "\"'")),
                                         ("a non-ASCII character", any(ord(c) > 127 for c in u_ + w_))) if bad]
                if odd:
                    print("   WARNING: the user name / password contains " + ", ".join(odd))
                print("   Check the lines MELA_USER_%d= and MELA_PASS_%d= in C:\\AmazonFeed\\credentials.env" % (an, an))
                print("   (tab %d must be the %s coloured tab from the left; Antonio M is 7)." % (an, an))
                print("   Test: sign in at melaleuca.com by hand with exactly these values. It was tried on several fresh connections, then stopped.")
                print("=" * 78)
                raise
            except Exception as e:
                log("sign-in attempt %d failed: %s" % (attempt, str(e)[:100]))
                try:
                    s.close()
                except Exception:
                    pass
                s = None
                if re.search(r"ERR_PROXY|ERR_TUNNEL|ERR_CONNECTION|ERR_TIMED_OUT|ERR_NAME_NOT", str(e)) and attempt < 8:
                    # the PROXY SERVICE (not the store) refused or dropped the connection: trying 7 more ports within 10 seconds only repeats it. Wait, then try again.
                    pause = min(90, 15 * attempt)
                    log("the proxy service refused the connection (not the store) - waiting %d s, then trying again on another port" % pause)
                    time.sleep(pause)
        if s is None:
            raise RuntimeError("could not sign in")
        fl = Filler(s)
        try:
            if audit:
                say("signed in as", name, "- pack audit (no cart is touched)")
                do_audit(fl, say)
                return 0
            say("signed in as", name, "| plan:", len(plan["lines"]), "lines, TOTAL points", plan["total"]["pts"] if plan["total"] else "?", "cost", plan["total"]["ws"] if plan["total"] else "?")
            js, sm = fl.summary()
            items = cart_items(js)
            if items and not dry:
                # always: whatever is in the cart of this account is removed first (never asks)
                say("cart had %d lines (%s points) - emptying it first" % (len(items), sm.get("Points")))
                for _try in range(3):
                    fl.clear()
                    js, sm = fl.summary()
                    items = cart_items(js)
                    if not items:
                        break
                if items:
                    raise RuntimeError("the cart could not be emptied (%d lines left)" % len(items))
                say("cart emptied")
            cat = Catalog(s)
            need = sorted({re.sub(r"\D", "", L["melid"]) for L in plan["lines"] if re.fullmatch(r"[FR]\d+[LH]?", L["melid"] or "")})
            if any(L["qty"] > 0 and L["melid"] and not NUM.match(L["melid"]) and not re.fullmatch(r"[FR]\d+[LH]?", L["melid"]) for L in plan["lines"]):
                need.append("manual")
            if need:
                cat.crawl(need)

            def rv(L):
                sku, why = cat.resolve(L)
                say("  variant: %s (%s) -> %s" % (L["name"][:50], L["melid"], ("%s  %s" % (sku, why)) if sku else "NOT RESOLVED: " + why))
                return sku
            acts, offers, problems, notes = build_actions(plan, fl.info, rv)
            write_audit()
            say("actions:", len(acts), "| offer lines:", len(offers), "| problems:", len(problems))
            for pr in problems:
                say("  PROBLEM:", pr)
            if dry:
                for a in acts:
                    say("  would add [%s] %s x%d %s" % (a.kind, a.sku, a.qty, a.label[:70]))
                    for c in a.notes:
                        say("       choice:", c)
                return 0
            # ---- 0. coupons: the ones this account really has are added from its 'Your Coupons' box at the coupon price
            coupon_lines = [L for L in plan["lines"] if L["qty"] > 0 and (str(L["type"]).strip().lower() == "coupon" or str(L["note"]).strip().lower().startswith("coupon of"))]
            coupon_use = []
            if coupon_lines:
                try:
                    cards = coupon_cards(s)
                except Exception as e:
                    cards = []
                    say("  could not read the coupons box:", str(e)[:100])
                say("coupons of this account:", len(cards), "|", " ; ".join(c[:50] for c in cards))
                for L in coupon_lines:
                    best = (0.0, None)
                    for ci, d in enumerate(cards):
                        title = re.sub(r"^\s*Save\s*\$[\d.,]+\s*(on\s*)?", "", d, flags=re.I)
                        sc = name_score(L["name"], title)
                        if sc > best[0]:
                            best = (sc, ci)
                    if best[1] is not None and best[0] >= 0.5:
                        coupon_use.append((L, best[1], cards[best[1]]))
                    else:
                        msg = "COUPON NOT ON THIS ACCOUNT: '%s' - the sheet counts it at the coupon price (%.0f pts / %.2f), the store charges the normal price (run Scan Account Offers, then Generate All Orders, so the builder knows this account's coupons)." % (L["name"], L["pts"], L["ws"])
                        say("  " + msg)
                        problems.append(msg)
                notes = [n_ for n_ in notes if "coupon line" not in n_]          # the coupon lines are handled here (added from the coupons box, or reported above)
                rows_c = {L["row"] for L, _, _ in coupon_use}
                acts = [a for a in acts if not (a.rows and set(a.rows) <= rows_c and a.kind == "single")]
            # ---- 1. products and packs
            for a in acts:
                ok = fl.post(a)
                say("  %s [%s] %s x%d %s %s" % ("added" if ok else "FAILED", a.kind, a.sku, a.qty, a.label[:55], "" if ok else a.notes[-2:]))
                for c in a.notes:
                    if "->" in c:
                        say("       choice:", c)
            for L, ci, desc in coupon_use:
                ids0 = {str(i["LineId"]) for i in cart_items(fl.cart())}
                try:
                    coupon_add(s, ci, L["qty"], L["name"])
                except Exception as e:
                    say("  coupon button problem:", str(e)[:120])
                new = [i for i in cart_items(fl.cart()) if str(i["LineId"]) not in ids0]
                a = Action("single", "coupon", L["qty"], label="COUPON %s" % desc[:45], rows=[L["row"]], expect_pts=L["pts"], expect_ws=L["ws"])
                a.done = bool(new)
                a.line = str(new[0]["LineId"]) if new else None
                a.extra = [str(i["LineId"]) for i in new[1:]]
                if not new:
                    a.notes.append("the coupon button did not add anything")
                    problems.append("coupon '%s' could not be added: do it by hand from 'Your Coupons' in the cart" % desc[:60])
                acts.append(a)
                say("  %s [coupon] x%d %s" % ("added" if new else "FAILED", L["qty"], desc[:70]))
            # ---- 2. special offers
            js, sm = fl.summary()
            say("cart before the offers:", sm.get("ItemCount"), "items,", sm.get("Points"), "points")
            if offers:
                s.page.goto(BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
                s.settle(8000)
                cards = {}
                for _try in range(3):                           # the offers page can be slow on a slow proxy: wait / reload before giving up
                    if s.last.get("bogo"):
                        r = s.fetch(s.last["bogo"])
                        for c in (r.get("json") or {}).get("Data", {}).get("Cards", []):
                            d = (c.get("InnerData") or {}).get("Data") or {}
                            cards[str(d.get("Sku"))] = d
                    if cards:
                        break
                    say("  offers not loaded yet - trying again (%d/3)" % (_try + 1))
                    s.page.goto(BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
                    s.settle(10000)
                say("offers on the page:", len(cards))
                try:
                    json.dump(cards, open(os.path.join(FEED, "fill_offer_cards_%d.json" % n), "w", encoding="utf-8"), indent=1)
                    json.dump(fl.cache, open(os.path.join(FEED, "fill_info_cache_%d.json" % n), "w", encoding="utf-8"), indent=1)
                except Exception:
                    pass
                for k, d in cards.items():
                    say("     offer card %s | promo %s | %s" % (k, d.get("PromotionId"), (d.get("Title") or "")[:80]))
                by = {}
                for L in offers:
                    by.setdefault(L["offsku"], []).append(L)
                for osku, ls in by.items():
                    d = cards.get(str(osku))
                    if not d:
                        problems.append("offer %s (%s) is not on the Special Offers page of this account" % (osku, ls[0]["name"]))
                        say("  PROBLEM: offer", osku, "not on the page")
                        continue
                    ou = max(1, ls[0]["offunits"] or 1)
                    units = []
                    for L in ls:
                        units += [(L["name"], L["melid"])] * L["qty"]
                    red = max(1, len(units) // ou)
                    inf = fl.info(osku)
                    for i in range(red):
                        chunk = units[i * ou:(i + 1) * ou]
                        conf, pr, ch = ([], [], [])
                        if any(c["type"] == "FSKU" for c in inf["conf"]):
                            conf, pr, ch = assign_choices(chunk, inf["conf"])
                            problems += ["offer %s: %s" % (osku, x) for x in pr]
                        a = Action("offer", osku, 1, conf, promo=d.get("PromotionId"), label=d.get("Title") or "", rows=[L["row"] for L in ls],
                                   expect_pts=sum(L["pts"] for L in ls) / red, expect_ws=sum(L["ws"] for L in ls) / red)
                        ok = fl.post(a, promo_type=True)
                        say("  %s offer %s x1 %s %s" % ("added" if ok else "FAILED", osku, (d.get("Title") or "")[:55], json.dumps(conf)[:100] if conf else ""))
                        if not ok:
                            say("      ", a.notes[-2:])
                        acts.append(a)
            try:
                json.dump(fl.cache, open(os.path.join(FEED, "fill_info_cache_%d.json" % n), "w", encoding="utf-8"), indent=1)
            except Exception:
                pass
            # ---- 2b. the account credit: the box "Buy with Loyalty Shopping Dollars" on the lines the sheet marks Credit 1 / Credit 2
            adjusted = []
            credit_rows = sorted({(str(L["type"]), L["row"]) for L in plan["lines"] if L["qty"] > 0 and str(L["type"]).lower().startswith("credit")})
            credit_done, credit_fail = set(), []
            for ctype, crow in credit_rows:
                tgt = next((a for a in acts if crow in a.rows and a.done and a.line is not None), None)
                if tgt is None:
                    credit_fail.append("%s (row %d): the product is not in the cart" % (ctype, crow))
                    continue
                try:
                    r = s.fetch(s.cart_url().replace("/api/cart?", "/api/cart/linetype?"), "POST", {"LineId": str(tgt.line), "LineType": "LSD", "Quantity": int(tgt.qty)})
                    res = ((r.get("json") or {}).get("Data") or {}).get("linesResults") or []
                    if r.get("status") == 200 and (r.get("json") or {}).get("Success") and res and not res[0].get("validationItems"):
                        tgt.line = str(res[0].get("lineId", tgt.line))
                        credit_done.add(crow)
                        say("  credit  : %s -> box 'Buy with Loyalty Shopping Dollars' ticked on %s" % (ctype, tgt.label[:55]))
                    else:
                        credit_fail.append("%s (row %d): the store did not accept it: %s" % (ctype, crow, str(r.get("json"))[:160]))
                except Exception as e:
                    credit_fail.append("%s (row %d): %s" % (ctype, crow, str(e)[:100]))
            if credit_fail and any("the product is not in the cart" not in c_ for c_ in credit_fail):
                # the store refuses the credit on that product (e.g. 'NotLSDEligible'): the credit goes on another product of the cart that takes it,
                # the one whose points are closest to the refused one (and at least as many, so the 150 limit still holds)
                used_lines = {str(a_.line) for a_ in acts if any(r_ in credit_done for r_ in a_.rows) and a_.line is not None}
                for c in list(credit_fail):
                    m_ = re.search(r"\(row (\d+)\)", c)
                    if not m_ or "the product is not in the cart" in c:
                        continue
                    crow = int(m_.group(1))
                    want = next((L["pts"] for L in plan["lines"] if L["row"] == crow), 0.0)
                    js_now, _sm = fl.summary()
                    cands = []
                    for it in cart_items(js_now):
                        lid = str(it.get("LineId"))
                        if lid in used_lines or str(it.get("LineType") or "").upper() == "LSD":
                            continue
                        ipts = f2(it.get("RawPoints"))
                        if ipts <= 0:
                            continue
                        cands.append((0 if ipts >= want else 1, abs(ipts - want), lid, it))
                    cands.sort(key=lambda x: (x[0], x[1]))
                    moved = False
                    for _a, _b, lid, it in cands[:8]:
                        try:
                            r = s.fetch(s.cart_url().replace("/api/cart?", "/api/cart/linetype?"), "POST", {"LineId": lid, "LineType": "LSD", "Quantity": int(f2(it.get("Quantity")) or 1)})
                            res = ((r.get("json") or {}).get("Data") or {}).get("linesResults") or []
                            if r.get("status") == 200 and (r.get("json") or {}).get("Success") and res and not res[0].get("validationItems"):
                                used_lines.add(lid)
                                credit_done.add(crow)
                                credit_fail.remove(c)
                                msg_ = "the store does not take the credit on the sheet's product (row %d); the credit went on '%s' instead" % (crow, str(it.get("Title") or it.get("Name") or lid)[:50])
                                say("  CREDIT MOVED:", msg_)
                                adjusted.append(msg_)
                                moved = True
                                break
                        except Exception:
                            pass
                    if not moved:
                        say("  (no other product of the cart takes the credit either)")
                        if any("NotLSDEligible" in c_ for c_ in credit_fail) and credit_done:
                            credit_fail[credit_fail.index(c)] = c + " | the first credit line already used up the account's credit, so nothing is left for this one: tick it by hand if the checkout still offers loyalty dollars"
            for c in credit_fail:
                say("  CREDIT PROBLEM:", c)
                problems.append("credit: " + c)
            for a in acts:
                if any(r_ in credit_done for r_ in a.rows) and a.kind in ("single", "pack") and a.line is not None and not a.label.lower().find(" for ") > 0:
                    a.expect_pts = 0.0          # a line bought with the credit counts 0 points
            # ---- 3. check against the sheet
            js, sm = fl.summary()
            pts, cnt = f2(sm.get("Points")), sm.get("ItemCount")
            net = f2(sm.get("CartGrossTotal"))
            say("\nCART NOW: %s items | %.0f points | gross %s | net %s | discount %s" % (cnt, pts, sm.get("CartGrossTotal"), sm.get("CartNetTotal"), sm.get("TotalDiscount")))
            exp_pts_all = sum(L["pts"] for L in plan["lines"] if L["qty"] > 0)
            exp_pts = sum(L["pts"] for L in plan["lines"] if L["qty"] > 0 and L["row"] not in credit_done)       # points that count for the 150 limit (credit lines bought with the credit count 0)
            exp_ws = sum(L["ws"] for L in plan["lines"] if L["qty"] > 0)
            credit_pts = sum(L["pts"] for L in plan["lines"] if L["qty"] > 0 and str(L["type"]).lower().startswith("credit"))
            say("SHEET   : %.0f points count for the limit (TOTAL row: %s) + %.0f points of credit items | cost of all lines %.2f" % (
                exp_pts, ("%.0f" % plan["total"]["pts"]) if plan["total"] else "?", credit_pts, exp_ws))
            say("CREDIT  : %s of loyalty dollars used by the cart" % ((sm.get("LoyaltyShoppingDollars") or {}).get("FormattedUsed") or "?"))
            cad = (REG == "ca")                    # a Canadian store charges Canadian dollars, the sheet counts US dollars: only the POINTS can be compared
            ok_pts, ok_cost = abs(pts - exp_pts) < 0.5, (cad or abs(net - exp_ws) < 0.05)
            say("RESULT  : points %s | cost %s" % ("MATCH" if ok_pts else "DIFFER by %+.0f" % (pts - exp_pts), ("not compared (Canadian dollars in the store, US dollars in the sheet)" if cad else ("MATCH" if ok_cost else "DIFFER by %+.2f" % (net - exp_ws)))))
            by_line = {str(it.get("LineId")): it for it in cart_items(js)}
            # actions that share a sheet row or a cart line belong together (a pack and its bottles, ...): compared as one block
            parent = list(range(len(acts)))

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            seen_key = {}
            for i, a in enumerate(acts):
                for key in [("row", r) for r in a.rows] + ([("line", str(a.line))] if a.line is not None else []):
                    if key in seen_key:
                        parent[find(i)] = find(seen_key[key])
                    else:
                        seen_key[key] = i
            blocks = {}
            for i, a in enumerate(acts):
                blocks.setdefault(find(i), []).append(a)
            diffs, pump_extra, pump_notes = [], 0.0, []
            for aa in blocks.values():
                ep, ew = sum(a.expect_pts for a in aa), sum(a.expect_ws for a in aa)
                lids = {str(x) for a in aa for x in ([a.line] + list(a.extra)) if x is not None}
                missing = [a for a in aa if not a.done]
                ap = sum(f2(by_line[l].get("RawPoints")) for l in lids if l in by_line)
                aw = sum(f2(by_line[l].get("RawPrice")) for l in lids if l in by_line)
                name = " + ".join(sorted({a.label for a in aa}))[:70]
                if missing:
                    diffs.append("%s: NOT ADDED (%s)" % (name, " | ".join(missing[0].notes[-2:] or ["?"])[:300]))
                elif not cad and abs(ap - ep) < 0.5 and aw > ew + 0.05 and any("pump" in a.label.lower() for a in aa):
                    pump_extra += aw - ew          # the sheet does not price the pump (0 points); the store does
                    pump_notes.append("%s: the pump costs %.2f in the store, the sheet does not count it" % (name, aw - ew))
                elif abs(ap - ep) > 0.5 or (not cad and abs(aw - ew) > 0.05):
                    diffs.append("%s: sheet %.0f pts / %.2f  -  store %.0f pts / %.2f" % (name, ep, ew, ap, aw))
            for d in diffs:
                say("  DIFFERENCE:", d)
            for d in pump_notes:
                say("  NOTE:", d)
            if not diffs and ok_pts and ok_cost:
                say("  every line of the cart equals the sheet.")
            for nn in notes:
                say("  NOTE:", nn)
            if pts > 150.0001 and os.environ.get("FILL_AUTOFIT", "1") != "0":
                # the store charges more points than the sheet expected (a coupon this account does not have): take units off the line that causes it
                # until the cart is back under the limit (target 148, the same band as the order builder). Only a plain item with quantity 2 or more is touched.
                try:
                    cand = []
                    for aa in blocks.values():
                        ep = sum(a.expect_pts for a in aa)
                        lids = {str(x) for a in aa for x in ([a.line] + list(a.extra)) if x is not None}
                        ap = sum(f2(by_line[l].get("RawPoints")) for l in lids if l in by_line)
                        singles = [a for a in aa if a.kind == "single" and a.line is not None and a.qty >= 2 and not any(r_ in credit_done for r_ in a.rows)]
                        if ap - ep > 0.5 and len(singles) == 1 and len(aa) == 1:
                            cand.append((ap - ep, ap, singles[0]))
                    cand.sort(key=lambda t: -t[0])
                    for excess, ap, a in cand:
                        if pts <= 150.0001:
                            break
                        unit = ap / a.qty
                        need = int(-(-(pts - 148.0) // unit)) if unit > 0 else 0       # ceil
                        k = max(1, min(a.qty - 1, need))
                        old_q = a.qty
                        s.remove_line(a.line)
                        a.qty = old_q - k
                        if fl.post(a):
                            adjusted.append("%s: quantity %d -> %d (the store gives it %.0f points per unit; the sheet expected a coupon price)" % (a.label[:50], old_q, a.qty, unit))
                            say("  AUTO-ADJUSTED:", adjusted[-1])
                        else:
                            say("  AUTO-ADJUST FAILED for", a.label[:50], "- put it back by hand: quantity", old_q)
                            problems.append("put %s back to quantity %d (the automatic reduction failed)" % (a.label[:50], old_q))
                        js, sm = fl.summary()
                        pts = f2(sm.get("Points"))
                        net = f2(sm.get("CartGrossTotal"))
                        by_line = {str(it.get("LineId")): it for it in cart_items(js)}
                    say("CART AFTER THE ADJUSTMENT: %s items | %.0f points | gross %s" % (sm.get("ItemCount"), pts, sm.get("CartGrossTotal")))
                except Exception as e:
                    say("automatic reduction failed:", str(e)[:120])
            if pts > 150.0001:
                say("")
                say("!" * 78)
                say("!!  THIS CART HAS %.0f POINTS - OVER THE 150 LIMIT (the sheet expected %.0f)." % (pts, exp_pts))
                say("!!  Look at the DIFFERENCE lines above: that is where the extra points come from.")
                say("!" * 78)
            result = {"match": bool(ok_pts and ok_cost), "cart_points": pts, "sheet_points": exp_pts, "cart_cost": net, "sheet_cost": exp_ws, "differences": diffs}
            try:                                              # the reports are only for me: a failure here must never stop the browser window
                os.makedirs(FEED, exist_ok=True)
                json.dump(result, open(os.path.join(FEED, "fill_result_%d.json" % n), "w", encoding="utf-8"), indent=1)
                open(os.path.join(FEED, "fill_report_%d.txt" % n), "w", encoding="utf-8").write("\n".join(report))
                json.dump(js, open(os.path.join(FEED, "fill_cart_%d.json" % n), "w", encoding="utf-8"))
            except Exception as e:
                say("could not save the report files:", str(e)[:120])
            # ---- 4. the checkout screen (never pays, never places the order)
            if final and lab:                                  # (a real fill opens the checkout in the visible window below - no need to do it twice)
                try:
                    s.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                    s.settle(5000)
                    b = s.page.locator("button:visible, a:visible").filter(has_text=re.compile(r"^\s*proceed to checkout\s*$", re.I))
                    if b.count():
                        b.first.click(timeout=15000)
                        s.settle(8000)
                    say("page:", s.page.url[:90])
                    b = s.page.locator("button:visible, a:visible").filter(has_text=re.compile(r"^\s*continue to checkout\s*$", re.I))
                    if b.count():
                        b.first.click(timeout=15000)
                        s.settle(9000)
                    say("page:", s.page.url[:90])
                    s.page.screenshot(path=os.path.join(FEED, "fill_final_%d.png" % n), full_page=True)
                    open(os.path.join(FEED, "fill_final_%d.txt" % n), "w", encoding="utf-8").write(" ".join(s.page.inner_text("body", timeout=8000).split())[:4000])
                except Exception as e:
                    say("could not reach the checkout screen:", str(e)[:150])
            if lab and "--persist-test" in sys.argv:          # lab only: does the cart survive for a second sign-in?
                try:
                    s2 = ms.Session(p, a2, an, cfg, port)
                    s2.login()
                    f2_ = Filler(s2)
                    say("PERSIST: second browser sees the cart:", len(cart_items(f2_.cart())), "lines, points", f2_.summary()[1].get("Points"))
                    s.close()
                    for w in (5, 25):
                        time.sleep(w)
                        say("PERSIST: after the first browser closed (+%ds):" % w, len(cart_items(f2_.cart())), "lines")
                    s2.close()
                    say("PERSIST: every browser closed; signing in again after 20 s")
                    time.sleep(20)
                    s3 = ms.Session(p, a2, an, cfg, port)
                    s3.login()
                    f3_ = Filler(s3)
                    say("PERSIST: brand-new browser after all were closed sees:", len(cart_items(f3_.cart())), "lines")
                    try:
                        s3.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                        s3.settle(6000)
                        tx = " ".join(s3.page.inner_text("body", timeout=8000).split())
                        i = tx.lower().find("cart")
                        say("PERSIST: what the /cart page shows to the new browser:", ("EMPTY MESSAGE FOUND" if "empty" in tx.lower() else "no 'empty' text"), "|", tx[tx.lower().find("shopping cart"):][:300] if "shopping cart" in tx.lower() else tx[600:900])
                        s3.page.screenshot(path=os.path.join(FEED, "persist_cart_page.png"), full_page=False)
                    except Exception as e:
                        say("PERSIST cart page failed:", str(e)[:150])
                    say("PERSIST: lab emptied:", f3_.clear())
                    s3.close()
                except Exception as e:
                    say("PERSIST test failed:", str(e)[:200])
                return 0
            if lab:
                s.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                say("lab: emptied the cart again:", fl.clear(), "lines")
                return 0
            # ---- 5. everything was done in the hidden window: now open YOUR browser window straight on the checkout screen
            say("")
            say("proxy traffic of this fill: about %.1f MB" % (s.bytes / 1048576.0))
            say("THE CART IS FILLED. Opening your browser window on the checkout screen now (about 20-40 seconds) ...")
            v = None
            try:
                _light = env.get("FINAL_IMAGES", "0").strip().lower() not in ("1", "true", "yes")      # default: the checkout window loads NO pictures / videos / fonts / trackers through the proxy (they cost credits and are not needed to pay)
                vcfg = dict(cfg, headless=False, fast=_light, early_route=_light, proxy=(cfg.get("proxy") if env.get("FINAL_PROXY", "1").strip().lower() not in ("0", "false", "no") else ""))        # default: the window keeps the account's own proxy IP (never your own IP); FINAL_PROXY=0 in credentials.env = your own connection
                v = ms.Session(p, a2, an, vcfg, port)
                if _light:
                    v.ctx.route("**/*", v._route)          # also after the cookies are copied (no sign-in = the sign-in code that sets this up is not run)
                try:                                           # same proxy IP + the cookies of the hidden window = already signed in, no second login
                    v.ctx.add_cookies(s.ctx.storage_state().get("cookies", []))
                except Exception as e:
                    say("  (cookie copy failed:", str(e)[:80], ")")
                v.page.goto(BASE + "/checkout?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                v.settle(4000)
                if re.search(r"login|signin|sign-in|account/log", v.page.url, re.I) or v.page.locator("input[name=username]:visible").count():
                    say("  window was not signed in - signing in ...")
                    v.login()
                    v.page.goto(BASE + "/checkout?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                    v.settle(5000)
                if "promo-page" in v.page.url:
                    b = v.page.locator("button:visible, a:visible").filter(has_text=re.compile(r"^\s*continue to checkout\s*$", re.I))
                    if b.count():
                        b.first.click(timeout=15000)
                        v.settle(6000)
                say("page:", v.page.url[:90])
            except Exception as e:
                say("could not open the visible window:", str(e)[:150], "- sign in to the store by hand: the cart is saved on the account")
                v = None
            try:
                s.close()
            except Exception:
                pass
            print("\n==============================================================================")
            print(" Cart of '%s' is ready on the checkout screen of your browser window." % name)
            print(" %.0f points | %s of loyalty dollars used | nothing was paid, no order was placed." % (pts, (sm.get("LoyaltyShoppingDollars") or {}).get("FormattedUsed") or "$0.00"))
            for ad in adjusted:
                print("  AUTO-ADJUSTED:", ad)
            for fx in FIXED_SKUS:
                print("  SKU CORRECTED:", fx)
            for sk_ in fl.failed:
                problems.append("the store page of item %s could not be read (connection) - its choices may be missing, check that line" % sk_)
            for pn in problems:
                print("  TO DO BY HAND:", pn)
            if pts > 150.0001:
                print("  !! OVER THE 150 POINT LIMIT - see the DIFFERENCE lines above before you pay")
            print(" Check it, pay yourself, then close the window (this black window closes after it).")
            print("==============================================================================")
            if "--window-test" in sys.argv and v is not None:       # lab: look at the window once and finish (nobody is there to close it)
                try:
                    v.page.screenshot(path=os.path.join(FEED, "fill_window_%d.png" % n), full_page=False)
                    say("WINDOW TEST: url", v.page.url[:90], "|", " ".join(v.page.inner_text("body", timeout=8000).split())[:400])
                    v.close()
                except Exception as e:
                    say("window test:", str(e)[:120])
                return 0
            if v is None:
                try:
                    input(" Press Enter to close this window ...")
                except Exception:
                    pass
            while v is not None:
                try:
                    if not v.browser.is_connected() or not v.page.context.pages:
                        break
                    v.page.wait_for_timeout(1500)
                except Exception:
                    break
            return 0
        finally:
            try:
                if lab and not dry:
                    done_ = False
                    for _k in range(4):
                        try:
                            left = fl.clear()
                            if left:
                                log("lab cleanup: removed", left, "lines")
                            done_ = True
                            break
                        except Exception as e:
                            log("lab cleanup attempt %d failed: %s" % (_k + 1, str(e)[:80]))
                            time.sleep(8 * (_k + 1))
                    if not done_:
                        log("LAB CLEANUP PROBLEM - empty the cart of the test account by hand")
                    s.close()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    n = int(sys.argv[1])
    try:
        rc = run(n, dry="--dry" in sys.argv, lab="--lab" in sys.argv, final="--nofinal" not in sys.argv, audit="--audit" in sys.argv)
    except Exception:
        traceback.print_exc()
        rc = 1
    sys.exit(rc)
