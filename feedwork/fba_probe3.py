"""READ-ONLY: v0 shipments created in Seller Central + test getLabels thermal 4x6 on the latest ones (no changes)."""
import json, os, urllib.request, urllib.parse
import sd_tools as S
c = S._credentials(); tok = S._token(c)
def v0(path, params=None):
    url = S.SP_API + path + (("?" + urllib.parse.urlencode(params, doseq=True)) if params else "")
    req = urllib.request.Request(url, headers={"x-amz-access-token": S._token(c), "User-Agent": S.UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
    except Exception as e:
        return {"ERR": str(e)[:150], "body": getattr(e, "read", lambda: b"")()[:600].decode(errors="replace")}
r = v0("/fba/inbound/v0/shipments", {"ShipmentStatusList": "WORKING,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,RECEIVING,CLOSED", "MarketplaceId": S.MARKETPLACE,
       "LastUpdatedAfter": "2026-06-01T00:00:00Z", "LastUpdatedBefore": "2026-10-28T00:00:00Z"})
ship = (r.get("payload") or {}).get("ShipmentData") or []
print("shipments:", len(ship), r.get("ERR"), r.get("body", ""))
for s in ship[:25]:
    print(" ", s.get("ShipmentId"), s.get("ShipmentStatus"), s.get("DestinationFulfillmentCenterId"), (s.get("ShipFromAddress") or {}).get("City"), s.get("ShipmentName"))
tested = 0
for s in ship:
    sid = s["ShipmentId"]
    for pt in ("PackageLabel_Thermal", "PackageLabel_Thermal_Unified", "PackageLabel_Thermal_NonPCP"):
        for lt, extra in (("UNIQUE", {"PackageLabelsToPrint": [sid + "U000001"]}), ("BARCODE_2D", {"NumberOfPackages": 1})):
            q = {"PageType": pt, "LabelType": lt}; q.update(extra)
            j = v0("/fba/inbound/v0/shipments/%s/labels" % sid, q)
            dl = (j.get("payload") or {}).get("DownloadURL")
            print("LABELS", sid, pt, lt, "OK" if dl else ("ERR " + str(j.get("ERR")) + " " + str(j.get("body"))[:240]))
            if dl:
                data = urllib.request.urlopen(dl, timeout=60).read()
                print("   bytes", len(data), data[:8]); open("/tmp/so/label_%s_%s_%s.bin" % (sid, pt, lt), "wb").write(data)
                tested += 1
    if tested >= 3 or s is ship[2]: break
