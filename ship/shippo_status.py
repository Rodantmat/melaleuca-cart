import os, json, urllib.request
t = os.environ.get("SHIPPO_LIVE_TOKEN", "").strip(); assert t.startswith("shippo_live_")
r = urllib.request.Request("https://api.goshippo.com/carrier_accounts/?results=100&carrier=ups", headers={"Authorization": "ShippoToken " + t})
for a in json.load(urllib.request.urlopen(r, timeout=60)).get("results", []):
    print(a["object_id"][:8], "active=", a.get("active"), "shippo_managed=", a.get("is_shippo_account"), "carrier=", a.get("carrier"), "test=", a.get("test"), "account_id=", str(a.get("account_id"))[:4] + "***")
