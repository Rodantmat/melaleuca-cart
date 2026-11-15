"""Set MFN stock for AlphaDog pilot children through the Feeds API (POST_INVENTORY_AVAILABILITY_DATA). SKUs from the feed only (AlphaDog SKU pattern).
env AMZ_FEED_URL, AMZ_ONLY, AMZ_FIX_LIMIT (0 = all), AMZ_QTY (default 999). Prints feed ids/status only."""
import json, os, re, time, urllib.request
import spapi, amz_validate as V
c = spapi.load_creds(V.HERE); seller = c.get("SELLER_ID") or "A3431QI59MY9RE"; MP = spapi.MARKETPLACE
feed = json.loads(urllib.request.urlopen(os.environ["AMZ_FEED_URL"] + "?x=%d" % os.getpid(), timeout=120).read().decode())
F = [f for f in feed if f["id"] == os.environ["AMZ_ONLY"]][0]
kids = F["children"][: int(os.environ.get("AMZ_FIX_LIMIT", "0")) or None]; qty = int(os.environ.get("AMZ_QTY", "999")); lat = V.LEAD[F["prod"]]
msgs = []
for i, k in enumerate(kids, 1):
    assert re.match(r"^[A-Z]-[A-Z]{2}-\d-[A-Z]{2}(-\w+)?$", k["sku"]), k["sku"]
    msgs.append("<Message><MessageID>%d</MessageID><OperationType>Update</OperationType><Inventory><SKU>%s</SKU><Quantity>%d</Quantity><FulfillmentLatency>%d</FulfillmentLatency></Inventory></Message>" % (i, k["sku"], qty, lat))
xml = '<?xml version="1.0" encoding="UTF-8"?><AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="amzn-envelope.xsd"><Header><DocumentVersion>1.01</DocumentVersion><MerchantIdentifier>%s</MerchantIdentifier></Header><MessageType>Inventory</MessageType>%s</AmazonEnvelope>' % (seller, "".join(msgs))
d = spapi.call(c, "POST", "/feeds/2021-06-30/documents", body={"contentType": "text/xml; charset=UTF-8"})
req = urllib.request.Request(d["url"], data=xml.encode(), method="PUT", headers={"Content-Type": "text/xml; charset=UTF-8"}); urllib.request.urlopen(req, timeout=120).read()
f = spapi.call(c, "POST", "/feeds/2021-06-30/feeds", body={"feedType": "POST_INVENTORY_AVAILABILITY_DATA", "marketplaceIds": [MP], "inputFeedDocumentId": d["feedDocumentId"]})
fid = f["feedId"]; print("feed", fid, "skus", len(kids))
for _ in range(40):
    s = spapi.call(c, "GET", "/feeds/2021-06-30/feeds/%s" % fid)
    if s.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"): break
    time.sleep(15)
print("status", s.get("processingStatus"))
if s.get("resultFeedDocumentId"):
    r = spapi.call(c, "GET", "/feeds/2021-06-30/documents/%s" % s["resultFeedDocumentId"])
    t = urllib.request.urlopen(r["url"], timeout=60).read().decode("utf-8", "replace")
    print("report:", re.sub(r"\s+", " ", t)[:1500])
