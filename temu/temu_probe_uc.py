"""Temu probe, stealth-Chrome variant (SeleniumBase UC mode, real Chrome under xvfb).
Separates "Temu blocks the IP" from "Temu blocks the automated browser fingerprint".
Images, video and fonts are blocked. No proxy here: network = whatever the workflow set up (Proton VPN).
"""
import json, os, re, time
from seleniumbase import SB

QUERY = os.environ.get("TEMU_QUERY", "dog shirt")
EXTRACT_JS = r"""
const out=[]; const seen=new Set();
for (const a of document.querySelectorAll('a[href*="goods_id="], a[href*="-g-"]')) {
  const m = a.href.match(/goods_id=(\d+)/) || a.href.match(/-g-(\d+)\.html/);
  if (!m || seen.has(m[1])) continue;
  let card=a; for (let k=0;k<6 && card.parentElement;k++){ if (/\$\s?\d/.test(card.innerText||'')) break; card=card.parentElement; }
  const txt=(card.innerText||'').replace(/\s+/g,' ').trim();
  const prices=[...txt.matchAll(/\$\s?([\d,]+(?:\.\d{1,2})?)/g)].map(x=>x[1]);
  const img=card.querySelector('img[alt]');
  let title=(img && img.alt || '').replace(/^item picture\s*/i,'').trim() || txt.slice(0,120);
  seen.add(m[1]); out.push({goods_id:m[1], title:title.slice(0,140), price:prices[0]||null, url:a.href.split('&_oak')[0]});
}
return out;
"""


def visit(sb, label, url, scrolls=0, wait=7):
    t0 = time.time()
    try:
        sb.uc_open_with_reconnect(url, 4)
    except Exception as e:
        print(json.dumps({"page": label, "error": str(e)[:200]}), flush=True); return []
    sb.sleep(wait)
    for _ in range(scrolls):
        sb.execute_script("window.scrollBy(0, 2500)"); sb.sleep(2.2)
    cur, title = sb.get_current_url(), sb.get_title()
    body = re.sub(r"\s+", " ", sb.execute_script("return (document.body && document.body.innerText || '').slice(0,300)") or "")
    blk = "LOGIN_WALL" if ("login" in cur.lower() or "sign in / register" in body.lower()) else ("CAPTCHA" if "captcha" in cur.lower() or "verif" in title.lower() else None)
    items = [] if blk else (sb.execute_script(EXTRACT_JS) or [])
    priced = [i for i in items if i.get("price")]
    print(json.dumps({"page": label, "secs": round(time.time() - t0, 1), "final_url": cur[:160], "title": title[:80], "block": blk,
                      "products": len(items), "with_price": len(priced), "body_head": body[:160]}), flush=True)
    for i in priced[:8]:
        print("   ", json.dumps(i)[:300], flush=True)
    return items


def main():
    print("=== TEMU PROBE (stealth UC Chrome)  query=%r  images/video/fonts blocked" % QUERY, flush=True)
    with SB(uc=True, xvfb=True, locale="en-US", block_images=True) as sb:
        try:
            sb.execute_cdp_cmd("Network.enable", {})
            sb.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*.mp4", "*.webm", "*.woff", "*.woff2", "*.ttf", "*.otf"]})
        except Exception as e:
            print("cdp block skipped:", str(e)[:120], flush=True)
        home = visit(sb, "homepage", "https://www.temu.com/", scrolls=6, wait=9)
        visit(sb, "search", "https://www.temu.com/search_result.html?search_key=" + QUERY.replace(" ", "%20"), scrolls=2)
        if home:
            visit(sb, "product", "https://www.temu.com/goods.html?goods_id=" + home[0]["goods_id"])
        visit(sb, "homepage_again", "https://www.temu.com/", scrolls=3, wait=6)


if __name__ == "__main__":
    main()
