#!/usr/bin/env python3
"""
fba_complete.py - Stage 2 of the Toronto / Vancouver shipment pipeline.  Runs only after you answered YES in the workbook.

  python fba_complete.py complete  send_stage1.json  <folder of the workbook>
  python fba_complete.py cancel    send_stage1.json

What `complete` does, in this order (every step is saved in the stage-1 json, so a stop can be resumed by running it again):
   1  Shippo: re-reads the quoted rate; a changed price is only reported at the end (nothing stops)
   2  Amazon: confirms the placement option  -> FBA shipment ids
   3  Amazon: re-reads every shipment; if ANY address other than the quoted one shows up ("to avoid disruption, send UPS shipment to...")
      it STOPS here, before a single label is bought, and shows both addresses
   4  Amazon: UPS (own carrier, small parcel) transportation option confirmed
   5  Shippo: buys the UPS Canada labels (PDF 4x6) + commercial invoice
   6  Amazon: box ids <- tracking numbers; 4x6 thermal box labels downloaded
   7  paper: CUSMA (importer = the receiving warehouse), invoice, FDA exemption copy, everything into the monthly folder
   8  e-mail: Jessica + UPS International Documents  (fba_mail.py; mode off / eml / send)
"""
import datetime, io, json, os, sys, time, urllib.parse, urllib.request
import sd_tools as S
import fba_ship as F
import fba_docs as D

NAMES = {"fba": "FBALabels", "ups": "UPSLabels", "inv": "CommercialInvoice", "cusma": "CUSMA", "fda": "FDAExemption"}
UPS_SOLUTION = ("UPSN", "GROUND_SMALL_PARCEL", "USE_YOUR_OWN_CARRIER")


class Stop(RuntimeError):
    """a deliberate stop: nothing wrong with the code, a human has to look"""


# ---------------------------------------------------------------- small helpers
def save(st, path): json.dump(st, open(path, "w"), indent=1)


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": S.UA})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()


def merge_pdfs(blobs, out):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for b in blobs:
        for p in PdfReader(io.BytesIO(b) if isinstance(b, (bytes, bytearray)) else b).pages: w.add_page(p)
    with open(out, "wb") as f: w.write(f)


def addr_key(a):
    a = a or {}
    g = lambda *ks: next((str(a[k]).strip().upper() for k in ks if a.get(k)), "")
    return (g("addressLine1", "AddressLine1", "line1"), g("city", "City"), g("stateOrProvinceCode", "StateOrProvinceCode", "state"),
            g("postalCode", "PostalCode", "zip")[:5])


def all_addresses(obj, path=""):
    """every dict that looks like an address anywhere inside an Amazon answer: [(json path, address dict)]"""
    found = []
    if isinstance(obj, dict):
        if (("addressLine1" in obj or "AddressLine1" in obj) and ("postalCode" in obj or "PostalCode" in obj)):
            found.append((path, obj))
        for k, v in obj.items(): found += all_addresses(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj): found += all_addresses(v, "%s[%d]" % (path, i))
    return found


def check_addresses(c, plan_id, legs, say):
    """re-read every shipment from Amazon.  Returns the list of differences (empty = all good)."""
    diffs = []
    for l in legs:
        sh = S._api(c, "GET", S.INB + "/inboundPlans/%s/shipments/%s" % (plan_id, l["shipmentId"]))
        l["amazonShipment"] = {k: sh.get(k) for k in ("status", "shipmentConfirmationId", "name", "selectedTransportationOptionId") if k in sh}
        if sh.get("shipmentConfirmationId"): l["fbaId"] = sh["shipmentConfirmationId"]
        want = addr_key(l["address"])
        for path, a in all_addresses(sh):
            if "source" in path.lower() or "origin" in path.lower() or "shipFrom" in path: continue     # our own ship-from address
            if addr_key(a) != want:
                diffs.append({"shipment": l.get("fbaId") or l["shipmentId"], "where": path, "quoted": want, "now": addr_key(a), "raw": a})
        wh = (sh.get("destination") or {}).get("warehouseId")
        if wh and wh != l["warehouse"]:
            diffs.append({"shipment": l.get("fbaId") or l["shipmentId"], "where": "/destination/warehouseId", "quoted": l["warehouse"], "now": wh})
    return diffs


def alt_stop(diffs):
    lines = ["AMAZON SHOWS A DIFFERENT ADDRESS - nothing was bought at Shippo (the Amazon placement may already be confirmed). Please look at it:"]
    for d in diffs: lines.append("  %s %s\n     quoted for UPS : %s\n     Amazon now says: %s" % (d["shipment"], d["where"], d["quoted"], d["now"]))
    lines.append("If the new address is the right one, tell me and I will re-quote Shippo to it; otherwise cancel in Seller Central.")
    return Stop("\n".join(lines))


# ---------------------------------------------------------------- Amazon steps
def confirm_placement(c, st, say):
    S._wait(c, S._api(c, "POST", S.INB + "/inboundPlans/%s/placementOptions/%s/confirmation" % (st["planId"], st["placementOptionId"])), "placement confirmation", say)


def confirm_transport(c, st, say):
    start = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() + 3 * 86400))
    cfg = [{"shipmentId": l["shipmentId"], "readyToShipWindow": {"start": start}} for l in st["legs"]]
    S._wait(c, S._api(c, "POST", S.INB + "/inboundPlans/%s/transportationOptions" % st["planId"],
                      {"placementOptionId": st["placementOptionId"], "shipmentTransportationConfigurations": cfg}), "transportation options", say)
    sel = []
    ff = S.ship_from(st["origin"])
    contact = {"name": "Rodolfo Antunes", "phoneNumber": ff["phoneNumber"], "email": "flippingmagic.sales@gmail.com"}
    for l in st["legs"]:
        opts = S._paged(c, S.INB + "/inboundPlans/%s/transportationOptions" % st["planId"], "transportationOptions",
                        {"placementOptionId": st["placementOptionId"], "shipmentId": l["shipmentId"]})
        mine = [o for o in opts if (o.get("carrier") or {}).get("alphaCode") == UPS_SOLUTION[0] and o.get("shippingMode") == UPS_SOLUTION[1]
                and o.get("shippingSolution") == UPS_SOLUTION[2]]
        if not mine: raise Stop("Amazon offers no UPS small-parcel (own carrier) option for %s. Options: %s" % (l["shipmentId"], [(o.get("carrier") or {}).get("alphaCode") for o in opts]))
        sel.append({"shipmentId": l["shipmentId"], "transportationOptionId": mine[0]["transportationOptionId"], "contactInformation": contact})
    S._wait(c, S._api(c, "POST", S.INB + "/inboundPlans/%s/transportationOptions/confirmation" % st["planId"], {"transportationSelections": sel}),
            "transportation confirmation", say)


def send_tracking(c, st, say):
    for l in st["legs"]:
        boxes = S._paged(c, S.INB + "/inboundPlans/%s/shipments/%s/boxes" % (st["planId"], l["shipmentId"]), "boxes")
        ids = [b["boxId"] for b in boxes for _ in range(int(b.get("quantity") or 1))]
        trk = l["tracking"]
        if len(ids) != len(trk):
            raise Stop("%s: Amazon has %d boxes but Shippo made %d labels - tracking NOT sent, please check" % (l.get("fbaId"), len(ids), len(trk)))
        items = [{"boxId": b, "trackingId": t} for b, t in zip(ids, trk)]
        S._wait(c, S._api(c, "PUT", S.INB + "/inboundPlans/%s/shipments/%s/trackingDetails" % (st["planId"], l["shipmentId"]),
                          {"trackingDetails": {"spdTrackingDetail": {"spdTrackingItems": items}}}), "tracking numbers", say)
        l["boxIds"] = ids


def amazon_labels(c, l):
    """4x6 thermal box labels (one per box) for one FBA shipment, as PDF bytes"""
    fid = l["fbaId"]
    ids = l.get("boxIds") or ["%sU%06d" % (fid, i + 1) for i in range(l["boxes"])]
    params = {"PageType": "PackageLabel_Thermal", "LabelType": "UNIQUE", "PackageLabelsToPrint": ids}
    url = S.SP_API + "/fba/inbound/v0/shipments/%s/labels?%s" % (fid, urllib.parse.urlencode(params, doseq=True))
    req = urllib.request.Request(url, headers={"x-amz-access-token": S._token(c), "User-Agent": S.UA})
    j = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
    dl = (j.get("payload") or {}).get("DownloadURL")
    if not dl: raise Stop("Amazon gave no label download for %s: %s" % (fid, json.dumps(j)[:300]))
    data = fetch(dl)
    if data[:4] != b"%PDF":
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(data)); data = z.read(z.namelist()[0])
    return data


# ---------------------------------------------------------------- Shippo steps
def shippo_requote(sp, st):
    notes = []
    for l in st["legs"]:
        r = sp.call("GET", "/rates/" + l["rate_id"])
        amt = float(r["amount"])
        if abs(amt - l["amount"]) > 0.005:
            notes.append("UPS price for %s changed from %.2f to %.2f %s since the quote" % (l["warehouse"], l["amount"], amt, r["currency"]))
            l["amount"] = amt; l["usd"] = round(amt * (st["fx"]["usd_per_cad"] if r["currency"] == "CAD" else 1), 2)
    return notes


def shippo_buy(sp, st, say):
    for l in st["legs"]:
        if l.get("tracking"): continue
        r = sp.call("POST", "/transactions/", {"rate": l["rate_id"], "label_file_type": "PDF_4x6", "async": False})
        tx = r.get("results") if isinstance(r, dict) and "results" in r else [r]
        if len(tx) < l["boxes"]:       # some accounts answer with one master transaction: list the shipment's transactions
            more = sp.call("GET", "/transactions/?rate=%s&results=100" % l["rate_id"]).get("results") or []
            if len(more) >= len(tx): tx = more
        bad = [t for t in tx if t.get("status") != "SUCCESS"]
        if bad: raise Stop("Shippo label purchase problem: %s" % json.dumps([(t.get("status"), t.get("messages")) for t in bad])[:600])
        l["tracking"] = [t["tracking_number"] for t in tx]
        l["labelUrls"] = [t["label_url"] for t in tx]
        l["invoiceUrl"] = next((t.get("commercial_invoice_url") for t in tx if t.get("commercial_invoice_url")), "")
        l["shippoTransactions"] = [t["object_id"] for t in tx]
        say("   Shippo labels bought for %s: %s" % (l["warehouse"], ", ".join(l["tracking"])))
        save_cb = st.get("_save")
        if save_cb: save_cb()


# ---------------------------------------------------------------- paper
def invoice_pdf(st, l, frm, to, today):
    """fallback invoice (UPS style) in case Shippo does not hand one over"""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO(); cv = canvas.Canvas(buf, pagesize=letter); W, H = letter; y = H - 50
    cv.setFont("Helvetica-Bold", 16); cv.drawString(50, y, "COMMERCIAL INVOICE"); y -= 22
    cv.setFont("Helvetica", 9)
    for k, v in (("Date", D.mdy(today)), ("Tracking", ", ".join(l["tracking"])), ("Reason for export", "Sale / merchandise"),
                 ("Country of origin", "US"), ("Incoterm", "DDU")): cv.drawString(50, y, "%s: %s" % (k, v)); y -= 12
    y -= 6
    cv.setFont("Helvetica-Bold", 9); cv.drawString(50, y, "FROM"); cv.drawString(310, y, "SHIP TO / SOLD TO"); y -= 12; cv.setFont("Helvetica", 9)
    left = [frm["company"], frm["name"], frm["street1"] + " " + frm.get("street2", ""), "%s, %s %s" % (frm["city"], frm["state"], frm["zip"]), frm["country"]]
    right = [to["company"], to["street1"], "%s, %s %s" % (to["city"], to["state"], to["zip"]), to["country"]]
    for i in range(max(len(left), len(right))):
        if i < len(left): cv.drawString(50, y, left[i])
        if i < len(right): cv.drawString(310, y, right[i])
        y -= 12
    y -= 10; cv.setFont("Helvetica-Bold", 8)
    for x, t in ((50, "Units"), (90, "Description"), (390, "HTS"), (440, "Unit USD"), (500, "Total USD")): cv.drawString(x, y, t)
    y -= 12; cv.setFont("Helvetica", 7.5); total = 0
    for cat, q in l["counts"].items():
        desc, tn = F.HTS[cat]; v = F.DECLARED[cat]; total += v * q
        cv.drawString(50, y, "%d EA" % q); cv.drawString(90, y, desc[:105]); cv.drawString(390, y, tn.replace(".", "")); cv.drawString(440, y, "%.2f" % v)
        cv.drawString(500, y, "%.2f" % (v * q)); y -= 11
    y -= 8; cv.setFont("Helvetica-Bold", 9); cv.drawString(440, y, "TOTAL: %.2f USD" % total); y -= 30
    cv.setFont("Helvetica", 8); cv.drawString(50, y, "I declare that the information is true and correct.   Rodolfo Antunes, Flipping Magic LLC   " + D.mdy(today))
    cv.showPage(); cv.save(); return buf.getvalue()


def build_papers(st, folder, today, say):
    """writes the five files, returns {key: path}"""
    tag = D.previous_month_tag(today); o = st["origin"].strip().title()
    out = {k: os.path.join(folder, "%s-%s-%s.pdf" % (tag, o, v)) for k, v in NAMES.items() if k != "fda"}
    out["fda"] = os.path.join(folder, "FDAExemption.pdf")          # same name as in your monthly mails
    frm = F.ship_from_addr(o)
    merge_pdfs([fetch(u) for l in st["legs"] for u in l["labelUrls"]], out["ups"])
    merge_pdfs([st["_amazon_labels"][l["shipmentId"]] for l in st["legs"]], out["fba"])
    inv = []
    for l in st["legs"]:
        data = None
        if l.get("invoiceUrl"):
            try: data = fetch(l["invoiceUrl"])
            except Exception as e: say("   Shippo invoice not downloadable (%s) - using our own invoice" % str(e)[:80])
        inv.append(data or invoice_pdf(st, l, frm, F.to_address({"address": l["address"], "warehouse": l["warehouse"]}), today))
    merge_pdfs(inv, out["inv"])
    cus = []
    for l in st["legs"]:
        a = l["address"]; tmp = os.path.join(folder, "_cusma_%s.pdf" % l["warehouse"])
        addr = "%s, %s, %s %s" % (a.get("addressLine1", ""), a.get("city", "").upper(), a.get("stateOrProvinceCode", ""), a.get("postalCode", ""))
        D.make_cusma(o, "%s - Amazon Services LLC" % l["warehouse"], addr, today, tmp); cus.append(tmp)
    merge_pdfs(cus, out["cusma"])
    for t in cus: os.unlink(t)
    D.copy_fda(out["fda"])
    return out


# ---------------------------------------------------------------- the whole thing
def complete(state_path, workbook_folder, today=None, say=print, mail_mode=None, api=None, sp=None):
    st = json.load(open(state_path)); today = today or datetime.date.today()
    st["_save"] = lambda: save({k: v for k, v in st.items() if not k.startswith("_")}, state_path)
    c = S._credentials(); sp = sp or F.Shippo(); step = st.setdefault("done", {})
    if st.get("test"): raise Stop("this state file comes from a --test run (its plan is already cancelled)")
    if not step.get("placement") and st.get("expires") and st["expires"] < time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()):
        raise Stop("the Amazon placement offer expired (%s). Send to Amazon again to get a fresh one." % st["expires"])
    notes = []
    if not step.get("shippo_checked"):
        notes += shippo_requote(sp, st); step["shippo_checked"] = True; st["_save"]()
    if not step.get("placement"):
        say("Amazon: confirming placement..."); confirm_placement(c, st, say); step["placement"] = True; st["_save"]()
    if not step.get("address_ok"):
        diffs = check_addresses(c, st["planId"], st["legs"], say); st["_save"]()
        if diffs and not st.get("addressApproved"):
            raise alt_stop(diffs)
        step["address_ok"] = True; st["_save"]()
    if not step.get("transport"):
        say("Amazon: confirming UPS as carrier..."); confirm_transport(c, st, say); step["transport"] = True; st["_save"]()
        diffs = check_addresses(c, st["planId"], st["legs"], say)           # the 'send UPS to' address can appear after this step
        if diffs and not st.get("addressApproved"):
            step["address_ok"] = False; st["_save"](); raise alt_stop(diffs)
    if not step.get("labels"):
        say("Shippo: buying UPS labels..."); shippo_buy(sp, st, say); step["labels"] = True; st["_save"]()
    if not step.get("tracking"):
        send_tracking(c, st, say); step["tracking"] = True; st["_save"]()
    st["_amazon_labels"] = {l["shipmentId"]: amazon_labels(c, l) for l in st["legs"]}
    folder = D.monthly_folder(workbook_folder, today)
    files = build_papers(st, folder, today, say)
    hist = os.path.join(F.HERE, "ship_history.json")
    rows = json.load(open(hist)) if os.path.exists(hist) else []
    rows.append({"origin": st["origin"], "date": str(today), "fee": st["feeUSD"], "usd_total": st["upsUSD"], "fba": [l.get("fbaId") for l in st["legs"]]})
    json.dump(rows, open(hist, "w"), indent=1)
    step["papers"] = True; st["files"] = files; st["_save"]()
    result = {"files": files, "tracking": {l["warehouse"]: l["tracking"] for l in st["legs"]}, "fba": [l.get("fbaId") for l in st["legs"]], "notes": notes}
    try:
        import fba_mail
        result["mail"] = fba_mail.send_all(st, files, today, mode=mail_mode, say=say)
    except Exception as e:
        result["mail"] = "NOT SENT: " + str(e)[:300]
    say("\nDONE. Files in " + folder)
    for k, v in files.items(): say("   " + os.path.basename(v))
    for n in notes: say("NOTE: " + n)
    say("mail: " + str(result["mail"]))
    return result


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    try:
        if len(a) == 3 and a[0] == "complete": complete(a[1], a[2])
        elif len(a) == 2 and a[0] == "cancel": F.cancel(a[1])
        else: print(__doc__)
    except Stop as e:
        print("STOPPED: " + str(e)); sys.exit(2)
    except Exception as e:
        print("ERROR: " + str(e)); sys.exit(1)
