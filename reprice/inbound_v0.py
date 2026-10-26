"""READ-ONLY: legacy inbound shipments (ship-from, destination FC, items) + product weights report."""
import json, os, datetime as dt, csv, io
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE)
os.makedirs("/tmp/so", exist_ok=True)
now = dt.datetime.now(dt.timezone.utc)
out = []
for st in ("WORKING","SHIPPED","IN_TRANSIT","DELIVERED","CHECKED_IN","RECEIVING","CLOSED","CANCELLED","DELETED","ERROR"):
    tok = None
    for _ in range(30):
        p = {"MarketplaceId": spapi.MARKETPLACE, "QueryType": "DATE_RANGE", "ShipmentStatusList": st,
             "LastUpdatedAfter": (now - dt.timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ"), "LastUpdatedBefore": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if tok: p = {"MarketplaceId": spapi.MARKETPLACE, "QueryType": "NEXT_TOKEN", "NextToken": tok}
        try: r = spapi.call(c, "GET", "/fba/inbound/v0/shipments", params=p, quiet=True, tries=3)
        except spapi.SpError as e: print("ERR", st, str(e)[:200]); break
        pl = r.get("payload") or {}
        for s in pl.get("ShipmentData") or []:
            a = s.get("ShipFromAddress") or {}
            out.append({"id": s.get("ShipmentId"), "name": s.get("ShipmentName"), "status": s.get("ShipmentStatus"), "fc": s.get("DestinationFulfillmentCenterId"),
                        "from": [a.get("City"), a.get("StateOrProvinceCode"), a.get("PostalCode"), a.get("CountryCode")], "boxSrc": s.get("BoxContentsSource")})
        tok = pl.get("NextToken")
        if not tok: break
print("v0 shipments:", len(out))
for s in sorted(out, key=lambda x: x["name"] or ""):
    print(json.dumps(s))
for s in out:
    try:
        r = spapi.call(c, "GET", "/fba/inbound/v0/shipments/%s/items" % s["id"], quiet=True, tries=3)
        s["items"] = {i["SellerSKU"]: i.get("QuantityShipped") for i in (r.get("payload") or {}).get("ItemData") or []}
    except spapi.SpError as e: s["items"] = {"err": str(e)[:100]}
json.dump(out, open("/tmp/so/v0.json", "w"), indent=1)
st, txt = spapi.report(c, "GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA", wait_minutes=20)
print("fees report:", st, len(txt))
open("/tmp/so/fees.tsv", "w").write(txt)
print(txt[:400])
