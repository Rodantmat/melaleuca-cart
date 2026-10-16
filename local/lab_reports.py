"""LAB (read only): can we pull the Sales & Traffic business report by child ASIN (Buy Box %, sessions, conversion, units, sales)?"""
import json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amazon_feed as af
from lab_pricing import creds, OUT

c = creds()
end = dt.date.today() - dt.timedelta(days=1)
start = end - dt.timedelta(days=29)
body = {"reportType": "GET_SALES_AND_TRAFFIC_REPORT", "marketplaceIds": [af.MARKETPLACE],
        "dataStartTime": start.isoformat() + "T00:00:00Z", "dataEndTime": end.isoformat() + "T23:59:59Z",
        "reportOptions": {"dateGranularity": "MONTH", "asinGranularity": "CHILD"}}
try:
    rid = af.api(c, "POST", "/reports/2021-06-30/reports", body=body)["reportId"]
except Exception as e:
    print("CREATE FAILED:", str(e)[:500]); sys.exit(0)
print("report", rid, start, end)
doc = None
for _ in range(60):
    r = af.api(c, "GET", "/reports/2021-06-30/reports/" + rid)
    st = r.get("processingStatus"); print("  status", st); sys.stdout.flush()
    if st in ("DONE", "FATAL", "CANCELLED"):
        doc = r.get("reportDocumentId"); break
    time.sleep(20)
if not doc:
    print("no document"); sys.exit(0)
blob = af.download(c, doc)
txt = af.decode(blob) if not isinstance(blob, str) else blob
open(os.path.join(OUT, "sales_traffic.json"), "w", encoding="utf-8").write(txt)
j = json.loads(txt)
rows = j.get("salesAndTrafficByAsin") or []
print("rows", len(rows), "keys", list(j.keys()))
if rows:
    print(json.dumps(rows[0])[:700])
want = ("B017JIL4GY", "B018C56968", "B018C5698G", "B00AA68KJC", "B0FKZKPLXK")
for r in rows:
    a = r.get("childAsin") or r.get("parentAsin")
    if a in want:
        print(a, json.dumps(r)[:600])
bb = [(r.get("trafficByAsin") or {}).get("buyBoxPercentage") for r in rows]
print("buy box % present for", sum(1 for x in bb if x is not None), "of", len(rows))
