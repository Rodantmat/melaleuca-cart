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

def load_embed():
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    def embed(imgs):
        with torch.no_grad():
            f = model.get_image_features(**proc(images=imgs, return_tensors="pt"))
            if not torch.is_tensor(f):
                f = f.pooler_output
        return torch.nn.functional.normalize(f, dim=-1)
    return embed


def ensure_images(cx, c, ref):
    row = cx.execute("select urls from deals.asin_images where asin=%s", (ref,)).fetchone()
    if row:
        return row[0]
    cx.execute("create table if not exists deals.asin_images (asin text primary key, main_url text, urls jsonb, at timestamptz default now())")
    r = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + ref, params={"marketplaceIds": df.MK, "includedData": "images"}, quiet=True, tries=4)
    imgs = [{"variant": im.get("variant"), "url": im.get("link"), "w": im.get("width")} for g in (r.get("images") or []) for im in (g.get("images") or [])]
    main = next((i["url"] for i in imgs if i["variant"] == "MAIN"), imgs[0]["url"] if imgs else None)
    cx.execute("insert into deals.asin_images(asin, main_url, urls) values (%s,%s,%s) on conflict (asin) do update set urls=excluded.urls, main_url=excluded.main_url, at=now()", (ref, main, json.dumps(imgs)))
    return imgs


def match_ref(cx, c, embed, ref, extra=(), store=True):
    """Returns (n_candidates_searched, kept rows [(sim, asin, parsed, offers)]) for one reference ASIN."""
    it = spapi.call(c, "GET", "/catalog/2022-04-01/items/" + ref, params={"marketplaceIds": df.MK, "includedData": "summaries,images"}, quiet=True, tries=4)
    title = df._parse_item(it)["title"]
    urls = [i["url"] for i in ensure_images(cx, c, ref) if i.get("url") and "_SL" not in i["url"]][:6]
    refimgs = [x for x in (fetch(u) for u in urls) if x]
    if not refimgs:
        return 0, []
    R = embed(refimgs)
    seen = {}
    for q in queries_for(title, list(extra)):
        for p in df.catalog_search(c, q, size=20, pages=2):
            if p["asin"] and p["asin"] != ref and p["asin"] not in seen and p.get("image"):
                seen[p["asin"]] = p
    scored = []
    for a, p in seen.items():
        im = fetch(p["image"])
        if not im:
            continue
        scored.append((float((embed([im]) @ R.T).max()), a, p))
    scored.sort(key=lambda x: -x[0])
    top = [x for x in scored if x[0] >= 0.75][:40]
    offers = df.offers_batch(c, [a for _, a, _ in top])
    out = [(s, a, p, offers.get(a)) for s, a, p in top]
    if store:
        for s, a, p, o in out:
            d = {k: p.get(k) for k in ("title", "brand", "rank", "rank_cat", "list_price")}
            d["offers"] = o
            cx.execute("insert into deals.img_match(ref_asin, asin, sim, data) values (%s,%s,%s,%s)", (ref, a, round(s, 3), json.dumps(d)))
    return len(scored), out


def main():
    cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    cx.execute("create table if not exists deals.img_match (id bigserial primary key, at timestamptz default now(), ref_asin text, asin text, sim real, data jsonb)")
    c = spapi.load_creds(os.path.join(HERE, "..", "reprice"))
    embed = load_embed()

    extra = [q.strip() for q in (os.environ.get("QUERIES") or "").split("|") if q.strip()]
    tot = 0
    for ref in (os.environ.get("REFS") or "").split():
        try:
            n, out = match_ref(cx, c, embed, ref, extra)
        except Exception as e:
            print("  ref ERR", str(e)[:60]); continue
        tot += len(out)
        print("img_match: ref scanned, %d candidates searched, %d kept (sim>=0.75)" % (n, len(out)))
    print("img_match: done %d rows" % tot)


if __name__ == "__main__":
    main()
