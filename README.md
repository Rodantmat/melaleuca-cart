# melaleuca-cart
Private. Automation to add Flipping Magic orders to the Melaleuca cart (never checks out).
- `probe/probe.py` read-only probe, run from Actions > "Melaleuca probe (read only)" > Run workflow.
- Secrets needed: `MELA_USER_1`, `MELA_PASS_1` (Settings > Secrets and variables > Actions).

## Repricer and Buy Box intelligence (reprice/)
- `reprice.yml` (3x/day): refresh order history -> `run.py` (decide + apply, gated) -> `analysis.py` (signals) -> `market.py` -> `bb_intel.py` (reports).
- `bb_web.yml` (daily 09:37 UTC): `bb_web.py` reads the PUBLIC amazon.com offer drawer logged out (own proxy port, no seller account, no API key): Buy Box seller/price, all offers, ratings. Saved in `state/webbb.jsonl`.
  The repricer never raises a price toward a Buy Box that a shopper sees owned by a cheaper rival.
- `bb_intel.py` writes `state/bb_report.tsv` (per product), `state/bb_sellers.tsv` (per rival seller), `state/bb_agreement.tsv` (API vs what shoppers see).
- `sim.py` / `sim_ab.py`: stress simulation and A/B test of engine changes (`SIM_MARKET=calibrated` uses the share curve measured on the real store). The MATCH rule (step toward a rival-owned Buy Box) is built and tested but OFF (`MATCH_ENABLED`): simulated gain ~0.
- Read-only probes: `bb_probe.yml` (SP-API), `bb_web_probe.yml` (public pages).
