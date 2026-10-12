"""
melaleuca_run.py - one command for the whole account scan (Excel starts it from "Update Melaleuca Data").

  1. reads credentials.env   (PROXY_URL, STICKY_BASE, HEADLESS, MELA_USER_1 / MELA_PASS_1, MELA_USER_2 ...  numbered like the coloured order tabs)
  2. reads feed\\mel_tabs.txt (written by Excel: number, tab name, kind)
  3. logs in to each account (own steady IP per account), reads its offers - never places an order
  4. writes feed\\account_offers.tsv, which Excel imports into the sheet AccountOffers

  python melaleuca_run.py            all accounts that have a user + password
  python melaleuca_run.py --only 7   just coloured tab number 7
"""
import os, sys, json, subprocess, traceback, datetime, pathlib

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
    res = None
    with sync_playwright() as p:
        for attempt in (1, 2):
            try:
                res = ms.scan_account(p, a, a["n"], cfg)
            except Exception:
                res = {"tab": a["tab"], "ok": False, "error": traceback.format_exc()[-400:]}
            if res.get("ok"):
                break
            ms.log("failed, trying once more")
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
    tabs = {}
    tp = os.path.join(FEED, "mel_tabs.txt")
    if not os.path.exists(tp):
        print("feed\\mel_tabs.txt is missing - start this from Excel (Update Melaleuca Data).")
        return 2
    for ln in open(tp, encoding="utf-8-sig"):
        p = ln.rstrip("\r\n").split("\t")
        if len(p) >= 2 and p[0].strip().isdigit():
            tabs[int(p[0])] = p[1]
    only = None
    if "--only" in sys.argv:
        only = int(sys.argv[sys.argv.index("--only") + 1])
    accounts = []
    for n in sorted(tabs):
        u, pw = env.get("MELA_USER_%d" % n), env.get("MELA_PASS_%d" % n)
        if only and n != only:
            continue
        if u and pw:
            accounts.append({"tab": tabs[n], "n": n, "user": u, "pass": pw})
        else:
            print("tab %d (%s): no MELA_USER_%d / MELA_PASS_%d in credentials.env - skipped" % (n, tabs[n], n, n))
    if not accounts:
        print("No account with credentials.")
        return 2
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": (10000 if env.get("STICKY_BASE") is None else int(env.get("STICKY_BASE") or 0)),
           "headless": env.get("HEADLESS", "1") not in ("0", "false", "no")}
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
    pathlib.Path(out).write_text(json.dumps({"generated": datetime.datetime.now().isoformat(timespec="seconds"), "accounts": results}, indent=1), encoding="utf-8")
    rc = subprocess.call([sys.executable, os.path.join(HERE, "melaleuca_offers_map.py"), out, os.path.join(FEED, "mel_rows.tsv"),
                          os.path.join(FEED, "account_offers.tsv")],
                         env=dict(os.environ, PYTHONIOENCODING="utf-8:replace"))
    okn = sum(1 for r in results if r.get("ok"))
    print("accounts read: %d of %d" % (okn, len(results)))
    return 0 if okn and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
