"""Dump where Temu puts product data in its server HTML (to design the parser). Runner IP, no proxy, HTML only."""
import json, os, re
from curl_cffi import requests as cr

IDS = os.environ.get("TEMU_IDS", "601102364449217,603242230592430").split(",")


def show(label, html):
    print("\n########", label, "len", len(html), flush=True)
    print("window vars:", sorted(set(re.findall(r"window\.(\w+)\s*=", html)))[:40])
    for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S)[:3]:
        print("LD+JSON:", blk[:1500])
    for m in re.findall(r'<meta[^>]+(?:property|name)="(?:og:[^"]+|product:[^"]+|description)"[^>]*>', html)[:12]:
        print("META:", m[:250])
    for key in ("goodsName", "salePrice", "linePrice", "priceStr", "minOnSalePrice", "skuId", "salesTip", "soldQuantity", "goodsScore", "reviewNum", "commentNum", "mallName", "price"):
        idx = [m.start() for m in re.finditer(r'"%s"' % key, html)][:2]
        for i in idx:
            print("CTX %-14s %s" % (key, html[max(0, i - 120):i + 260].replace("\n", " ")))
    dollars = re.findall(r'.{0,80}\$\d+\.\d\d.{0,60}', html)
    for d in dollars[:6]:
        print("DOLLAR:", d.replace("\n", " ")[:220])
    m = re.search(r'window\.rawData\s*=\s*', html)
    if m:
        print("rawData starts:", html[m.end():m.end() + 1200])


for gid in IDS[:2]:
    for imp in ("safari_ios", "chrome"):
        r = cr.get("https://www.temu.com/-g-%s.html" % gid, impersonate=imp, timeout=40, headers={"Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.google.com/"})
        show("product %s %s status=%s" % (gid, imp, r.status_code), r.text)
r = cr.get("https://www.temu.com/", impersonate="safari_ios", timeout=40, headers={"Accept-Language": "en-US,en;q=0.9"})
show("homepage safari_ios status=%s" % r.status_code, r.text)
