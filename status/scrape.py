"""scrape.py - reads the ORDER HISTORY of one Melaleuca account (same proxy / sign-in / no-pictures rules as the cart filler) and writes out/acct_<n>.json:
every recent order with its tracking numbers (store's own tracking links), status and the ship-to city.  READ ONLY: nothing is ordered, changed or paid.
usage:  python scrape.py <account number> [--out DIR] [--days 50]"""
import datetime as dt, json, os, re, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(os.path.dirname(HERE), "local")
sys.path.insert(0, LOCAL)
import melaleuca_run as mr
import melaleuca_scan as ms
from playwright.sync_api import sync_playwright

JS = """() => [...document.querySelectorAll('ul.m-po__header')].map(u => {
  const t = s => { const e = u.querySelector(s); return e ? e.innerText.trim() : ''; };
  return {date: t('span.m-po__date.-value'), number: t('span.m-po__number.-value'), total: t('span.m-po__total.-value'), points: t('span.m-po__points.-value'),
          opts: [...u.querySelectorAll('li.m-po__track select option')].map(o => [o.innerText.trim(), o.value]).filter(x => x[1] && x[1] !== 'Track')};
})"""


def tab_info(an):
    for ln in open(os.path.join(LOCAL, "feed", "mel_tabs.txt"), encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 3 and p[0].strip().isdigit() and int(p[0]) == an:
            return p[1], (p[3].strip().lower() if len(p) > 3 else "")
    raise SystemExit("unknown account %d" % an)


def region_of(colour):
    return {"orange": "vancouver", "yellow": "toronto"}.get(colour, "socal")


def parse_date(s):
    try: return dt.datetime.strptime(s.strip(), "%B %d, %Y").date()
    except Exception: return None


def scrape(an, days=50, log=print):
    env = mr.read_env(os.path.join(LOCAL, "credentials.env"))
    name, colour = tab_info(an)
    region = env.get("REGION_%d" % an, "").strip().lower() or region_of(colour)
    acct = {"tab": name, "n": an, "user": env["MELA_USER_%d" % an], "pass": env["MELA_PASS_%d" % an], "region": region}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": int(env.get("STICKY_BASE") or 10000), "headless": True, "channel": "", "session_minutes": 120,
           "debug_dir": os.path.join(LOCAL, "feed", "debug"), "fast": True, "early_route": True}
    ca = region in ("vancouver", "toronto")
    res = {"an": an, "tab": name, "region": region, "ok": False, "orders": [], "error": "", "scraped": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with sync_playwright() as p:
        s = None
        for attempt in range(1, 7):
            try:
                a2 = dict(acct, geo_level=0 if attempt <= 2 else 1, channel_override=(None if attempt % 2 else "chromium"))
                s = ms.Session(p, a2, an, cfg, None if attempt == 1 else 10000 + an + 100 * attempt)
                s.login()
                break
            except Exception as e:
                log("sign-in attempt %d failed: %s" % (attempt, str(e)[:100]))
                try: s.close()
                except Exception: pass
                s = None
                if attempt == 6:
                    res["error"] = "sign-in failed: " + str(e)[:120]
                    return res
                time.sleep(min(60, 12 * attempt))
        try:
            pg = s.page
            cards = []
            for k in range(3):
                pg.goto(ms.BASE + "/my-account/order-history", wait_until="domcontentloaded", timeout=60000)
                s.settle(7000 + 4000 * k)
                cards = pg.evaluate(JS)
                if cards: break
            if not cards:
                res["error"] = "order history showed no orders"
                return res
            since = dt.date.today() - dt.timedelta(days=days)
            for c in cards:
                d = parse_date(c["date"])
                if not d or d < since: continue
                o = {"date": d.isoformat(), "number": c["number"], "total": c["total"], "points": c["points"],
                     "packages": [{"n": t, "href": h} for t, h in c["opts"]], "status": "", "name": "", "city": "", "state": "", "country": ""}
                r = s.fetch("/api/receipt/%s?sc_lang=%s&sc_site=%s" % (c["number"], "en-CA" if ca else "en-US", "productstoreCa" if ca else "productstoreUs"))
                dd = (r.get("json") or {}).get("Data") or {}
                a = dd.get("ShipToAddress") or {}
                o.update(status=dd.get("OrderStatusLabel") or dd.get("OrderStatus") or "", name=dd.get("ShipToName") or "",
                         city=a.get("City") or "", state=a.get("State") or "", country=a.get("Country") or "")
                res["orders"].append(o)
            res["ok"] = True
            log("%s: %d recent order(s), %d package(s)" % (name, len(res["orders"]), sum(len(o["packages"]) for o in res["orders"])))
        except Exception:
            res["error"] = traceback.format_exc()[-300:]
        finally:
            try: s.close()
            except Exception: pass
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = "out"; days = 50
    if "--out" in sys.argv: out = sys.argv[sys.argv.index("--out") + 1]; args = [a for a in args if a != out]
    if "--days" in sys.argv: days = int(sys.argv[sys.argv.index("--days") + 1]); args = [a for a in args if a != str(days)]
    an = int(args[0])
    os.makedirs(out, exist_ok=True)
    r = scrape(an, days, log=lambda *a: print(time.strftime("%H:%M:%S"), *a, flush=True))
    with open(os.path.join(out, "acct_%d.json" % an), "w", encoding="utf-8") as f: json.dump(r, f)
    print("ok" if r["ok"] else "FAILED: " + r["error"])


if __name__ == "__main__":
    main()
