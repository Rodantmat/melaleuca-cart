"""lab: LIVE lab run (fills the test cart, compares with the sheet, empties it again) of the plans in feed/plans (signs in with account 7 for all, changes nothing)"""
import subprocess, sys, glob, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
which = sys.argv[1:] or [str(i) for i in range(1, 18)]
for n in which:
    f = "feed/plans/cart_plan_%s.tsv" % n
    if not os.path.exists(os.path.join(HERE, f)):
        continue
    print("=" * 30, "plan", n, flush=True)
    subprocess.run([sys.executable, "melaleuca_fill.py", n, "--lab", "--as=7", "--plan=" + f], cwd=HERE)
