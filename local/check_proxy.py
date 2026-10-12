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


for port in (823, 10001, 10007):
    for url in ("https://api.ipify.org", "https://www.melaleuca.com/"):
        print("port %-5s %-28s %s" % (port, url, test(port, url)))
input("\nPress Enter to close")
