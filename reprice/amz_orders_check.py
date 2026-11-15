"""READ-ONLY: can the SP-API app read orders and buyer shipping addresses? Prints status codes/counts only - no buyer data."""
import os, datetime as dt
import spapi
HERE = os.path.dirname(os.path.abspath(__file__)); c = spapi.load_creds(HERE)
since = (dt.datetime.utcnow() - dt.timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
def safe(path, params=None):
    try:
        r = spapi.call(c, "GET", path, params=params, tries=2, quiet=True); return r
    except Exception as e:
        print("  ->", str(e)[:200]); return None
print("1) getOrders (45d)")
r = safe("/orders/v0/orders", {"MarketplaceIds": spapi.MARKETPLACE, "CreatedAfter": since})
orders = ((r or {}).get("payload") or {}).get("Orders", []) if isinstance(r, dict) else []
print("   orders returned:", len(orders), "| channels:", sorted({o.get("FulfillmentChannel") for o in orders}))
mfn = [o for o in orders if o.get("FulfillmentChannel") == "MFN"] or orders
if mfn:
    oid = mfn[0]["AmazonOrderId"]
    print("2) getOrderAddress (restricted data role) on one order")
    ra = safe(f"/orders/v0/orders/{oid}/address")
    print("   address call:", "OK (has ShippingAddress)" if isinstance(ra, dict) and (ra.get("payload") or {}).get("ShippingAddress") else "no address returned")
    print("3) getOrderItems")
    ri = safe(f"/orders/v0/orders/{oid}/orderItems"); print("   items:", len(((ri or {}).get("payload") or {}).get("OrderItems", [])))
else:
    print("no orders in the window to test the address call on")
