"""Hourly 2-request check: is Temu's page data back for cloud IPs? Appends one line to the watch log. HTML only."""
import json, re, sys
from datetime import datetime, timezone
from curl_cffi import requests as cr

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
