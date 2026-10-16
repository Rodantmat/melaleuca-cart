import sys, re, json
from playwright.sync_api import sync_playwright
import melaleuca_fill as mf
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    for sku in ("60146","60147","60148","60171","60247","60155"):
        try:
            pg.goto("https://www.melaleuca.com/products/%s?sc_lang=en-US" % sku, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(3500)
            html = pg.content()
            inf = mf.parse_info(html)
            t = re.search(r"<title>(.*?)</title>", html, re.S)
            print("SKU", sku, len(html), (t.group(1).strip()[:90] if t else ""), json.dumps(inf)[:900])
        except Exception as e:
            print("SKU", sku, "ERR", str(e)[:100])
    b.close()
