"""Read-only Amazon login check: one GET, prints OK or the refusal reason. Prints no credentials."""
import os, sys, spapi
c = spapi.load_creds(os.path.dirname(os.path.abspath(__file__)))
try:
    r = spapi.call(c, "GET", "/sellers/v1/marketplaceParticipations", tries=2, quiet=True)
    print("AUTH_PROBE OK marketplaces=%d" % len(r.get("payload", [])))
except spapi.SpError as e:
    print("AUTH_PROBE FAIL", str(e).replace("\n", " ")[:300]); sys.exit(1)
