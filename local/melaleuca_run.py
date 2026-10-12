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
    import melaleuca_scan as ms
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        for i, a in enumerate(accounts, 1):
            res = None
            for attempt in (1, 2):
                ms.log("[%d/%d] %s (tab %d)%s" % (i, len(accounts), a["tab"], a["n"], " - retry" if attempt == 2 else ""))
                try:
                    res = ms.scan_account(p, a, a["n"], cfg)
                except Exception:
                    res = {"tab": a["tab"], "ok": False, "error": traceback.format_exc()[-400:]}
                if res.get("ok"):
                    break
            results.append(res)
            print("   ->", "ok" if res.get("ok") else "FAILED: " + str(res.get("error") or res.get("note"))[:200])
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
