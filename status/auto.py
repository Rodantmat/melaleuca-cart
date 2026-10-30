"""auto.py - the self-driving part of the status pages.

Per account (the 17 order tabs) a small state machine, kept in branch status-state (state.json):
    idle      nothing to watch
    waiting   an order was placed (armed by the cart filler / the arm workflow): the account's order history is read ONCE EVERY MORNING (06:00 Pacific)
              until every order of the month has its tracking numbers; then -> tracking
    tracking  the carriers are asked for the packages every 2 hours, every 15 minutes once a package is OUT FOR DELIVERY;
              a delivered package is never asked again; when all are delivered -> idle
A new month's first arm starts a new batch: the page then shows only that month's orders.

   python auto.py plan    --site S --state T [--mode auto|all|status]    prints JSON {"scrape":[...],"status":bool,"any":bool}  (read only)
   python auto.py publish --site S --state T --in DIR [--mode ...]        applies everything: rows, carrier status, state, pages
"""
import copy, datetime as dt, glob, json, os, re, sys, time
try:
    from zoneinfo import ZoneInfo
except ImportError:                                  # pragma: no cover
    ZoneInfo = None
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build as B
import carriers as C

TZ = ZoneInfo("America/Los_Angeles")
UTC = dt.timezone.utc
MORNING_HOUR = 6
GIVE_UP_DAYS = 10                 # an armed account that still has no tracking after this many days is dropped (a note stays in the state)
EVERY_NORMAL_MIN = 110            # "every 2 hours": the cron ticks every 15 minutes, 110 min means the tick at 120
EVERY_OFD_MIN = 12                # "every 15 minutes" (same reason: the tick that follows)
RETRY_FAILED_MIN = 120


def now():
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso(d): return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
def parse(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def next_morning(after):
    loc = after.astimezone(TZ)
    t = dt.datetime.combine(loc.date(), dt.time(MORNING_HOUR, 0), TZ)
    if t <= loc: t = dt.datetime.combine(loc.date() + dt.timedelta(days=1), dt.time(MORNING_HOUR, 0), TZ)
    return t.astimezone(UTC)


def tabs():
    out = {}
    p = os.path.join(os.path.dirname(HERE), "local", "feed", "mel_tabs.txt")
    for ln in open(p, encoding="utf-8-sig"):
        f = ln.rstrip("\r\n").split("\t")
        if len(f) >= 3 and f[0].strip().isdigit(): out[int(f[0])] = f[1]
    return out


# ------------------------------------------------------------------------------------------------- state
def load_state(state_dir, prev):
    p = os.path.join(state_dir, "state.json")
    if os.path.exists(p): return json.load(open(p, encoding="utf-8"))
    # first start: built from what the page already shows
    st = {"batch_month": (prev or {}).get("month", ""), "accounts": {}, "updated": iso(now())}
    rows = (prev or {}).get("rows", [])
    for an, tab in tabs().items():
        mine = [r for r in rows if r["account"] == tab]
        mode = "tracking" if any(r["tracking"] and r["status"] != "DELIVERED" for r in mine) else "idle"
        if mine and any(not r["tracking"] for r in mine): mode = "waiting"
        st["accounts"][str(an)] = {"tab": tab, "mode": mode, "armed": "", "next_scrape": iso(next_morning(now())) if mode == "waiting" else "", "tries": 0, "note": "", "last_error": ""}
    return st


def read_queue(state_dir):
    out = []
    for f in sorted(glob.glob(os.path.join(state_dir, "queue", "*.json"))):
        try: out.append((f, json.load(open(f, encoding="utf-8"))))
        except Exception: out.append((f, None))
    return out


def apply_queue(st, queue, t):
    """-> (state, reset_rows).  Every arm marks accounts as waiting; the first arm of a new month starts a new batch."""
    reset = False
    all_tabs = tabs()
    for f, q in queue:
        if not q: continue
        at0 = parse(q["at"]) if q.get("at") else t
        month = q.get("month") or at0.astimezone(TZ).strftime("%Y-%m")
        accts = q.get("accounts") or []
        if accts == ["all"]: accts = sorted(all_tabs)
        if month != st.get("batch_month"):
            st["batch_month"] = month; reset = True
            for a in st["accounts"].values(): a.update(mode="idle", next_scrape="", note="")
        for an in accts:
            an = str(an)
            if int(an) not in all_tabs: continue
            a = st["accounts"].setdefault(an, {"tab": all_tabs[int(an)]})
            at = parse(q["at"]) if q.get("at") else t
            a.update(tab=all_tabs[int(an)], mode="waiting", armed=iso(at), next_scrape=iso(next_morning(at)), tries=0, note="", last_error="")
    return st, reset


# ------------------------------------------------------------------------------------------------- plan
def due_rows(rows, t, force=False):
    ti = iso(t)
    return [r for r in rows if r["tracking"] and r.get("status") != "DELIVERED" and (force or (r.get("next_check") or "") <= ti)]


def plan(site, state_dir, mode, t):
    prev = B.load_prev(site)
    st = load_state(state_dir, prev)
    q = read_queue(state_dir)
    st, reset = apply_queue(copy.deepcopy(st), q, t)
    rows = [] if reset else (prev or {}).get("rows", [])
    if mode == "all": scrape = sorted(tabs())
    else: scrape = sorted(int(an) for an, a in st["accounts"].items() if a["mode"] == "waiting" and a.get("next_scrape") and iso(t) >= a["next_scrape"])
    status = bool(due_rows(rows, t, force=(mode in ("status", "all"))))
    return {"scrape": scrape, "status": status, "queue": len(q), "any": bool(scrape or status or q or mode != "auto")}


# ------------------------------------------------------------------------------------------------- publish
def is_ofd(r):
    return r.get("status") == "TRANSIT" and bool(re.search(r"out for delivery", (r.get("detail", "") + " " + r.get("status_text", "")), re.I))


def refresh(rows, t, force=False):
    todo = due_rows(rows, t, force)
    if todo: B.refresh_status(todo, only_open=False)
    for r in todo:
        if r.get("status") == "DELIVERED": r["next_check"] = ""
        else: r["next_check"] = iso(t + dt.timedelta(minutes=EVERY_OFD_MIN if is_ofd(r) else EVERY_NORMAL_MIN))
    return len(todo)


def publish(site, state_dir, indir, mode, t, forced_month=None):
    prev = B.load_prev(site)
    st = load_state(state_dir, prev)
    q = read_queue(state_dir)
    st, reset = apply_queue(st, q, t)
    month = forced_month or st.get("batch_month") or (prev or {}).get("month") or t.astimezone(TZ).strftime("%Y-%m")
    rows = [] if reset else list((prev or {}).get("rows", []))
    accts = {}
    for f in sorted(glob.glob(os.path.join(indir, "acct_*.json"))):
        a = json.load(open(f, encoding="utf-8")); accts[a["an"]] = a
    if mode == "all" and not forced_month and not st.get("batch_month"):
        month = B.batch_month([a for a in accts.values() if a.get("ok")])
    if mode == "all" and not forced_month and accts:
        m2 = B.batch_month([a for a in accts.values() if a.get("ok")])
        if st.get("batch_month") and m2 != st["batch_month"] and sum(1 for a in accts.values() if a.get("ok")) >= B.MIN_ACCOUNTS:
            month = m2; rows = []                    # a full read of all accounts found a different month: that is the batch now
    st["batch_month"] = month
    old = {(r["order_no"], r["tracking"]): r for r in rows}
    all_tabs = tabs()
    for an, a in sorted(accts.items()):
        s = st["accounts"].setdefault(str(an), {"tab": all_tabs.get(an, a["tab"]), "mode": "idle", "armed": "", "next_scrape": "", "tries": 0, "note": "", "last_error": ""})
        if not a.get("ok"):
            s["last_error"] = a.get("error", "")[:120]
            if s["mode"] == "waiting": s["next_scrape"] = iso(t + dt.timedelta(minutes=RETRY_FAILED_MIN))
            continue
        s["last_error"] = ""
        mine = B.rows_from([a], month)
        for r in mine:                                    # carry the known carrier information of a package that is already followed
            o = old.get((r["order_no"], r["tracking"]))
            if o and o["tracking"]:
                for k in ("status", "status_text", "detail", "location", "eta", "delivered_at", "last_update", "checked", "service", "next_check"):
                    if k in o: r[k] = o[k]
        rows = [r for r in rows if r["account"] != a["tab"]] + mine
        orders = [o for o in a["orders"] if o["date"][:7] == month]
        if orders and all(o["packages"] for o in orders):
            if s["mode"] != "tracking": s["mode"] = "tracking"; s["note"] = "tracking numbers found %s" % iso(t)
            s["next_scrape"] = ""
        elif orders or s["mode"] == "waiting":              # an order without tracking yet, or an armed account whose order is not visible yet: look again tomorrow morning
            s["mode"] = "waiting"
            s["tries"] = s.get("tries", 0) + 1
            s["next_scrape"] = iso(next_morning(t))
            if s.get("armed") and t - parse(s["armed"]) > dt.timedelta(days=GIVE_UP_DAYS):
                s["mode"] = "idle"; s["next_scrape"] = ""; s["note"] = "no tracking after %d days - stopped" % GIVE_UP_DAYS
    n = refresh(rows, t, force=(mode in ("status", "all")))
    for an, s in st["accounts"].items():                  # everything delivered -> idle
        mine = [r for r in rows if r["account"] == s.get("tab") and r["tracking"]]
        if s["mode"] == "tracking" and mine and all(r["status"] == "DELIVERED" for r in mine):
            s["mode"] = "idle"; s["note"] = "all delivered %s" % iso(t)
    rows.sort(key=lambda r: (r["name"].lower(), r["order_date"], r["tracking"]))
    failed = [s["tab"] for s in st["accounts"].values() if s.get("last_error")]
    data = {"generated": iso(t), "generated_full": iso(t) if accts else (prev or {}).get("generated_full", iso(t)),
            "generated_status": iso(t) if (n or accts) else (prev or {}).get("generated_status", iso(t)), "month": month, "rows": rows, "failed_accounts": failed,
            "auto": {m: sum(1 for s in st["accounts"].values() if s["mode"] == m) for m in ("waiting", "tracking", "idle")}}
    st["updated"] = iso(t)
    B.write_site(site, data, os.path.join(HERE, "site", "index.html"))
    os.makedirs(state_dir, exist_ok=True)
    json.dump(st, open(os.path.join(state_dir, "state.json"), "w", encoding="utf-8"), indent=1)
    for f, _ in q:
        try: os.remove(f)
        except OSError: pass
    print("publish: month %s | scraped %s | %d carrier lookups | rows %d | modes %s | failed %s" % (month, sorted(accts) or "-", n, len(rows), data["auto"], failed or "none"))
    return data


def main():
    cmd = sys.argv[1]
    arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    site, state_dir, mode = arg("--site"), arg("--state"), arg("--mode", "auto")
    t = now()
    if cmd == "plan":
        out = plan(site, state_dir, mode, t)
        print(json.dumps(out))
        gh = os.environ.get("GITHUB_OUTPUT")
        if gh:
            with open(gh, "a") as f:
                f.write("scrape=%s\nstatus=%s\nany=%s\n" % (json.dumps(out["scrape"]), str(out["status"]).lower(), str(out["any"]).lower()))
    else:
        publish(site, state_dir, arg("--in", "out"), mode, t, arg("--month"))


if __name__ == "__main__":
    main()
