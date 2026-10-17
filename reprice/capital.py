"""Read-only: Amazon balance (open settlement), FBA inventory report, inbound shipments by month.  usage: python capital.py -> state/capital.json, state/inbound.tsv, state/planning_latest.tsv"""
import datetime as dt, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import spapi
ST = os.path.join(HERE, "state"); os.makedirs(ST, exist_ok=True)
MK = spapi.MARKETPLACE
c = spapi.load_creds(HERE)
out = {"ts": dt.datetime.utcnow().isoformat()}

def tryit(label, fn):
    try:
        return fn()
    except Exception as e:
        print(label, "FAILED:", str(e)[:300]); out.setdefault("errors", {})[label] = str(e)[:300]; return None

# 0. transactions by status (held / deferred money)
def tx():
    after = (dt.datetime.utcnow() - dt.timedelta(days=45)).strftime("%Y-%m-%dT00:00:00Z")
    tot, n, tok, cnt = {}, 0, None, {}
    while True:
        ps = {"postedAfter": after, "marketplaceId": MK}
        if tok: ps = {"nextToken": tok}
        r = spapi.call(c, "GET", "/finances/2024-06-19/transactions", params=ps, quiet=True)
        r = r.get("payload") or r
        for t in r.get("transactions", []):
            st = t.get("transactionStatus", "?"); a = (t.get("totalAmount") or {}).get("currencyAmount") or 0
            tot[st] = tot.get(st, 0) + a; cnt[st] = cnt.get(st, 0) + 1
            if st in ("DEFERRED", "DEFERRED_RELEASED") or st == "OPEN": pass
        n += len(r.get("transactions", []))
        tok = (r.get("payload") or r).get("nextToken") or r.get("nextToken")
        if not tok or n > 20000: break
        time.sleep(0.6)
    out["tx_by_status"] = {k: round(v, 2) for k, v in tot.items()}; out["tx_counts"] = cnt
    print("transactions by status:", out["tx_by_status"], cnt)
tryit("transactions", tx)
if os.environ.get("ONLY") == "tx":
    json.dump(out, open(os.path.join(ST, "capital_tx.json"), "w"), indent=1); sys.exit(0)

# 1. settlement groups
def groups():
    after = (dt.datetime.utcnow() - dt.timedelta(days=60)).strftime("%Y-%m-%dT00:00:00Z")
    r = spapi.call(c, "GET", "/finances/v0/financialEventGroups", params={"MaxResultsPerPage": 100, "FinancialEventGroupStartedAfter": after})
    g = (r.get("payload") or {}).get("FinancialEventGroupList", [])
    out["groups"] = [{k: x.get(k) for k in ("FinancialEventGroupId", "ProcessingStatus", "FundTransferStatus", "OriginalTotal", "ConvertedTotal", "BeginningBalance", "FinancialEventGroupStart", "FinancialEventGroupEnd", "FundTransferDate")} for x in g]
    print("groups:", len(g))
    for x in out["groups"]:
        print("  ", x["ProcessingStatus"], x["FundTransferStatus"], x["OriginalTotal"], x["FinancialEventGroupStart"], x["FinancialEventGroupEnd"])
tryit("groups", groups)

# 2. inventory planning report
def plan():
    st, txt = spapi.report(c, "GET_FBA_INVENTORY_PLANNING_DATA")
    if st == "DONE":
        open(os.path.join(ST, "planning_latest.tsv"), "w", encoding="utf-8").write(txt); print("planning rows", len(txt.splitlines()) - 1)
    else:
        print("planning", st)
tryit("planning", plan)

# 3. inbound shipments, month by month (last 9 months)
def inbound():
    rows, seen = [], set()
    today = dt.datetime.utcnow()
    for k in range(9, -1, -1):
        s = (today.replace(day=1) - dt.timedelta(days=30 * k)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        e = min(today, (s + dt.timedelta(days=32)).replace(day=1))
        ps = {"MarketplaceId": MK, "QueryType": "DATE_RANGE", "LastUpdatedAfter": s.strftime("%Y-%m-%dT%H:%M:%SZ"), "LastUpdatedBefore": e.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "ShipmentStatusList": "WORKING,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,RECEIVING,CLOSED"}
        r = spapi.call(c, "GET", "/fba/inbound/v0/shipments", params=ps, quiet=True)
        for sh in (r.get("payload") or {}).get("ShipmentData", []):
            sid = sh["ShipmentId"]
            if sid in seen:
                continue
            seen.add(sid)
            it = spapi.call(c, "GET", "/fba/inbound/v0/shipments/%s/items" % sid, quiet=True)
            for x in (it.get("payload") or {}).get("ItemData", []):
                rows.append([sid, sh.get("ShipmentStatus"), s.strftime("%Y-%m"), x.get("SellerSKU"), x.get("QuantityShipped"), x.get("QuantityReceived")])
            time.sleep(0.6)
        print("inbound window", s.strftime("%Y-%m"), "shipments so far", len(seen)); sys.stdout.flush()
    open(os.path.join(ST, "inbound.tsv"), "w").write("shipment\tstatus\twindow\tsku\tshipped\treceived\n" + "\n".join("\t".join(str(v) for v in r) for r in rows) + "\n")
tryit("inbound", inbound)
json.dump(out, open(os.path.join(ST, "capital.json"), "w"), indent=1)
