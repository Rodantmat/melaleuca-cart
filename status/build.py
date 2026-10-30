"""build.py - turns the scraped orders into the three status pages.
  python build.py full   --in DIR --site SITE_DIR [--month YYYY-MM]    orders from scrape.py + carrier status of every package
  python build.py status --site SITE_DIR                               same tracking numbers as before, only the carrier status is refreshed (fast)
Pages: <SITE>/<token>/index.html + data.json for  main / toronto / vancouver.  token = HMAC(STATUS_SALT, view): not guessable, not stored in the repo.
Environment: STATUS_SALT (secret), SHIPPO_LIVE_TOKEN (secret)."""
import concurrent.futures as cf, datetime as dt, glob, hashlib, hmac, json, os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import carriers as C

VIEWS = ("main", "toronto", "vancouver")
MIN_ACCOUNTS = 8             # a month counts as "the batch" when at least this many accounts have an order in it


def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def token(view):
    salt = os.environ.get("STATUS_SALT", "").strip()
    if not salt: raise SystemExit("STATUS_SALT secret is missing (Settings > Secrets and variables > Actions)")
    return hmac.new(salt.encode(), view.encode(), hashlib.sha256).hexdigest()[:20]


def batch_month(accts, forced=None):
    if forced: return forced
    per = {}
    for a in accts:
        for o in a.get("orders", []):
            per.setdefault(o["date"][:7], set()).add(a["an"])
    ok = sorted(m for m, s in per.items() if len(s) >= MIN_ACCOUNTS)
    if ok: return ok[-1]
    return max(per) if per else dt.date.today().strftime("%Y-%m")


def title(s): return " ".join(w.capitalize() for w in (s or "").lower().split())


def rows_from(accts, month):
    rows = []
    for a in accts:
        if not a.get("ok"): continue
        reg = {"vancouver": "Vancouver", "toronto": "Toronto"}.get(a["region"], "US")
        for o in a["orders"]:
            if o["date"][:7] != month: continue
            base = {"account": a["tab"], "region": reg, "name": title(o.get("name")) or a["tab"], "city": title(o.get("city")), "state": (o.get("state") or "").upper(),
                    "order_date": o["date"], "order_no": o["number"], "order_status": o.get("status", "")}
            if not o["packages"]:
                rows.append(dict(base, tracking="", carrier="", carrier_name="", link="", status="NONE", status_text=o.get("status") or "Not shipped yet",
                                 detail="no tracking number yet", location="", eta="", delivered_at="", last_update="", checked=""))
                continue
            for p in o["packages"]:
                car = C.detect(p["n"], p.get("href", ""))
                rows.append(dict(base, tracking=p["n"], carrier=car, carrier_name=C.NAMES.get(car, car), link=C.link(car, p["n"]),
                                 status="", status_text="", detail="", location="", eta="", delivered_at="", last_update="", checked=""))
    return rows


def refresh_status(rows, only_open=True):
    token_ = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip()
    todo = [r for r in rows if r["tracking"] and not (only_open and r.get("status") == "DELIVERED")]
    def one(r):
        res = C.lookup(r["carrier"], r["tracking"], token_)
        # keep the last good information when the carrier gives nothing this time
        if res["status"] == "UNKNOWN" and r.get("status") not in ("", "UNKNOWN", None, "NONE"):
            return r, None
        return r, res
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r, res in ex.map(one, todo):
            if res: r.update(res)
    return len(todo)


def counts(rows):
    c = {}
    for r in rows: c[r["status"] or "UNKNOWN"] = c.get(r["status"] or "UNKNOWN", 0) + 1
    return c


def write_site(site, data, template):
    html = open(template, encoding="utf-8").read()
    keep = set()
    for view in VIEWS:
        rows = data["rows"] if view == "main" else [r for r in data["rows"] if r["region"].lower() == view]
        d = dict(data, rows=rows, scope=view)
        if view != "main": d.pop("failed_accounts", None)
        folder = os.path.join(site, token(view)); os.makedirs(folder, exist_ok=True); keep.add(os.path.basename(folder))
        with open(os.path.join(folder, "data.json"), "w", encoding="utf-8") as f: json.dump(d, f, separators=(",", ":"))
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(html.replace("__PAGE_PAT__", os.environ.get("PAGE_PAT", "").strip() if view == "main" else "").replace("__VIEW__", view).replace("__TITLE__", {"main": "Melaleuca orders - tracking", "toronto": "Toronto - tracking", "vancouver": "Vancouver - tracking"}[view]))
    for x in os.listdir(site):                            # folders of older salts / views are removed
        p = os.path.join(site, x)
        if os.path.isdir(p) and x not in keep and not x.startswith("."): shutil.rmtree(p)
    for fn, body in (("index.html", '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><title>.</title>'), (".nojekyll", ""), ("robots.txt", "User-agent: *\nDisallow: /\n")):
        with open(os.path.join(site, fn), "w", encoding="utf-8") as f: f.write(body)


def load_prev(site):
    p = os.path.join(site, token("main"), "data.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def main():
    mode = sys.argv[1]
    dry = "--dry" in sys.argv
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    site = arg("--site"); template = os.path.join(HERE, "site", "index.html")
    prev = None if dry else load_prev(site)
    if mode == "full":
        accts = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(arg("--in"), "acct_*.json")))]
        failed = [a["tab"] for a in accts if not a.get("ok")]
        month = batch_month([a for a in accts if a.get("ok")], arg("--month"))
        rows = rows_from(accts, month)
        # an account that could not be read this time keeps its previous rows (marked old), so one bad sign-in never empties the page
        if prev and failed:
            keep = [r for r in prev["rows"] if r["account"] in failed and r["order_date"][:7] == month]
            rows += keep
        # carry the known status of a package whose tracking number is unchanged (a delivered package is not asked again)
        old = {(r["order_no"], r["tracking"]): r for r in (prev["rows"] if prev else [])}
        for r in rows:
            o = old.get((r["order_no"], r["tracking"]))
            if o and o.get("status") == "DELIVERED": r.update({k: o[k] for k in ("status", "status_text", "detail", "location", "eta", "delivered_at", "last_update", "checked", "service") if k in o})
        n = refresh_status(rows)
        data = {"generated": now(), "generated_full": now(), "generated_status": now(), "month": month, "rows": rows, "failed_accounts": failed}
        print("full: month %s | %d rows | %d looked up | failed accounts: %s" % (month, len(rows), n, failed or "none"))
    else:
        if not prev: raise SystemExit("no previous data: run the full refresh first")
        rows = prev["rows"]
        n = refresh_status(rows)
        data = dict(prev, generated=now(), generated_status=now())
        print("status: %d packages looked up" % n)
    rows.sort(key=lambda r: (r["name"].lower(), r["order_date"], r["tracking"]))
    print("status counts:", counts(rows))
    if "--dry" in sys.argv:                      # test run: nothing is written, only a summary WITHOUT names / tracking numbers is printed
        cc = {}
        for r in rows: cc[r["carrier"] or "-"] = cc.get(r["carrier"] or "-", 0) + 1
        print("carriers:", cc)
        cs = {}
        for r in rows: cs[(r["carrier"] or "-", r["status"] or "-")] = cs.get((r["carrier"] or "-", r["status"] or "-"), 0) + 1
        print("carrier/status:", {"%s/%s" % k: v for k, v in sorted(cs.items())})
        print("unknown reasons:", sorted({r["detail"][:90] for r in rows if r["tracking"] and r["status"] in ("UNKNOWN", "")}))
        print("rows per region:", {g: sum(1 for r in rows if r["region"] == g) for g in ("US", "Toronto", "Vancouver")})
        print("accounts with rows:", len({r["account"] for r in rows}), "| rows without tracking:", sum(1 for r in rows if not r["tracking"]))
        seen = set()
        for r in rows:
            k = (r["status"], bool(r["eta"]))
            if r["tracking"] and k not in seen and len(seen) < 8:
                seen.add(k)
                print("  sample:", r["carrier"], r["tracking"][:4] + "..." + r["tracking"][-3:], "|", r["status"], "|", r["status_text"], "|", r["detail"][:80], "| loc:", r["location"], "| eta:", r["eta"], "| delivered:", r["delivered_at"], "| last:", r["last_update"])
        print("cities:", sorted({(r["city"], r["state"]) for r in rows}))
        return
    write_site(site, data, template)


if __name__ == "__main__":
    main()
