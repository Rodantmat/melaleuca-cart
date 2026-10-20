"""Read-only: distinct ship-from addresses of past inbound shipments (v0 getShipments). Changes nothing."""
import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
def main():
    c = spapi.load_creds(HERE)
    seen = {}
    st = "WORKING,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,RECEIVING,CLOSED,CANCELLED,DELETED,ERROR".split(",")
    tok = None
    for _ in range(40):
        p = {"MarketplaceId": "ATVPDKIKX0DER", "QueryType": "SHIPMENT", "ShipmentStatusList": ",".join(st)} if not tok else {"MarketplaceId": "ATVPDKIKX0DER", "QueryType": "NEXT_TOKEN", "NextToken": tok}
        try:
            r = spapi.call(c, "GET", "/fba/inbound/v0/shipments", params=p, quiet=True, tries=3)
        except spapi.SpError as e:
            print("ERR", e); break
        pl = r.get("payload") or {}
        for s in pl.get("ShipmentData") or []:
            a = s.get("ShipFromAddress") or {}
            k = json.dumps(a, sort_keys=True)
            seen.setdefault(k, []).append((s.get("ShipmentId"), s.get("ShipmentName")))
        tok = pl.get("NextToken")
        if not tok: break
    for k, v in seen.items():
        print(len(v), k, v[:3])
main()
