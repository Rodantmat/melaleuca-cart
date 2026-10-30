"""carriers.py - which carrier a tracking number belongs to, the public tracking link, and the delivery status (Shippo live tracking API)."""
import json, os, re, time, urllib.request, urllib.error

LINKS = {
    "ups": "https://www.ups.com/track?tracknum={n}",
    "usps": "https://tools.usps.com/go/TrackConfirmAction?tLabels={n}",
    "fedex": "https://www.fedex.com/fedextrack/?trknbr={n}",
    "ontrac": "https://www.ontrac.com/tracking/?number={n}",
    "lasership": "https://www.lasership.com/track/{n}",
    "canada_post": "https://www.canadapost-postescanada.ca/track-reperage/en#/search?searchFor={n}",
    "purolator": "https://www.purolator.com/en/shipping/tracker?pin={n}",
    "dhl_express": "https://www.dhl.com/en/express/tracking.html?AWB={n}",
    "dhl_ecommerce": "https://webtrack.dhlglobalmail.com/?trackingnumber={n}",
}
NAMES = {"ups": "UPS", "usps": "USPS", "fedex": "FedEx", "ontrac": "OnTrac", "lasership": "LaserShip", "canada_post": "Canada Post",
         "purolator": "Purolator", "dhl_express": "DHL", "dhl_ecommerce": "DHL eCommerce", "unknown": "?"}


def detect(n, hint=""):
    """-> carrier key.  `hint` = the link / text the store shows next to the number (wins when it names a carrier)."""
    h = (hint or "").lower()
    for key, words in (("ups", ("ups.com", "ups ")), ("usps", ("usps", "postal")), ("fedex", ("fedex",)), ("ontrac", ("ontrac",)),
                       ("lasership", ("lasership",)), ("canada_post", ("canadapost", "canada post")), ("purolator", ("purolator",)), ("dhl_express", ("dhl",))):
        if any(w in h for w in words): return key
    n = re.sub(r"\s", "", n or "").upper()
    if re.fullmatch(r"1Z[0-9A-Z]{16}", n): return "ups"
    if re.fullmatch(r"(92|93|94|95)\d{18,24}", n) or re.fullmatch(r"[A-Z]{2}\d{9}US", n): return "usps"
    if re.fullmatch(r"[CD]\d{14}", n): return "ontrac"
    if re.fullmatch(r"1LS\d{9,}|LX\d{8,}|LS\d{8,}", n): return "lasership"
    if re.fullmatch(r"\d{12}|\d{15}|96\d{20}", n): return "fedex"
    if re.fullmatch(r"\d{16}", n): return "canada_post"
    return "unknown"


def link(carrier, n):
    t = LINKS.get(carrier)
    if t: return t.format(n=n)
    return "https://www.google.com/search?q=" + n        # unknown carrier: at least a search that usually finds it


SHIPPO_CARRIER = {"ups": "ups", "usps": "usps", "fedex": "fedex", "ontrac": "ontrac", "lasership": "lasership", "canada_post": "canada_post",
                  "purolator": "purolator", "dhl_express": "dhl_express", "dhl_ecommerce": "dhl_ecommerce"}
STATUS_TXT = {"PRE_TRANSIT": "Label created", "TRANSIT": "In transit", "DELIVERED": "Delivered", "RETURNED": "Returned", "FAILURE": "Delivery problem", "UNKNOWN": "No info yet"}


def _get(url, token, tries=3):
    for k in range(tries):
        try:
            rq = urllib.request.Request(url, headers={"Authorization": "ShippoToken " + token, "User-Agent": "status-page"})
            with urllib.request.urlopen(rq, timeout=40) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try: body = json.loads(e.read().decode("utf-8", "replace"))
            except Exception: body = {}
            if e.code in (429, 500, 502, 503) and k < tries - 1:
                time.sleep(3 * (k + 1)); continue
            return e.code, body
        except Exception as e:
            if k == tries - 1: return 0, {"error": str(e)[:100]}
            time.sleep(2)


def lookup(carrier, n, token):
    """-> dict(status, status_text, detail, location, eta, eta_text, delivered_at, last_update)  - empty status when the carrier gives nothing."""
    out = {"status": "UNKNOWN", "status_text": STATUS_TXT["UNKNOWN"], "detail": "", "location": "", "eta": "", "delivered_at": "", "last_update": "", "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    sc = SHIPPO_CARRIER.get(carrier)
    if not sc or not token:
        out["detail"] = "carrier not supported" if not sc else "no Shippo token"
        return out
    code, js = _get("https://api.goshippo.com/tracks/%s/%s" % (sc, n), token)
    if code != 200 or not isinstance(js, dict):
        out["detail"] = ("carrier says: %s" % (js.get("detail") or js.get("error") or js))[:120] if code else "network error"
        return out
    ts = js.get("tracking_status") or {}
    st = (ts.get("status") or "UNKNOWN").upper()
    out["status"] = st
    out["status_text"] = STATUS_TXT.get(st, st.title())
    out["detail"] = (ts.get("status_details") or "")[:160]
    loc = ts.get("location") or {}
    out["location"] = ", ".join(x for x in (loc.get("city"), loc.get("state")) if x)
    out["last_update"] = ts.get("status_date") or ""
    out["eta"] = js.get("eta") or ""
    if st == "DELIVERED": out["delivered_at"] = ts.get("status_date") or ""
    out["service"] = ((js.get("servicelevel") or {}).get("name") or "")
    return out
