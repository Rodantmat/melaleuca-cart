"""READ-ONLY check of one finished FBA shipment at Amazon and Shippo. Prints statuses only (no addresses, no credentials)."""
import os, re, sys, json, urllib.request
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
plan, ship, txs = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
c = spapi.load_creds(HERE)
try:
    r = spapi.call(c, "GET", "/inbound/fba/2024-03-20/inboundPlans/%s/shipments/%s" % (plan, ship), tries=3, quiet=True)
    td = r.get("trackingDetails") or {}
    spd = (td.get("spdTrackingDetail") or {}).get("spdTrackingItems") or []
    print("AMAZON shipment:", r.get("shipmentConfirmationId"), "| status:", r.get("status"), "| destination:", (r.get("destination") or {}).get("warehouseId"),
          "| window:", (r.get("selectedDeliveryWindow") or {}).get("startDate", "")[:10], "-", (r.get("selectedDeliveryWindow") or {}).get("endDate", "")[:10])
    print("AMAZON tracking items:", [(str(i.get("trackingId"))[-4:], i.get("trackingNumberValidationStatus")) for i in spd])
    b = spapi.call(c, "GET", "/inbound/fba/2024-03-20/inboundPlans/%s/shipments/%s/boxes" % (plan, ship), params={"pageSize": 50}, tries=3, quiet=True)
    bx = b.get("boxes") or []
    print("AMAZON boxes:", len(bx), "| units:", sum(i.get("quantity", 0) for x in bx for i in (x.get("items") or [])), "| skus:", len({i.get("msku") for x in bx for i in (x.get("items") or [])}))
    p = spapi.call(c, "GET", "/inbound/fba/2024-03-20/inboundPlans/%s" % plan, tries=3, quiet=True)
    print("AMAZON plan status:", p.get("status"), "| shipments in plan:", len(p.get("shipments") or []))
except spapi.SpError as e:
    print("AMAZON ERROR", str(e).replace("\n", " ")[:300])
tok = ""
for k in ("SHIPPO_LIVE_TOKEN", "SHIPPO_LIVE_API_KEY", "SHIPPO_LIVE_KEY", "SHIPPO_API_KEY"):
    v = os.environ.get(k, "").strip()
    if v.startswith("shippo_live_"): tok = v
if not tok:
    m = re.search(r"shippo_live_[A-Za-z0-9]+", os.environ.get("CRED_ENV", ""))
    tok = m.group(0) if m else ""
if not tok:
    print("SHIPPO: no live token available on GitHub - not checked")
else:
    for t in txs:
        try:
            req = urllib.request.Request("https://api.goshippo.com/transactions/" + t, headers={"Authorization": "ShippoToken " + tok})
            d = json.load(urllib.request.urlopen(req, timeout=60))
            print("SHIPPO label ..%s | status: %s | tracking ..%s | tracking_status: %s | test: %s | has label: %s | has invoice: %s | messages: %s" % (
                t[-4:], d.get("status"), str(d.get("tracking_number"))[-4:], d.get("tracking_status"), d.get("test"), bool(d.get("label_url")),
                bool(d.get("commercial_invoice_url")), [str(m.get("text"))[:80] for m in (d.get("messages") or [])]))
        except Exception as e:
            print("SHIPPO ERROR ..%s %s" % (t[-4:], str(e)[:120]))
