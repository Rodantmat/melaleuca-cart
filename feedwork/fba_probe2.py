"""READ-ONLY: look at REAL confirmed shipments to learn (a) which fields carry carrier ship-to / alternate address, (b) box ids,
(c) whether v0 getLabels thermal 4x6 works. Writes/changes nothing."""
import json, os, sys, urllib.request, urllib.parse
import sd_tools as S
c = S._credentials()
INB = S.INB
plans = S._paged(c, INB + "/inboundPlans", "inboundPlans")
print("plans:", len(plans))
for p in sorted(plans, key=lambda x: x.get("createdAt", ""), reverse=True)[:25]:
    print(" ", p.get("createdAt", "")[:10], p.get("status"), p.get("name"), p["inboundPlanId"])
done = 0
for p in sorted(plans, key=lambda x: x.get("createdAt", ""), reverse=True):
    if "TEST" in (p.get("name") or "").upper(): continue
    pid = p["inboundPlanId"]
    try: full = S._api(c, "GET", INB + "/inboundPlans/" + pid)
    except Exception as e: print("ERR plan", pid, str(e)[:150]); continue
    ships = full.get("shipments") or []
    if not ships: continue
    print("\n##### PLAN", p.get("name"), pid, full.get("status"), "shipments:", json.dumps(ships)[:300])
    for sref in ships[:2]:
        sid = sref["shipmentId"]
        try:
            sh = S._api(c, "GET", INB + "/inboundPlans/%s/shipments/%s" % (pid, sid))
        except Exception as e:
            print("ERR shipment", str(e)[:200]); continue
        print("SHIPMENT keys:", sorted(sh.keys()))
        print(json.dumps(sh, indent=1)[:3500])
        try:
            bx = S._paged(c, INB + "/inboundPlans/%s/shipments/%s/boxes" % (pid, sid), "boxes")
            print("BOXES", len(bx), json.dumps(bx[:2])[:600])
        except Exception as e: bx = []; print("boxes ERR", str(e)[:200])
        conf = sh.get("shipmentConfirmationId")
        ids = [b.get("boxId") for b in bx if b.get("boxId")]
        if conf and ids and done < 2:
            tok = S._token(c)
            for pt in ("PackageLabel_Thermal", "PackageLabel_Thermal_Unified", "PackageLabel_Thermal_NonPCP"):
                q = {"PageType": pt, "LabelType": "UNIQUE", "PackageLabelsToPrint": ",".join(ids[:2])}
                url = S.SP_API + "/fba/inbound/v0/shipments/%s/labels?%s" % (conf, urllib.parse.urlencode(q))
                try:
                    req = urllib.request.Request(url, headers={"x-amz-access-token": tok, "User-Agent": S.UA})
                    j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
                    dl = (j.get("payload") or {}).get("DownloadURL")
                    print("LABELS", pt, "OK", bool(dl))
                    if dl:
                        data = urllib.request.urlopen(dl, timeout=60).read()
                        print("  bytes", len(data), data[:8])
                        open("/tmp/so/label_%s.bin" % pt, "wb").write(data)
                except Exception as e:
                    body = getattr(e, "read", lambda: b"")()
                    print("LABELS", pt, "ERR", str(e)[:100], body[:300])
            done += 1
    if done >= 2: break
