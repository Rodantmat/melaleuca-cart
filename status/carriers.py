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


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _utc(s):
    """'2026-10-31T18:00:00-07:00' -> '2026-10-31T01:00:00Z' (all times on the pages are stored in UTC and shown in the time zone of the page)"""
    import datetime as dt
    try:
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None: return s
        return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return s


def _empty(detail=""):
    return {"status": "UNKNOWN", "status_text": STATUS_TXT["UNKNOWN"], "detail": detail, "location": "", "eta": "", "delivered_at": "", "last_update": "",
            "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def ontrac(n):
    """OnTrac's own tracking service (the one their web page calls) - no carrier account needed"""
    out = _empty()
    try:
        rq = urllib.request.Request("https://webtrack.ontrac.com/PackageServices/tracking/" + n,
                                    headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://www.ontrac.com", "Referer": "https://www.ontrac.com/"})
        with urllib.request.urlopen(rq, timeout=40) as r:
            js = json.loads(r.read().decode("utf-8", "replace"))
        pk = (js.get("Packages") or [None])[0]
        if not pk: out["detail"] = "OnTrac has no data for this number yet"; return out
    except Exception as e:
        out["detail"] = "OnTrac lookup failed: %s" % str(e)[:80]; return out
    evs = [e for e in (pk.get("Events") or []) if isinstance(e, dict)]
    evs.sort(key=lambda e: str(e.get("UtcEventDateTime") or ""))
    last = evs[-1] if evs else {}
    desc = ""
    for k in ("EventDescription", "Description", "StatusDescription", "Status", "EventStatus", "Event", "Message"):
        if isinstance(last.get(k), str) and last.get(k).strip(): desc = last[k].strip(); break
    if not desc:
        desc = " ".join(str(v) for v in last.values() if isinstance(v, str) and 3 < len(v) < 80 and not re.search(r"\d{4}-\d\d", v))[:100]
    city = last.get("City") or last.get("EventCity") or ""; st = last.get("State") or last.get("EventState") or ""
    low = desc.lower()
    deliv = pk.get("UtcDeliveryDateTime") or ""
    if deliv or re.search(r"\bdelivered\b", low): status = "DELIVERED"
    elif not evs or re.search(r"label|order placed|information|created|pre-?ship", low): status = "PRE_TRANSIT"
    else: status = "TRANSIT"
    out.update(status=status, status_text=("Out for delivery" if re.search(r"out for delivery", low) and status == "TRANSIT" else STATUS_TXT[status]),
               detail=desc[:160], location=", ".join(x for x in (str(city).title(), str(st)) if x), last_update=_utc(str(last.get("UtcEventDateTime") or "")))
    eta = pk.get("UtcExpectedDeliveryDateTime") or ""
    out["eta"] = _utc(eta) if eta else (pk.get("ExpectedDeliveryDate") or "")
    if status == "DELIVERED": out["delivered_at"] = _utc(deliv) if deliv else out["last_update"]
    out["service"] = "OnTrac"
    return out


_PW = {}
import threading
_PWLOCK = threading.Lock()


def _browser():
    """a text-only browser for the carriers that have no open data service; installed on first use (the cloud runner has none by default)"""
    if "b" in _PW: return _PW["b"]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "playwright"], check=False)
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=False)
        from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=UA, locale="en-US")
    ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
    _PW.update(p=p, b=b, ctx=ctx)
    return b


def web_status(carrier, n):
    """last resort for carriers Shippo cannot read without an own carrier account (FedEx, USPS ...): opens the public tracking page (text only) and reads the words.
    Less exact than an API: the detail line says so."""
    out = _empty("read from the carrier website")
    try:
        _PWLOCK.acquire()
        _browser()
        pg = _PW["ctx"].new_page()
        pg.goto(link(carrier, n), wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(9000)
        txt = re.sub(r"\s+", " ", pg.inner_text("body"))
        pg.close()
    except Exception as e:
        out["detail"] = "carrier website not readable: %s" % str(e)[:70]
        return out
    finally:
        try: _PWLOCK.release()
        except RuntimeError: pass
    low = txt.lower()
    if re.search(r"(not found|cannot find|can't find|no record|unable to find|not available yet|no results)", low[:6000]) and n.lower() not in low[:3000]:
        out["detail"] = "carrier does not know this number yet"; return out
    m = re.search(r"(delivered[^.]{0,80}|out for delivery[^.]{0,60}|in transit[^.]{0,60}|on its way[^.]{0,60}|label created[^.]{0,60}|shipping label created[^.]{0,40}|pre-shipment[^.]{0,40}|departed[^.]{0,60}|arrived at[^.]{0,60})", low)
    if m:
        t = m.group(1)
        st = "DELIVERED" if t.startswith("delivered") else "PRE_TRANSIT" if re.match(r"(label|shipping label|pre-ship)", t) else "TRANSIT"
        out.update(status=st, status_text=("Out for delivery" if t.startswith("out for") else STATUS_TXT[st]), detail="from carrier website: " + t[:100])
    e = re.search(r"(?:expected|estimated|scheduled|arriving|deliver(?:y)? by|delivery date)[^0-9a-z]{0,12}(?:(?:mon|tue|wed|thu|fri|sat|sun)\w*,?\s+)?([a-z]{3,9}\.? \d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)", low)
    if e and out["status"] != "DELIVERED":
        import datetime as dt
        raw = e.group(1).replace(".", "")
        for fm in ("%B %d", "%b %d", "%m/%d/%Y", "%m/%d/%y", "%m/%d"):
            try:
                d = dt.datetime.strptime(raw.title(), fm)
                y = dt.date.today().year if "%Y" not in fm and "%y" not in fm else d.year
                out["eta"] = "%04d-%02d-%02d" % (y, d.month, d.day); break
            except ValueError:
                continue
    return out


def lookup(carrier, n, token):
    """-> dict(status, status_text, detail, location, eta, eta_text, delivered_at, last_update)  - empty status when the carrier gives nothing."""
    out = {"status": "UNKNOWN", "status_text": STATUS_TXT["UNKNOWN"], "detail": "", "location": "", "eta": "", "delivered_at": "", "last_update": "", "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if carrier == "ontrac":                     # Shippo cannot read OnTrac without an own account: OnTrac's own service is used
        r = ontrac(n)
        if r["status"] != "UNKNOWN" or "failed" not in r["detail"]: return r
    sc = SHIPPO_CARRIER.get(carrier)
    if not sc or not token:
        out["detail"] = "carrier not supported" if not sc else "no Shippo token"
        if carrier != "unknown":
            w = web_status(carrier, n)
            if w["status"] != "UNKNOWN": return w
        return out
    code, js = _get("https://api.goshippo.com/tracks/%s/%s" % (sc, n), token)
    if code != 200 or not isinstance(js, dict):
        out["detail"] = ("carrier says: %s" % (js.get("detail") or js.get("error") or js))[:120] if code else "network error"
        if carrier in ("fedex", "usps", "canada_post", "purolator", "lasership", "dhl_express", "dhl_ecommerce") and code in (400, 401, 402, 403, 404, 422):
            w = web_status(carrier, n)                  # Shippo has no access: read the public tracking page instead
            if w["status"] != "UNKNOWN": return w
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
