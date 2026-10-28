"""READ-ONLY probe: build a TEST plan (named TEST-DELETE-ME), list the placement options (fees, destinations),
look at the shipments and transportation options, then ALWAYS cancel the plan. Never confirms anything."""
import json, sys, os, time
import sd_tools as S

def show(title, obj, n=6000):
    print("\n##", title); print(json.dumps(obj, indent=1)[:n])

path = sys.argv[1]
c = S._credentials()
r = S.send_to_amazon(path, say=print, cancel_after=False, placement=True)
pid = r["inboundPlanId"]
INB = S.INB
try:
    opts = S._paged(c, INB + "/inboundPlans/%s/placementOptions" % pid, "placementOptions")
    print("placement options:", len(opts))
    for o in opts:
        print(" option", o.get("placementOptionId"), o.get("status"), "shipments:", len(o.get("shipmentIds") or []), "fees:", json.dumps(o.get("fees")), "discounts:", json.dumps(o.get("discounts")), "expires:", o.get("expiration"))
    plan = S._api(c, "GET", INB + "/inboundPlans/" + pid)
    show("plan (trimmed)", {k: plan.get(k) for k in ("status", "sourceAddress", "shipments", "placementOptions", "packingOptions")}, 3000)
    seen = set()
    for o in opts:
        for sid in (o.get("shipmentIds") or []):
            if sid in seen: continue
            seen.add(sid)
            try:
                sh = S._api(c, "GET", INB + "/inboundPlans/%s/shipments/%s" % (pid, sid))
                show("shipment %s (option %s)" % (sid, o.get("placementOptionId")), sh, 2500)
            except Exception as e:
                print("shipment", sid, "ERR", str(e)[:400])
        break_after = False
    # transportation options for the first option (generation only, not a purchase)
    o = opts[0] if opts else None
    if o:
        sids = o.get("shipmentIds") or []
        cfg = [{"shipmentId": s, "readyToShipWindow": {"start": time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() + 3 * 86400))}} for s in sids]
        try:
            op = S._api(c, "POST", INB + "/inboundPlans/%s/transportationOptions" % pid, {"placementOptionId": o["placementOptionId"], "shipmentTransportationConfigurations": cfg})
            S._wait(c, op, "transportation options", print)
            for s in sids[:3]:
                t = S._paged(c, INB + "/inboundPlans/%s/transportationOptions" % pid, "transportationOptions", {"placementOptionId": o["placementOptionId"], "shipmentId": s})
                show("transportation options for %s" % s, t, 3500)
        except Exception as e:
            print("transportation ERR", str(e)[:1200])
finally:
    try:
        S._api(c, "PUT", INB + "/inboundPlans/%s/cancellation" % pid); print("\ntest plan cancelled:", pid)
    except Exception as e:
        print("CANCEL FAILED", pid, str(e)[:300])
