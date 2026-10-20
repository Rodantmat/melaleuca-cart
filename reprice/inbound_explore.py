"""Read-only: look at existing inbound plans (2024-03-20) to learn ship-from addresses and shapes. Changes nothing."""
import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s); sys.stdout.flush()
B = "/inbound/fba/2024-03-20"
def main():
    c = spapi.load_creds(HERE)
    try:
        r = spapi.call(c, "GET", B + "/inboundPlans", params={"pageSize": 30}, quiet=True, tries=3)
    except spapi.SpError as e:
        say("LIST ERR", e); open(os.path.join(STATE, "inbound_explore.log"), "w").write("\n".join(LOG)); return
    plans = r.get("inboundPlans") or []
    say("plans:", len(plans))
    for p in plans:
        say(" ", p.get("inboundPlanId"), p.get("status"), p.get("name"), p.get("createdAt"), json.dumps(p.get("sourceAddress")))
    for p in plans[:3]:
        pid = p["inboundPlanId"]
        for sub in ("", "/items", "/boxes", "/packingOptions"):
            try:
                x = spapi.call(c, "GET", B + "/inboundPlans/" + pid + sub, params={"pageSize": 5} if sub else None, quiet=True, tries=2)
                say("==", pid, sub or "plan", json.dumps(x)[:1800])
            except spapi.SpError as e:
                say("==", pid, sub, "ERR", str(e)[:300])
    open(os.path.join(STATE, "inbound_explore.log"), "w").write("\n".join(LOG))
main()
