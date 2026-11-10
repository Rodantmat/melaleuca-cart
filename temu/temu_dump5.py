"""Inspect raw goods objects (search, best sellers) and an e-bike product page, Pinterest-crawler view."""
import json, re, sys
sys.path.insert(0, "temu")
from temu_bridge import fetch, raw_data

h, _ = fetch("https://www.temu.com/search_result.html?search_key=dog%20shirt")
i = h.find('"goodsId"')
print("SEARCH RAW OBJ:", h[max(0, i - 300):i + 2600].replace("\n", " "))
rd = raw_data(h)
print("SEARCH rawData parsed:", bool(rd), (list(rd.keys())[:10] if isinstance(rd, dict) else None))

h, _ = fetch("https://www.temu.com/channel/best-sellers.html")
ids = re.findall(r'"goods_?[iI]d"\s*:\s*"?(\d{12,})', h)
print("BEST ids by key:", len(ids), "rawData:", bool(raw_data(h)))
i = h.find(ids[0]) if ids else -1
print("BEST RAW OBJ:", h[max(0, i - 600):i + 2200].replace("\n", " ") if i >= 0 else h[:500])

h, u = fetch("https://www.temu.com/-g-601102364449217.html")
print("EBIKE final", u, "len", len(h or ""))
for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h or "", re.S):
    print("EBIKE LD:", re.sub(r'"image":\[.*?\]\s*,', '"image":[...],', blk)[:1500])
print("EBIKE META:", re.findall(r'<meta property="product:[^>]+>', h or ""))
