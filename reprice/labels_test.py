"""Test: can Amazon itself make the product labels (Fulfillment Inbound API 2024-03-20 createMarketplaceItemLabels)?"""
import json, os, sys, urllib.request
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
MK = "ATVPDKIKX0DER"
STATE = os.path.join(HERE, "state"); os.makedirs(STATE, exist_ok=True)
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.append(s); sys.stdout.flush()
def main():
    c = spapi.load_creds(HERE)
    items = [{"msku": "ME1303", "quantity": 3}, {"msku": "E0-FNUP-YHBK", "quantity": 2}, {"msku": "ME0018", "quantity": 1}]
    tests = [("std_letter30", {"labelType": "STANDARD_FORMAT", "pageType": "Letter_30"}),
             ("thermal_50x25", {"labelType": "THERMAL_PRINTING", "width": 50, "height": 25}),
             ("thermal_plain", {"labelType": "THERMAL_PRINTING"})]
    for name, extra in tests:
        body = {"marketplaceId": MK, "mskuQuantities": items}
        body.update(extra)
        try:
            r = spapi.call(c, "POST", "/inbound/fba/2024-03-20/items/labels", body=body, quiet=True, tries=2)
            say(name, "OK", json.dumps(r)[:300])
            for i, d in enumerate(r.get("documentDownloads") or []):
                uri = d.get("uri")
                if uri:
                    data = urllib.request.urlopen(uri, timeout=90).read()
                    fn = os.path.join(STATE, "labels_%s_%d.pdf" % (name, i))
                    open(fn, "wb").write(data); say("  saved", fn, len(data), "bytes")
        except spapi.SpError as e:
            say(name, "ERR", str(e)[:700])
    open(os.path.join(STATE, "labels_test.log"), "w").write("\n".join(LOG))
sys.exit(main() or 0)
