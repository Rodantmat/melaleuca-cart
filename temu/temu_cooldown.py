"""Controlled cooldown test. Phase 1: requests 3 s apart until Temu stops sending product data (2 empty in a row) ->
trip threshold. Phase 2: one request every 3 min until data is back -> exact cooldown. Logs every line to the file in argv[1]."""
import json, re, subprocess, sys, time, urllib.parse
from datetime import datetime, timezone
from curl_cffi import requests as cr

LOG = sys.argv[1]
UA = {"User-Agent": "Pinterestbot/1.0 (+http://www.pinterest.com/bot.html)", "Accept-Language": "en-US,en;q=0.9"}
WORDS = ["dog shirt", "cat mug", "phone case", "yoga mat", "dog leash", "garden hose", "led lights", "kitchen towel", "car mount",
         "water bottle", "beanie", "socks", "tote bag", "keychain", "sticker", "hoodie", "blanket", "pillow case", "candle", "earrings"]
T0 = time.time()


def now(): return datetime.now(timezone.utc).strftime("%H:%M:%S")


def log(d):
    d["utc"] = now(); d["min"] = round((time.time() - T0) / 60, 1)
    line = json.dumps(d); print(line, flush=True); open(LOG, "a").write(line + "\n")


def push(msg):
    subprocess.run("git add %s && git commit -qm '%s' && git push -q origin temu-data" % (LOG, msg), shell=True)


def ask(i):
    q = WORDS[i % len(WORDS)] + ("" if i < len(WORDS) else " %d" % (i // len(WORDS)))
    try:
        r = cr.get("https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(q), impersonate="chrome", headers=UA, timeout=45)
        return len(set(re.findall(r'"goodsId":"?(\d{12,})', r.text)))
    except Exception:
        return -1


log({"phase": "start"})
# phase 1: trip it
n, empties, t_block = 0, 0, None
while n < 200:
    g = ask(n); n += 1
    empties = empties + 1 if g == 0 else 0
    if n <= 3 or n % 10 == 0 or g <= 0:
        log({"phase": "burst", "req": n, "goods": g})
    if empties >= 2:
        t_block = time.time(); log({"phase": "BLOCKED", "trip_at_request": n - 1, "secs_to_trip": round(t_block - T0)}); break
    time.sleep(3)
push("cooldown test: burst done")
if not t_block:
    log({"phase": "never blocked in 200 requests"}); push("cooldown test: no block"); sys.exit(0)
# phase 2: measure cooldown
k = 0
while time.time() - t_block < 5.6 * 3600:
    time.sleep(180); k += 1
    g = ask(1000 + k)
    log({"phase": "probe", "n": k, "goods": g, "blocked_min": round((time.time() - t_block) / 60, 1)})
    push("cooldown probe %d" % k)
    if g > 0:
        log({"phase": "REOPENED", "cooldown_min": round((time.time() - t_block) / 60, 1), "probe_step_min": 3}); push("cooldown test: reopened"); break
else:
    log({"phase": "still blocked after 5.6 h"}); push("cooldown test: still blocked")
