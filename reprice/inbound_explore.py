import json, os, sys, collections
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
B = "/inbound/fba/2024-03-20"
c = spapi.load_creds(HERE)
def paged(path, key):
    out = []; tok = None
    for _ in range(50):
        p = {"pageSize": 20}
        if tok: p["paginationToken"] = tok
        try:
            r = spapi.call(c, "GET", path, params=p, quiet=True, tries=3)
        except spapi.SpError as e:
            print("ERR", path, str(e)[:200]); break
        out += r.get(key) or []
        tok = (r.get("pagination") or {}).get("nextToken")
        if not tok: break
    return out
plans = paged(B + "/inboundPlans", "inboundPlans")
mine = [p for p in plans if p.get("name") == "2026-10-SanDiego"]
print("plans named 2026-10-SanDiego:", [(p["inboundPlanId"], p["status"], p["createdAt"]) for p in mine])
for p in mine:
    pid = p["inboundPlanId"]
    full = spapi.call(c, "GET", B + "/inboundPlans/" + pid, quiet=True, tries=3)
    print("PLAN", pid, full.get("status"), full.get("name"), "src:", json.dumps(full.get("sourceAddress")))
    print(" placementOptions:", json.dumps(full.get("placementOptions"))[:300], "shipments:", json.dumps(full.get("shipments"))[:300], "packingOptions:", json.dumps(full.get("packingOptions"))[:200])
    items = paged(B + "/inboundPlans/" + pid + "/items", "items")
    print(" plan items:", len(items), "units", sum(i.get("quantity", 0) for i in items), "exp sample", [i.get("expiration") for i in items if i.get("expiration")][:3], "expired-count", sum(1 for i in items if i.get("expiration")))
    print(" owners:", collections.Counter((i.get("prepOwner"), i.get("labelOwner")) for i in items))
    boxes = paged(B + "/inboundPlans/" + pid + "/boxes", "boxes")
    print(" boxes:", len(boxes))
    tot = collections.Counter()
    for b in boxes:
        its = b.get("items") or []
        u = sum(i.get("quantity", 0) for i in its)
        for i in its: tot[i["msku"]] += i["quantity"]
        print("  ", b.get("boxId", "")[:14], b.get("packageId", ""), json.dumps(b.get("dimensions")), json.dumps(b.get("weight")), "skus", len(its), "units", u, "qty", b.get("quantity"))
    print(" box totals: skus", len(tot), "units", sum(tot.values()))
    pi = {i["msku"]: i["quantity"] for i in items}
    diff = {k: (pi.get(k), tot.get(k)) for k in set(pi) | set(tot) if pi.get(k) != tot.get(k)}
    print(" plan-vs-boxes differences:", diff)
    json.dump({"items": pi, "boxes": [{"dims": b.get("dimensions"), "w": b.get("weight"), "items": {i["msku"]: i["quantity"] for i in b.get("items") or []}} for b in boxes]}, open("/tmp/plan_dump.json", "w"))
    print("DUMP", json.dumps({"boxes": [{"dims": b.get("dimensions"), "w": b.get("weight"), "items": {i["msku"]: i["quantity"] for i in b.get("items") or []}} for b in boxes]}))
