"""2-request check: is Temu's page data back for cloud IPs? Appends one line per check to the watch log. HTML only.
WATCH_LOOP=1: re-check every 10 min until open (max ~5.5 h) - measures the exact cooldown after a block."""
import json, os, re, sys, time, subprocess
from datetime import datetime, timezone
from curl_cffi import requests as cr

def check():
    row = {"utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}
    for label, url, ua, imp in (
        ("crawler_search", "https://www.temu.com/search_result.html?search_key=dog%20shirt", "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)", "chrome"),
        ("shopper_home", "https://www.temu.com/", None, "safari_ios")):
        h = {"Accept-Language": "en-US,en;q=0.9"}
        if ua: h["User-Agent"] = ua
        try:
            r = cr.get(url, impersonate=imp, headers=h, timeout=45)
            row[label] = len(set(re.findall(r'"goodsId":"?(\d{12,})', r.text)))
        except Exception as e:
            row[label] = "err"
    row["open"] = isinstance(row.get("crawler_search"), int) and row["crawler_search"] > 0
    print(json.dumps(row))
    open(sys.argv[1], "a").write(json.dumps(row) + "\n")
    return row["open"]


def save(msg):
    if os.environ.get("WATCH_PUSH") == "1":
        subprocess.run("git add %s && git commit -qm '%s' && (git push -q origin temu-data || (git pull -q --rebase origin temu-data && git push -q origin temu-data))" % (sys.argv[1], msg), shell=True)


if os.environ.get("WATCH_LOOP") == "1":
    t0 = time.time()
    while True:
        ok = check(); save("temu watch loop")
        if ok or time.time() - t0 > 5.5 * 3600:
            print("cooldown watch ended: %s after %.0f min" % ("OPEN" if ok else "still closed", (time.time() - t0) / 60)); break
        time.sleep(600)
else:
    check(); save("temu watch")
