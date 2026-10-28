"""offline test of Stage 2 with fake Amazon and Shippo (buys nothing, calls nothing):  python test_complete.py"""
import datetime, io, json, os, shutil, tempfile
import sd_tools as S, fba_complete as C, fba_ship as F, fba_mail as M
from reportlab.pdfgen import canvas

def pdf(txt):
    b = io.BytesIO(); c = canvas.Canvas(b, pagesize=(288, 432)); c.drawString(20, 400, txt); c.showPage(); c.save(); return b.getvalue()

class Fake:
    def __init__(self, alt=False): self.alt = alt; self.calls = []
    def api(self, c, method, path, body=None, params=None):
        self.calls.append((method, path.replace(S.INB, "")))
        if method == "POST" and "operationId" not in path: return {"operationId": "op1"}
        if method == "PUT": return {"operationId": "op1"}
        if "/operations/" in path: return {"operationStatus": "SUCCESS"}
        if path.endswith("/boxes"): return {"boxes": [{"boxId": "FBA1U000001", "quantity": 1}, {"boxId": "FBA1U000002", "quantity": 1}]}
        if "/transportationOptions" in path and method == "GET":
            return {"transportationOptions": [{"carrier": {"alphaCode": "TFIN"}, "shippingMode": "FREIGHT_LTL", "shippingSolution": "USE_YOUR_OWN_CARRIER", "transportationOptionId": "x"},
                    {"carrier": {"alphaCode": "UPSN"}, "shippingMode": "GROUND_SMALL_PARCEL", "shippingSolution": "USE_YOUR_OWN_CARRIER", "transportationOptionId": "to1"}]}
        if "/shipments/" in path and method == "GET":
            d = {"shipmentConfirmationId": "FBA1", "status": "UNCONFIRMED", "destination": {"warehouseId": "BNA6", "address": {"addressLine1": "1 Test Rd", "city": "Lebanon", "stateOrProvinceCode": "TN", "postalCode": "37090"}}}
            if self.alt and any(x[0] == "PUT" or "confirmation" in x[1] for x in self.calls):
                d["carrierDropOff"] = {"address": {"addressLine1": "99 Other St", "city": "Memphis", "stateOrProvinceCode": "TN", "postalCode": "38109"}}
            return d
        return {}

class FakeShippo:
    def call(self, m, p, b=None):
        if p.startswith("/rates/"): return {"amount": "420.00", "currency": "CAD"}
        if p.startswith("/transactions") and m == "POST":
            return {"results": [{"status": "SUCCESS", "tracking_number": "1Z000%d" % i, "label_url": "u%d" % i, "object_id": "t%d" % i, "commercial_invoice_url": "inv"} for i in (1, 2)]}
        raise RuntimeError(p)

def run(alt):
    tmp = tempfile.mkdtemp(); wb = os.path.join(tmp, "2026-10"); os.makedirs(wb)
    st = {"origin": "Toronto", "name": "t", "planId": "p1", "placementOptionId": "po1", "feeUSD": 209.03, "upsUSD": 300.0, "fx": {"usd_per_cad": 0.71}, "expires": "2099-01-01T00:00:00Z",
          "legs": [{"shipmentId": "sh1", "warehouse": "BNA6", "address": {"addressLine1": "1 Test Rd", "city": "Lebanon", "stateOrProvinceCode": "TN", "postalCode": "37090"}, "boxes": 2, "lb": 40, "units": 100,
                    "counts": {"Cleaner": 60, "Bar": 40}, "rate_id": "r1", "amount": 420.0, "currency": "CAD", "usd": 298.2}]}
    sp = os.path.join(wb, "send_stage1.json"); json.dump(st, open(sp, "w"))
    f = Fake(alt)
    S._api = f.api; S._credentials = lambda: {"CLIENT_ID": "a"}; S._token = lambda c: "t"
    C.fetch = lambda u, timeout=0: pdf("pdf " + u) if u != "inv" else pdf("shippo invoice")
    C.amazon_labels = lambda c, l: pdf("amazon box labels " + l["fbaId"])
    F.Shippo = FakeShippo; S.ship_from = lambda o: {"addressLine1": "500 Murray Ross Parkway", "addressLine2": "#207", "city": "North York", "stateOrProvinceCode": "ON", "postalCode": "M3J2Z3", "countryCode": "CA", "phoneNumber": "9544590398"}
    out = []
    try:
        r = C.complete(sp, wb, today=datetime.date(2026, 10, 28), say=out.append, mail_mode="eml", sp=FakeShippo())
        return tmp, wb, r, out, None
    except C.Stop as e:
        return tmp, wb, None, out, str(e)

tmp, wb, r, out, err = run(False)
assert err is None, err
folder = os.path.join(tmp, "2026-09"); print(sorted(os.listdir(folder)))
assert {"2026-09-Toronto-FBALabels.pdf", "2026-09-Toronto-UPSLabels.pdf", "2026-09-Toronto-CommercialInvoice.pdf", "2026-09-Toronto-CUSMA.pdf", "FDAExemption.pdf", "_Jessica.eml", "_UPS_documents.eml"} <= set(os.listdir(folder))
print(r["mail"]); print(open(os.path.join(folder, "_Jessica.eml"), errors="ignore").read()[:300])
print("note: price change reported:", r["notes"])
tmp2, wb2, r2, out2, err2 = run(True)
assert err2 and "DIFFERENT ADDRESS" in err2, err2
print("\nALT-ADDRESS CASE ->", err2.splitlines()[:5])
shutil.rmtree(tmp); shutil.rmtree(tmp2); print("\nALL OK")
