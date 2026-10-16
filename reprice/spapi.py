"""Small, careful SP-API client (standard library only). Credentials: CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN (+ SELLER_ID) from credentials.env or the environment."""
import gzip, json, os, sys, time, urllib.error, urllib.parse, urllib.request

API = "https://sellingpartnerapi-na.amazon.com"
LWA = "https://api.amazon.com/auth/o2/token"
MARKETPLACE = "ATVPDKIKX0DER"
UA = "FlippingMagicPlanner/1.0 (Language=Python)"


class SpError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


def read_env(path):
    d = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8-sig"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                d[k.strip().upper()] = v.strip().strip('"').strip("'")
    return d


def load_creds(here):
    d = read_env(os.path.join(here, "credentials.env"))
    for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN", "SELLER_ID"):
        if os.environ.get(k) and not d.get(k):
            d[k] = os.environ[k]
    miss = [k for k in ("CLIENT_ID", "CLIENT_SECRET", "REFRESH_TOKEN") if not d.get(k)]
    if miss:
        raise SpError("missing credentials: " + ", ".join(miss))
    return d


_tok = {"v": None, "exp": 0}


def token(c, force=False):
    if not force and _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    data = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": c["REFRESH_TOKEN"], "client_id": c["CLIENT_ID"], "client_secret": c["CLIENT_SECRET"]}).encode()
    req = urllib.request.Request(LWA, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SpError("login refused: HTTP %s" % e.code, e.code)
    _tok["v"], _tok["exp"] = j["access_token"], time.time() + int(j.get("expires_in", 3600))
    return _tok["v"]


def call(c, method, path, params=None, body=None, tries=7, quiet=False):
    """A POST/PATCH is repeated only on 429/5xx answers where Amazon did not process it (never on a timeout after sending)."""
    url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    for k in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers={"x-amz-access-token": token(c), "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and k < tries - 1:
                w = min(120, 4 * (2 ** k))
                if not quiet:
                    print("  (Amazon %s on %s - waiting %ss)" % (e.code, path[:50], w)); sys.stdout.flush()
                time.sleep(w)
                continue
            if e.code in (401, 403) and "expired" in msg.lower() and k < tries - 1:
                token(c, True)
                continue
            raise SpError("HTTP %s %s %s: %s" % (e.code, method, path[:60], msg[:400]), e.code)
        except (urllib.error.URLError, TimeoutError) as e:
            if method in ("GET",) and k < tries - 1:
                time.sleep(5)
                continue
            raise SpError("network error on %s %s: %s" % (method, path[:60], e))
    raise SpError("gave up on " + path[:60])


def report(c, rtype, start=None, end=None, options=None, wait_minutes=45):
    """request, wait, download a report -> text. Returns (status, text)"""
    body = {"reportType": rtype, "marketplaceIds": [MARKETPLACE]}
    if start: body["dataStartTime"] = start
    if end: body["dataEndTime"] = end
    if options: body["reportOptions"] = options
    rid = call(c, "POST", "/reports/2021-06-30/reports", body=body)["reportId"]
    t0 = time.time()
    while time.time() - t0 < wait_minutes * 60:
        r = call(c, "GET", "/reports/2021-06-30/reports/" + rid, quiet=True)
        st = r.get("processingStatus")
        if st in ("DONE", "FATAL", "CANCELLED"):
            if st != "DONE" or not r.get("reportDocumentId"):
                return st, ""
            d = call(c, "GET", "/reports/2021-06-30/documents/" + r["reportDocumentId"])
            rq = urllib.request.Request(d["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(rq, timeout=300) as resp:
                blob = resp.read()
            if str(d.get("compressionAlgorithm", "")).upper() == "GZIP":
                blob = gzip.decompress(blob)
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    return "DONE", blob.decode(enc)
                except UnicodeDecodeError:
                    continue
        time.sleep(20)
    return "TIMEOUT", ""
