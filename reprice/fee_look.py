"""READ-ONLY: Amazon FBA fee estimate for ASIN:price pairs. Prints FEE <asin> <price> <total fees>."""
import os, sys, json, spapi
HERE = os.path.dirname(os.path.abspath(__file__))
c = spapi.load_creds(HERE); MP = spapi.MARKETPLACE
for pair in sys.argv[1].replace(" ", "").split(","):
    a, p = pair.split(":"); p = float(p)
    try:
        r = spapi.call(c, "POST", "/products/fees/v0/items/%s/feesEstimate" % a, body={"FeesEstimateRequest": {"MarketplaceId": MP, "IsAmazonFulfilled": True, "Identifier": a, "PriceToEstimateFees": {"ListingPrice": {"CurrencyCode": "USD", "Amount": p}}}}, tries=5, quiet=True)
        fr = (r.get("payload") or r).get("FeesEstimateResult") or {}
        print("FEE", a, p, (fr.get("FeesEstimate") or {}).get("TotalFeesEstimate", {}).get("Amount"), json.dumps(fr.get("Error"))[:100] if fr.get("Error") else "")
    except spapi.SpError as e:
        print("FEE", a, p, "ERR", str(e)[:100])
