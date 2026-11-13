"""Fetch main product image URLs from SP-API catalog for given ASINs; store in private deals.asin_images. Log prints counts only."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, spapi, deal_finder as df

def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.asin_images (asin text primary key, main_url text, urls jsonb, at timestamptz default now())")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    ok = 0
    for a in (os.environ.get("REFS") or "").split():
        try:
            r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + a, params={"marketplaceIds": df.MK, "includedData": "images"}, quiet=True, tries=4)
        except Exception as e:
            print("  img ERR", str(e)[:60]); continue
        imgs = []
        for grp in (r.get("images") or []):
            for im in grp.get("images") or []:
                imgs.append({"variant": im.get("variant"), "url": im.get("link"), "w": im.get("width")})
        main = [i for i in imgs if i["variant"] == "MAIN"]
        main = max(main, key=lambda i: i["w"] or 0)["url"] if main else (imgs[0]["url"] if imgs else None)
        cx.execute("insert into deals.asin_images(asin, main_url, urls) values (%s,%s,%s) on conflict (asin) do update set main_url=excluded.main_url, urls=excluded.urls, at=now()", (a, main, json.dumps(imgs)))
        ok += bool(main); time.sleep(0.6)
    print("img_fetch: %d images stored" % ok)

main()
