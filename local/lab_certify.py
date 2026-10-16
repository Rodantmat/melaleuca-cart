"""lab: fills the REAL cart of each listed tab with its plan (feed/plans), compares with the sheet, empties the cart again. Never pays.
   python lab_certify.py 6 7 8"""
import subprocess, sys, os, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
PDIR = "feed/plans"
for a in list(sys.argv[1:]):
    if a.startswith("--dir="):
        PDIR = a[6:]
        sys.argv.remove(a)
which = sys.argv[1:] or [str(i) for i in range(1, 18)]
summary = []
for n in which:
    f = "%s/cart_plan_%s.tsv" % (PDIR, n)
    if not os.path.exists(os.path.join(HERE, f)):
        summary.append((n, "NO PLAN"))
        continue
    print("=" * 30, "tab", n, time.strftime("%H:%M:%S"), flush=True)
    p = subprocess.run([sys.executable, "melaleuca_fill.py", n, "--lab", "--nofinal", "--plan=" + f], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1500, text=True, errors="replace")
    out = p.stdout
    print(out, flush=True)
    keep = [ln for ln in out.splitlines() if re.search(r"RESULT|DIFFERENCE|PROBLEM|NOT ON THIS|AUTO-ADJUSTED|SKU CORRECTED|SUBSTITUTED|CHECK:|Traceback|Error|REFUSED|signed in as|lab: emptied|every line|NOT RESOLVED|could not|failed", ln)]
    summary.append((n, "rc=%s" % p.returncode, keep))
print("\n" + "#" * 30, "SUMMARY")
for s in summary:
    print("--- tab", s[0], s[1])
    for ln in (s[2] if len(s) > 2 else []):
        print("    ", ln.strip()[:230])
