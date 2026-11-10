# Temu bridge

Products and prices from Temu with **no login, no proxy, no VPN, no browser and no images**. It runs on a plain GitHub runner and costs nothing.

## How it works
Temu sends fully rendered pages (products and prices in the HTML) to Pinterest's link crawler, so it can show product pins. `temu_bridge.py` asks for pages the same way over plain HTTPS. It reads only the HTML (about 0.3-0.9 MB per page) and never loads images.

| Call | What you get |
|---|---|
| `search(query)` | about 40 products for a keyword (Temu's own search, first page): id, title, price, list price, link, image URL |
| `product(goods_id)` | title, price, currency, in stock, rating, review count, category, description, image URLs |

Limits: search returns the first page only, and no sold counts or ratings appear in search results (product lookup has the rating). Some big-ticket product pages carry no price block; use the search price for those. Best-sellers renders empty at times, so it is off by default.

## Run it
GitHub Actions -> **Temu bridge** -> inputs `search` (keywords separated by `|`), `ids` (comma list), `best` (0/1).
Results: branch **temu-data** -> `temu/latest.json`, `temu/latest.log`, `temu/runs/<UTC time>.json`.

Local: `pip install curl_cffi && python temu/temu_bridge.py --search "dog shirt|golden retriever mug" --ids 603242230592430`

## Network notes (tested 2026-11-10)
- Normal browsers (Playwright, stealth Chrome) are sent to login or a captcha from GitHub, Proton VPN and Cloudflare WARP IPs alike. Temu's JavaScript does that, not the IP.
- Plain HTTPS with the crawler header works from the plain runner IP. Proton (`PROTON_WG_CONF` secret) and WARP were also tested and work, but they aren't needed.
- The paid proxy is never used.
