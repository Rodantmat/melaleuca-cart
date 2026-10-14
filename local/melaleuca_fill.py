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
            problems.append("no choice found for '%s' (%s)" % (nm, mel))
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
        self.varc = cload("variants", 7)
        self.var = {k: e["v"] for k, e in self.varc.items()}
        self.crawled = False
        ALL_CARDS.update((self.famc.get("cards") or {}).get("v") or {})

    def crawl(self, need):
        if self.crawled:
            return
        if self.fam and ALL_CARDS and all(f in self.fam for f in need if f != "manual"):
            log("  catalog from the saved copy: %d families (no need to read the store)" % len(self.fam))
            return
        self.crawled = True
        pg = self.s.page
        for cat in CATEGORIES:
            if need and all((f in self.fam) for f in need if f != "manual") and "manual" not in need:
                break
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
        csave("family_map", {"all": {"t": now, "v": self.fam}, "cards": {"t": now, "v": ALL_CARDS}})

    def variants(self, fid):
        if fid in self.var:
            return self.var[fid]
        f = self.fam.get(fid)
        out = []
        if f:
            try:
                self.s.page.goto(BASE + f["pdp"] + ("&" if "?" in f["pdp"] else "?") + "sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
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
        for k, c in ALL_CARDS.items():
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

    def info(self, sku):
        sku = str(sku)
        if sku not in self.cache:
            pg = self.s.page
            try:
                pg.goto("%s/products/%s?sc_lang=en-US" % (BASE, sku), wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(2500)
                html = pg.content()
                inf = parse_info(html)
                loaded = len(html) > 60000 and ('"%s"' % sku) in html
                if not inf["conf"] and not inf["acc"]:
                    # special-offer items have no page of their own: the offer dialog reads its choices from /api/shelf?Sku=
                    r = self.s.fetch("%s/api/shelf?Sku=%s&sc_lang=en-US&sc_site=productstoreUs" % (BASE, sku))
                    if r.get("json"):
                        inf = parse_info(json.dumps(r["json"], separators=(",", ":")))
                self.cache[sku] = inf
                if inf.get("conf") or inf.get("acc") or loaded:
                    self.infoc[sku] = {"t": time.time(), "v": inf}
                    csave("info", self.infoc)
            except Exception as e:
                log("  could not read page of item", sku, str(e)[:80])
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


def run(n, dry=False, lab=False, final=True):
    import melaleuca_run as mr
    import melaleuca_scan as ms
    from playwright.sync_api import sync_playwright
    plan_path = os.path.join(FEED, "cart_plan_%d.tsv" % n)
    for a in sys.argv:
        if a.startswith("--plan="):
            plan_path = a[7:]
    plan = load_plan(plan_path)
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
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": int(env.get("STICKY_BASE") or 10000), "headless": bool(lab) or env.get("HEADLESS", "0") in ("1", "true"),
           "channel": env.get("BROWSER", "") or "", "session_minutes": int(env.get("SESSION_MINUTES", "120") or 0), "debug_dir": os.path.join(FEED, "debug"),
           "fast": bool(lab)}
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
        for attempt in range(1, 6):
            try:
                a2 = dict(acct, geo_level=0 if attempt <= 2 else 1, channel_override=(None if attempt % 2 else "chromium"))
                s = ms.Session(p, a2, an, cfg, port if attempt == 1 else (10000 + an + 100 * attempt))
                s.login()
                break
            except ms.BadLogin:
                raise
            except Exception as e:
                log("sign-in attempt %d failed: %s" % (attempt, str(e)[:100]))
                try:
                    s.close()
                except Exception:
                    pass
                s = None
        if s is None:
            raise RuntimeError("could not sign in")
        fl = Filler(s)
        try:
            say("signed in as", name, "| plan:", len(plan["lines"]), "lines, TOTAL points", plan["total"]["pts"] if plan["total"] else "?", "cost", plan["total"]["ws"] if plan["total"] else "?")
            js, sm = fl.summary()
            items = cart_items(js)
            if items and not dry:
                if lab or os.environ.get("FILL_CLEAR") == "1":
                    say("cart had %d lines - emptied (lab)" % fl.clear())
                else:
                    print("\nThe cart of this account is NOT empty (%d lines, %s points)." % (len(items), sm.get("Points")))
                    ans = input("Type E and Enter to EMPTY it and fill it with this order, or just Enter to stop: ").strip().lower()
                    if ans != "e":
                        say("stopped: cart not empty")
                        return 3
                    say("cart emptied:", fl.clear(), "lines")
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
            say("actions:", len(acts), "| offer lines:", len(offers), "| problems:", len(problems))
            for pr in problems:
                say("  PROBLEM:", pr)
            if dry:
                for a in acts:
                    say("  would add [%s] %s x%d %s" % (a.kind, a.sku, a.qty, a.label[:70]))
                    for c in a.notes:
                        say("       choice:", c)
                return 0
            # ---- 1. products and packs
            for a in acts:
                ok = fl.post(a)
                say("  %s [%s] %s x%d %s %s" % ("added" if ok else "FAILED", a.kind, a.sku, a.qty, a.label[:55], "" if ok else a.notes[-1:]))
                for c in a.notes:
                    if "->" in c:
                        say("       choice:", c)
            # ---- 2. special offers
            js, sm = fl.summary()
            say("cart before the offers:", sm.get("ItemCount"), "items,", sm.get("Points"), "points")
            if offers:
                s.page.goto(BASE + "/checkout/promo-page", wait_until="domcontentloaded", timeout=60000)
                s.settle(8000)
                cards = {}
                if s.last.get("bogo"):
                    r = s.fetch(s.last["bogo"])
                    for c in (r.get("json") or {}).get("Data", {}).get("Cards", []):
                        d = (c.get("InnerData") or {}).get("Data") or {}
                        cards[str(d.get("Sku"))] = d
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
                            say("      ", a.notes[-1:])
                        acts.append(a)
            try:
                json.dump(fl.cache, open(os.path.join(FEED, "fill_info_cache_%d.json" % n), "w", encoding="utf-8"), indent=1)
            except Exception:
                pass
            # ---- 3. check against the sheet
            js, sm = fl.summary()
            pts, cnt = f2(sm.get("Points")), sm.get("ItemCount")
            net = f2(sm.get("CartNetTotal"))
            say("\nCART NOW: %s items | %.0f points | gross %s | net %s | discount %s" % (cnt, pts, sm.get("CartGrossTotal"), sm.get("CartNetTotal"), sm.get("TotalDiscount")))
            exp_pts = sum(L["pts"] for L in plan["lines"] if L["qty"] > 0)
            exp_ws = sum(L["ws"] for L in plan["lines"] if L["qty"] > 0)
            credit_pts = sum(L["pts"] for L in plan["lines"] if L["qty"] > 0 and str(L["type"]).lower().startswith("credit"))
            say("SHEET   : all lines %.0f points | %.2f cost   (TOTAL row: %s points counted for the order limit + %.0f points of credit items)" % (
                exp_pts, exp_ws, ("%.0f" % plan["total"]["pts"]) if plan["total"] else "?", credit_pts))
            ok_pts, ok_cost = abs(pts - exp_pts) < 0.5, abs(net - exp_ws) < 0.05
            say("RESULT  : points %s | cost %s" % ("MATCH" if ok_pts else "DIFFER by %+.0f" % (pts - exp_pts), "MATCH" if ok_cost else "DIFFER by %+.2f" % (net - exp_ws)))
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
                lids = {str(a.line) for a in aa if a.line is not None}
                missing = [a for a in aa if not a.done]
                ap = sum(f2(by_line[l].get("RawPoints")) for l in lids if l in by_line)
                aw = sum(f2(by_line[l].get("RawPrice")) for l in lids if l in by_line)
                name = " + ".join(sorted({a.label for a in aa}))[:70]
                if missing:
                    diffs.append("%s: NOT ADDED (%s)" % (name, (missing[0].notes[-1:] or ["?"])[0]))
                elif abs(ap - ep) < 0.5 and aw > ew + 0.05 and any("pump" in a.label.lower() for a in aa):
                    pump_extra += aw - ew          # the sheet does not price the pump (0 points); the store does
                    pump_notes.append("%s: the pump costs %.2f in the store, the sheet does not count it" % (name, aw - ew))
                elif abs(ap - ep) > 0.5 or abs(aw - ew) > 0.05:
                    diffs.append("%s: sheet %.0f pts / %.2f  -  store %.0f pts / %.2f" % (name, ep, ew, ap, aw))
            for d in diffs:
                say("  DIFFERENCE:", d)
            for d in pump_notes:
                say("  NOTE:", d)
            if not diffs and ok_pts and ok_cost:
                say("  every line of the cart equals the sheet.")
            for nn in notes:
                say("  NOTE:", nn)
            result = {"match": bool(ok_pts and ok_cost), "cart_points": pts, "sheet_points": exp_pts, "cart_cost": net, "sheet_cost": exp_ws, "differences": diffs}
            json.dump(result, open(os.path.join(FEED, "fill_result_%d.json" % n), "w", encoding="utf-8"), indent=1)
            os.makedirs(FEED, exist_ok=True)
            open(os.path.join(FEED, "fill_report_%d.txt" % n), "w", encoding="utf-8").write("\n".join(report))
            json.dump(js, open(os.path.join(FEED, "fill_cart_%d.json" % n), "w"))
            # ---- 4. the checkout screen (never pays, never places the order)
            if final:
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
            if lab:
                s.page.goto(BASE + "/cart?sc_lang=en-US", wait_until="domcontentloaded", timeout=60000)
                say("lab: emptied the cart again:", fl.clear(), "lines")
                return 0
            print("\n==============================================================================")
            print(" Cart of '%s' is ready. CHECK it in the browser window and pay yourself." % name)
            print(" Nothing was paid and no order was placed. Close the browser window when done.")
            print("==============================================================================")
            while True:
                try:
                    if not s.browser.is_connected() or not s.page.context.pages:
                        break
                    s.page.wait_for_timeout(1500)
                except Exception:
                    break
            return 0
        finally:
            try:
                if lab:
                    try:
                        left = fl.clear()
                        if left:
                            log("lab cleanup: removed", left, "lines")
                    except Exception as e:
                        log("LAB CLEANUP PROBLEM - empty the cart of the test account by hand:", str(e)[:100])
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
        rc = run(n, dry="--dry" in sys.argv, lab="--lab" in sys.argv, final="--nofinal" not in sys.argv)
    except Exception:
        traceback.print_exc()
        rc = 1
    sys.exit(rc)
