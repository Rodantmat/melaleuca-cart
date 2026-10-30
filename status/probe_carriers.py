"""LAB probe: the web fallback on FedEx / USPS public pages with made-up numbers (they must come back as 'does not know this number', never crash)."""
import os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import carriers as C
for car, n in (("usps", "9400111899223197428490"), ("fedex", "794644790138"), ("ups", "1Z999AA10123456784")):
    try:
        r = C.web_status(car, n) if car != "ups" else C.web_status("ups", n)
        print(car, "->", r["status"], "|", r["detail"], "| eta:", r["eta"])
    except Exception as e:
        print(car, "CRASH", repr(e)[:200])
