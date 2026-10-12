"""check_proxy.py - 10-second test of the proxy from this computer. Run:  python check_proxy.py   (in C:\\AmazonFeed)"""
import os, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
env = {}
for ln in open(os.path.join(HERE, "credentials.env"), encoding="utf-8-sig"):
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, v = ln.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
u = urllib.parse.urlparse(env.get("PROXY_URL", ""))
login = urllib.parse.unquote(u.username or "")
if "__" not in login:
    login += "__cr.us"
pw = urllib.parse.unquote(u.password or "")
print("proxy host:", u.hostname, "| user:", login, "| password length:", len(pw), "| port in file:", u.port)


def test(port, url):
    px = "http://%s:%s@%s:%s" % (urllib.parse.quote(login, safe=""), urllib.parse.quote(pw, safe=""), u.hostname, port)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": px, "https": px}))
    t = time.time()
    try:
        r = op.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25)
        body = r.read(200).decode("utf-8", "replace").strip().replace("\n", " ")
        return "OK %s (%.1fs) %s" % (r.status, time.time() - t, body[:60])
    except Exception as e:
        return "FAILED (%.1fs) %s" % (time.time() - t, str(e)[:120])


import json
LOGIN_BASE = login.split("__")[0]


def geo_test(label, geo, port=10001):
    px = "http://%s:%s@%s:%s" % (urllib.parse.quote(LOGIN_BASE + "__" + geo, safe=""), urllib.parse.quote(pw, safe=""), u.hostname, port)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": px, "https": px}))
    t = time.time()
    try:
        r = op.open(urllib.request.Request("https://ipinfo.io/json", headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
        d = json.loads(r.read().decode())
        return "OK  %s  %s, %s, %s  (%.1fs)" % (d.get("ip"), d.get("city"), d.get("region"), d.get("country"), time.time() - t)
    except Exception as e:
        return "FAILED (%.1fs) %s" % (time.time() - t, str(e)[:100])


print("\nLocation test (each line should show the city asked for):")
for label, geo in (("blue / S. California", "cr.us;city.losangeles,sandiego,longbeach,anaheim,irvine,santaana,riverside"),
                   ("blue / wider S. Calif.", "cr.us;city.losangeles,burbank,glendale,pasadena,torrance,pomona,fullerton,oceanside,escondido,sanbernardino,corona,ontario,fontana,ventura,oxnard,carlsbad,murrieta,temecula"),
                   ("orange / Vancouver", "cr.ca;city.vancouver"), ("yellow / Toronto", "cr.ca;city.toronto"), ("Canada only", "cr.ca")):
    print("%-22s %s" % (label, geo_test(label, geo)))
input("\nPress Enter to close")
