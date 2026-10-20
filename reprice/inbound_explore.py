import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
B = "/inbound/fba/2024-03-20"
c = spapi.load_creds(HERE)
for st in (None, "ACTIVE", "VOIDED", "SHIPPED"):
    p = {"pageSize": 30}
    if st: p["status"] = st
    try:
        r = spapi.call(c, "GET", B + "/inboundPlans", params=p, quiet=True, tries=3)
    except spapi.SpError as e:
        print(st, "ERR", str(e)[:200]); continue
    print("== filter", st, len(r.get("inboundPlans") or []))
    for x in r.get("inboundPlans") or []:
        print(" ", x.get("inboundPlanId"), x.get("status"), repr(x.get("name")), x.get("createdAt"))
for pid in ("wfb41f80a7-de10-492a-b729-92343d607040",):
    try:
        x = spapi.call(c, "GET", B + "/inboundPlans/" + pid, quiet=True, tries=2)
        print("plan", pid, x.get("status"), x.get("name"), x.get("lastUpdatedAt"))
    except spapi.SpError as e:
        print("plan", pid, "ERR", str(e)[:200])
