"""READ-ONLY: list recent inbound plans with ship-from city, destination FC address, boxes (dims/weight)."""
import json, os, datetime as dt
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
B = "/inbound/fba/2024-03-20"
c = spapi.load_creds(HERE)
def paged(path, key, extra=None):
    out = []; tok = None
    for _ in range(60):
        p = {"pageSize": 20}
        if extra: p.update(extra)
        if tok: p["paginationToken"] = tok
        try: r = spapi.call(c, "GET", path, params=p, quiet=True, tries=3)
        except spapi.SpError as e: print("ERR", path, str(e)[:200]); break
        out += r.get(key) or []
        tok = (r.get("pagination") or {}).get("nextToken")
        if not tok: break
    return out
plans = paged(B + "/inboundPlans", "inboundPlans")
print("plans total", len(plans))
cut = (dt.datetime.utcnow() - dt.timedelta(days=150)).isoformat()
rows = []
for p in sorted(plans, key=lambda x: x.get("createdAt", ""), reverse=True):
    if p.get("createdAt", "") < cut: continue
    pid = p["inboundPlanId"]
    full = spapi.call(c, "GET", B + "/inboundPlans/" + pid, quiet=True, tries=3)
    src = full.get("sourceAddress") or {}
    rec = {"plan": pid, "name": full.get("name"), "status": full.get("status"), "created": full.get("createdAt"),
           "src": [src.get("city"), src.get("stateOrProvinceCode"), src.get("postalCode")], "shipments": []}
    for sh in full.get("shipments") or []:
        sid = sh.get("shipmentId")
        try: d = spapi.call(c, "GET", B + "/inboundPlans/%s/shipments/%s" % (pid, sid), quiet=True, tries=3)
        except spapi.SpError as e: d = {"err": str(e)[:150]}
        dest = d.get("destination") or {}
        addr = dest.get("address") or {}
        rec["shipments"].append({"id": sid, "status": d.get("status"), "fc": dest.get("warehouseId"),
            "addr": [addr.get("addressLine1"), addr.get("city"), addr.get("stateOrProvinceCode"), addr.get("postalCode")],
            "tracking": (d.get("trackingDetails") or {}), "selectedCarrier": d.get("selectedTransportationOptionId")})
    boxes = paged(B + "/inboundPlans/" + pid + "/boxes", "boxes")
    rec["boxes"] = [{"dims": b.get("dimensions"), "w": b.get("weight"), "qty": b.get("quantity"), "units": sum(i.get("quantity", 0) for i in b.get("items") or [])} for b in boxes]
    rows.append(rec)
    print(json.dumps(rec)[:900])
os.makedirs("/tmp/so", exist_ok=True)
json.dump(rows, open("/tmp/so/plans.json", "w"), indent=1)
