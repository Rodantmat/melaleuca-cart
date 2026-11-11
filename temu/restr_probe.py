"""Print only the reason codes of the listing-restrictions check for a few ASINs (read-only)."""
import os, sys, re, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reprice"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spapi, validate
c = spapi.load_creds(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reprice"))
sid = validate._seller_id(c)
print("seller id found:", bool(sid))
for a in sys.argv[1:]:
    try:
        j = spapi.call(c, "GET", "/listings/2021-08-01/restrictions", params={"asin": a, "sellerId": sid, "marketplaceIds": spapi.MARKETPLACE, "conditionType": "new_new"}, quiet=True, tries=2)
        rs = j.get("restrictions") or []
        print(" ", a[:4] + "..", "restrictions:", len(rs), [[x.get("reasons") and [(y.get("reasonCode"), (y.get("message") or "")[:70]) for y in x["reasons"]]] for x in rs][:2])
    except Exception as e:
        print(" ", a[:4] + "..", "error", str(e)[:150])
