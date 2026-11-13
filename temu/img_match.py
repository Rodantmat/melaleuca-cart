"""Image-similarity competitor finder (private results).
Env: REFS (space separated ASINs), QUERIES (optional '|' separated extra keyword queries applied to every ref), DATABASE_URL.
For each ref: its stored photos (deals.asin_images) are compared with the main photo of every catalog-search hit (keyword queries from the title plus extras)
using CLIP image embeddings. Hits with offers/price/rank are stored in deals.img_match. Log prints counts only."""
import io, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "reprice"))
import psycopg, requests, spapi, deal_finder as df
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

STOP = set("the a an for with and of in on to by pack set pcs pc piece pieces new upgraded 2024 2025 2026 2027 black white red blue brown".split())

def words(t):
    return [w for w in re.findall(r"[A-Za-z]+", t.lower()) if w not in STOP and len(w) > 2]

def queries_for(title, extra):
    w = words(title)
    qs = [" ".join(w[:n]) for n in (3, 4, 5, 6) if len(w) >= n]
    qs += [" ".join(w[i:i + 3]) for i in range(0, min(len(w) - 2, 6), 2)]
    return list(dict.fromkeys(qs + extra))

def fetch(url):
    try:
        r = requests.get(url, timeout=20)
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.img_match (id bigserial primary key, at timestamptz default now(), ref_asin text, asin text, sim real, data jsonb)")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    def embed(imgs):
        with torch.no_grad():
            f = model.get_image_features(**proc(images=imgs, return_tensors="pt"))
            if not torch.is_tensor(f):
                f = model.visual_projection(f.pooler_output)
        return torch.nn.functional.normalize(f, dim=-1)

    extra = [q.strip() for q in (os.environ.get("QUERIES") or "").split("|") if q.strip()]
    tot = 0
    for ref in (os.environ.get("REFS") or "").split():
        row = cx.execute("select urls from deals.asin_images where asin=%s", (ref,)).fetchone()
        try:
            it = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + ref, params={"marketplaceIds": df.MK, "includedData": "summaries,images"}, quiet=True, tries=4)
        except Exception as e:
            print("  ref ERR", str(e)[:60]); continue
        title = df._parse_item(it)["title"]
        urls = [i["url"] for i in (row[0] if row else []) if i.get("url") and "_SL" not in i["url"]][:6]
        refimgs = [x for x in (fetch(u) for u in urls) if x]
        if not refimgs:
            print("  no ref images for one ref"); continue
        R = embed(refimgs)
        seen = {}
        for q in queries_for(title, extra):
            for p in df.catalog_search(c, q, size=20, pages=2):
                if p["asin"] and p["asin"] != ref and p["asin"] not in seen and p.get("image"):
                    seen[p["asin"]] = p
        scored = []
        for a, p in seen.items():
            im = fetch(p["image"])
            if not im: continue
            s = float((embed([im]) @ R.T).max())
            scored.append((s, a, p))
        scored.sort(key=lambda x: -x[0])
        top = [x for x in scored if x[0] >= 0.75][:40]
        offers = df.offers_batch(c, [a for _, a, _ in top])
        for s, a, p in top:
            d = {k: p.get(k) for k in ("title", "brand", "rank", "rank_cat", "list_price")}
            d["offers"] = offers.get(a)
            cx.execute("insert into deals.img_match(ref_asin, asin, sim, data) values (%s,%s,%s,%s)", (ref, a, round(s, 3), json.dumps(d)))
        tot += len(top)
        print("img_match: ref scanned, %d candidates searched, %d kept (sim>=0.75)" % (len(scored), len(top)))
    print("img_match: done %d rows" % tot)

main()
