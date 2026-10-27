"""
melaleuca_run.py - one command for the whole account scan (Excel starts it from "Update Melaleuca Data").

  1. reads credentials.env   (PROXY_URL, STICKY_BASE, HEADLESS, MELA_USER_1 / MELA_PASS_1, MELA_USER_2 ...  numbered like the coloured order tabs)
  2. reads feed\\mel_tabs.txt (written by Excel: number, tab name, kind)
  3. logs in to each account (own steady IP per account), reads its offers - never places an order
  4. writes feed\\account_offers.tsv, which Excel imports into the sheet AccountOffers

  python melaleuca_run.py            all accounts that have a user + password
  python melaleuca_run.py --only 7   just coloured tab number 7
"""
import os, sys, json, subprocess, traceback, datetime, pathlib, time

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "feed")
sys.path.insert(0, HERE)


def read_env(path):
    env = {}
    for ln in open(path, encoding="utf-8-sig"):
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def write(self, s):
        sys.__stdout__.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        sys.__stdout__.flush()


class Prefix:
    """prefixes every line with the tab number (several accounts print at the same time) and keeps a copy in the log file"""
    def __init__(self, tag, logpath):
        self.tag, self.logpath, self.buf = tag, logpath, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            ln, self.buf = self.buf.split("\n", 1)
            line = "[%s] %s\n" % (self.tag, ln)
            sys.__stdout__.write(line)
            try:
                with open(self.logpath, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass

    def flush(self):
        sys.__stdout__.flush()


def scan_one(job):
    a, cfg, logpath = job
    try:
        sys.__stdout__.reconfigure(errors="replace")
    except Exception:
        pass
    sys.stdout = Prefix("tab %d %s" % (a["n"], a["tab"]), logpath)
    import melaleuca_scan as ms
    from playwright.sync_api import sync_playwright
    n = a["n"]
    ipfile = os.path.join(FEED, "ip_%d.json" % n)
    saved, old_ip = None, None
    try:
        d = json.load(open(ipfile))
        saved, old_ip = d.get("port"), d.get("ip")
    except Exception:
        pass
    base = int(cfg.get("sticky_base") or 0)
    # the saved port first (same IP as long as the provider keeps that session), then fresh ports: no account may be skipped
    ports = ([saved] if saved else ([base + n] if base else [None])) + ([base + n + 100 * k for k in range(1, 40)] if base else [None] * 40)
    tries = int(cfg.get("max_tries", 8))
    res = None
    bad_n = 0
    with sync_playwright() as p:
        for attempt in range(1, tries + 1):
            port = ports[attempt - 1] if attempt - 1 < len(ports) else None
            if attempt > 1:
                ms.log("retry %d of %d with another IP" % (attempt, tries))
            # exact city first, then the country, then (last resort) a US IP; the browser alternates between real Chrome and the built-in one
            a = dict(a, geo_level=0 if attempt <= 2 else (1 if attempt <= 4 else 2), channel_override=(None if attempt % 2 else "chromium"))
            try:
                res = ms.scan_account(p, a, n, cfg, port)
            except Exception:
                res = {"tab": a["tab"], "ok": False, "error": traceback.format_exc()[-400:]}
            if res.get("ok"):
                if old_ip and res.get("ip"):
                    ms.log("  IP %s as last time (%s -> %s)" % ("is the SAME" if old_ip == res["ip"] else "CHANGED", old_ip, res["ip"]))
                try:
                    json.dump({"tab": a["tab"], "port": res.get("port"), "ip": res.get("ip"), "date": res.get("scanned")}, open(ipfile, "w"))
                except Exception:
                    pass
                break
            if (not res.get("ok")) and res.get("error_kind") != "badlogin" and any(k in str(res.get("error") or "") for k in ("ERR_PROXY", "ERR_TUNNEL", "ERR_CONNECTION")) and attempt < tries:
                pause = min(90, 15 * attempt)       # the proxy service refused the connection: wait instead of burning every port in a few seconds
                ms.log("the proxy service refused the connection - waiting %d s before the next IP" % pause)
                time.sleep(pause)
            if res.get("error_kind") == "badlogin":
                # the store often answers "Invalid Username or Password" to an IP / browser it does not like (a human check in disguise): the same
                # account signs in fine at other times. So it is tried again on a fresh IP and the other browser, with a longer pause each time
                # (like the cart filler does); only after several refusals in a row is the password treated as really wrong.
                bad_n += 1
                if bad_n <= 4 and attempt < tries:
                    pause = 20 + 20 * bad_n
                    ms.log("sign-in refused (%d of 4) - trying again on a fresh connection and browser in %d s (the same account signs in fine at other times)" % (bad_n, pause))
                    time.sleep(pause)
                    continue
                ms.log("the user name / password of this account was refused on %d fresh connections in a row - check MELA_USER_%d / MELA_PASS_%d in credentials.env" % (bad_n, n, n))
                break
    print("-> " + ("ok" if res.get("ok") else "FAILED: " + str(res.get("error") or res.get("note"))[:200]))
    return res



def main():
    os.makedirs(FEED, exist_ok=True)
    try:
        sys.__stdout__.reconfigure(errors="replace")      # the Windows console cannot show every character of a product name
    except Exception:
        pass
    sys.stdout = Tee(os.path.join(FEED, "scan_log.txt"))
    env = read_env(os.path.join(HERE, "credentials.env"))
    tabs, kinds, colours = {}, {}, {}
    tp = os.path.join(FEED, "mel_tabs.txt")
    if not os.path.exists(tp):
        print("feed\\mel_tabs.txt is missing - start this from Excel (Update Melaleuca Data).")
        return 2
    for ln in open(tp, encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 2 and p[0].strip().isdigit():
            tabs[int(p[0])] = p[1]
            kinds[int(p[0])] = p[2].strip() if len(p) > 2 else "2"
            colours[int(p[0])] = p[3].strip().lower() if len(p) > 3 else ""
    only = None
    if "--only" in sys.argv:
        only = int(sys.argv[sys.argv.index("--only") + 1])
    accounts = []
    for n in sorted(tabs):
        u, pw = env.get("MELA_USER_%d" % n), env.get("MELA_PASS_%d" % n)
        if only and n != only:
            continue
        if u and pw:
            region = env.get("REGION_%d" % n, "").strip().lower()
            if not region:                                   # orange tabs = Vancouver, yellow = Toronto, blue = southern California
                region = {"orange": "vancouver", "yellow": "toronto"}.get(colours.get(n, ""), "socal" if kinds.get(n) == "2" else "vancouver")
            accounts.append({"tab": tabs[n], "n": n, "user": u, "pass": pw, "region": region})
        else:
            print("tab %d (%s): no MELA_USER_%d / MELA_PASS_%d in credentials.env - skipped" % (n, tabs[n], n, n))
    if not accounts:
        print("No account with credentials.")
        return 2
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": (10000 if env.get("STICKY_BASE") is None else int(env.get("STICKY_BASE") or 0)),
           "headless": env.get("HEADLESS", "1") not in ("0", "false", "no")}
    cfg["channel"] = env.get("BROWSER", "") or ""
    cfg["session_minutes"] = int(env.get("SESSION_MINUTES", "120") or 0)
    cfg["debug_dir"] = os.path.join(FEED, "debug")
    cfg["max_tries"] = int(env.get("MAX_TRIES", "8") or 8)
    cfg["fast"] = env.get("FAST", "1") not in ("0", "false", "no")
    workers = max(1, min(int(env.get("WORKERS", "4") or 4), len(accounts)))
    print("scanning %d account(s), %d at a time" % (len(accounts), workers))
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(a, cfg, os.path.join(FEED, "scan_log.txt")) for a in accounts]
    if workers == 1:
        results = [scan_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(scan_one, jobs))
    out = os.path.join(FEED, "melaleuca_offers.json")
    # a partial run (--only N) must not wipe the other accounts: keep their last good results (also the US prices the Canadian tabs need)
    try:
        old = json.load(open(out, encoding="utf-8"))
        have = {r.get("tab") for r in results}
        results = results + [r for r in old.get("accounts", []) if r.get("ok") and r.get("tab") not in have]
    except Exception:
        pass
    pathlib.Path(out).write_text(json.dumps({"generated": datetime.datetime.now().isoformat(timespec="seconds"), "accounts": results}, indent=1), encoding="utf-8")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "melaleuca_offers_map.py"), out, os.path.join(FEED, "mel_rows.tsv"),
                          os.path.join(FEED, "account_offers.tsv")],
                         env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
    okn = sum(1 for r in results if r.get("ok"))
    print("accounts read: %d of %d" % (okn, len(results)))
    return 0 if okn and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
