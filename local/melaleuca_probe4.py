"""lab probe 4 (read only): pack pages (choices, accessories) and the variant lists of product families. No cart changes."""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__)); FEED = os.path.join(HERE, "feed"); sys.path.insert(0, HERE)
import melaleuca_run as mr, melaleuca_scan as ms
from playwright.sync_api import sync_playwright
OUT = os.path.join(FEED, "probe4"); os.makedirs(OUT, exist_ok=True)

def grab(h, key):
    i = h.find('"%s":[{' % key)
    if i < 0:
        return []
    j = h.find('[', i); d = 0
    for k in range(j, len(h)):
        if h[k] == '[': d += 1
        elif h[k] == ']':
            d -= 1
            if d == 0:
                try:
                    return json.loads(h[j:k + 1])
                except Exception:
                    return []
    return []

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    env = mr.read_env(os.path.join(HERE, "credentials.env"))
    acct = {"tab": "Antonio M", "n": n, "user": env["MELA_USER_%d" % n], "pass": env["MELA_PASS_%d" % n], "region": "socal"}
    cfg = {"proxy": env.get("PROXY_URL", ""), "sticky_base": 10000, "headless": True, "channel": "", "session_minutes": 120, "debug_dir": os.path.join(FEED, "debug"), "fast": True}
    skus = [x.strip() for x in open(os.path.join(FEED, "probe4_skus.txt")) if x.strip()]
    packs = {}
    with sync_playwright() as p:
        s = ms.Session(p, acct, n, cfg, None)
        try:
            s.login()
            for sku in skus:
                try:
                    s.page.goto("%s/products/%s?sc_lang=en-US" % (ms.BASE, sku), wait_until="domcontentloaded", timeout=60000)
                    s.page.wait_for_timeout(2500)
                    h = s.page.content()
                    conf = grab(h, "Configurations")
                    acc = grab(h, "Accessories")
                    for c in conf:
                        for ch in c.get("Choices", []):
                            m = re.search(r"products/(\d+)h", ch.get("ShelfImage") or "")
                            ch["sku"] = m.group(1) if m else None
                            ch.pop("ShelfImage", None); ch.pop("PdpImage", None)
                    t = re.search(r"<title>([^<]*)", h)
                    packs[sku] = {"title": t.group(1) if t else "", "url": s.page.url, "conf": conf,
                                  "acc": [{"sku": a.get("Sku"), "title": a.get("Title") or (a.get("Image") or {}).get("Alt"), "price": (a.get("PriceRange") or {}).get("RawMinPreferredPrice"), "pts": (a.get("PriceRange") or {}).get("RawMinPoints")} for a in acc]}
                    print(sku, packs[sku]["title"][:50], "conf:", len(conf), "acc:", len(acc))
                except Exception as e:
                    print(sku, "trouble", str(e)[:100])
            json.dump(packs, open(os.path.join(OUT, "packs.json"), "w"), indent=1)
            # families: the store's category lists with every variant of a card
            cards = []
            for cat in ("beauty", "personal-care", "cleaning-and-laundry", "supplements", "healthy-foods-and-drinks"):
                before = len(s.json_log)
                try:
                    s.page.goto("%s/productstore/%s?sc_lang=en-US" % (ms.BASE, cat), wait_until="domcontentloaded", timeout=60000)
                    s.settle(8000)
                except Exception as e:
                    print(cat, "trouble", str(e)[:80])
                for u, m, j in s.json_log[before:]:
                    if "/api/category/search/" in u and isinstance(j, dict):
                        for c in j.get("Cards", []):
                            d = (c.get("InnerData") or {}).get("Data") or {}
                            if d.get("Products") and len(d["Products"]) > 1 and len(cards) < 40:
                                dd = {k: v for k, v in d.items() if k not in ("PriceRange", "Image", "Description")}
                                cards.append(dd)
                print(cat, "cards so far with variants:", len(cards))
            json.dump(cards, open(os.path.join(OUT, "family_cards.json"), "w"), indent=1)
            if cards:
                lk = cards[0].get("PdpLink")
                if lk:
                    s.page.goto(ms.BASE + lk, wait_until="domcontentloaded", timeout=60000); s.page.wait_for_timeout(3000)
                    h = s.page.content()
                    open(os.path.join(OUT, "family_page_sample.html"), "w", encoding="utf-8").write(h)
        finally:
            s.close()

if __name__ == "__main__":
    main()
