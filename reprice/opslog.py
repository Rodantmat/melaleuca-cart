#!/usr/bin/env python3
"""Append one line per automated run to a permanent journal (branch `ops-log`, file ops_log.tsv).

Why: the reprice-state branch is force-pushed on every run, so run.log only ever holds the LAST run.
This journal keeps the history (newest ~4000 lines) so any run can be read, analysed and compared later.

usage: python opslog.py JOB STATUS LOGFILE [KEEP_REGEX ...]
  JOB      reprice | bb_web | feed | heartbeat
  STATUS   success | failure | cancelled   (the step's job.status)
  LOGFILE  text log of the run (may be missing)
  KEEP_REGEX  lines of the log whose text is copied (shortened) into the summary

Also overwrites details/<JOB>_latest.txt with the last 150 lines of the log (for a closer look).
Never fails the workflow: every problem is printed and the exit code stays 0.
"""
import os, re, sys, subprocess, tempfile, datetime as dt

MAX_LINES = 4000
ERR = re.compile(r"Traceback|Error|ERROR|failed|FAIL|HTTP 5\d\d|HTTP 429", re.I)


def sh(args, cwd, check=False):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def summarize(path, keeps):
    try:
        lines = open(path, errors="replace").read().splitlines()
    except Exception:
        return "no log file", []
    errs = [l for l in lines if ERR.search(l) and "DeprecationWarning" not in l and "waiting" not in l]
    parts = []
    for rx in keeps:
        r = re.compile(rx)
        hit = [l.strip() for l in lines if r.search(l)]
        if hit:
            parts.append(hit[-1][:170] + (" (x%d)" % len(hit) if len(hit) > 1 else ""))
    if errs:
        parts.append("errors=%d first: %s" % (len(errs), errs[0].strip()[:140]))
    s = " | ".join(parts) or "(no summary lines)"
    return s.replace("\t", " ").replace("\n", " ")[:900], lines[-150:]


def main():
    if len(sys.argv) < 4:
        print("opslog: usage JOB STATUS LOGFILE [KEEP_REGEX ...]"); return
    job, status, logfile = sys.argv[1:4]
    keeps = sys.argv[4:]
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("opslog: GH_TOKEN/GITHUB_REPOSITORY missing, nothing written"); return
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    trig = os.environ.get("GITHUB_EVENT_NAME", "")
    summary, tail = summarize(logfile, keeps)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = "\t".join([now, job, status, trig, run_id, summary])
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    d = tempfile.mkdtemp()
    sh(["git", "init", "-q"], d)
    sh(["git", "config", "user.name", "ops-bot"], d)
    sh(["git", "config", "user.email", "ops-bot@users.noreply.github.com"], d)
    sh(["git", "remote", "add", "origin", url], d)
    for attempt in range(5):
        have = sh(["git", "fetch", "-q", "--depth", "1", "origin", "ops-log"], d).returncode == 0
        if have:
            sh(["git", "checkout", "-q", "-B", "ops-log", "FETCH_HEAD"], d)
        else:
            sh(["git", "checkout", "-q", "--orphan", "ops-log"], d)
        p = os.path.join(d, "ops_log.tsv")
        old = open(p).read().splitlines() if os.path.exists(p) else \
            ["utc\tjob\tstatus\ttrigger\trun_id\tsummary"]
        new = old[:1] + (old[1:] + [row])[-MAX_LINES:]
        open(p, "w").write("\n".join(new) + "\n")
        os.makedirs(os.path.join(d, "details"), exist_ok=True)
        open(os.path.join(d, "details", job + "_latest.txt"), "w").write(
            "# %s  %s  %s  run %s\n" % (now, job, status, run_id) + "\n".join(tail) + "\n")
        open(os.path.join(d, "README.md"), "w").write(
            "Run journal of the automated jobs (reprice, bb_web, feed, heartbeat).\n"
            "ops_log.tsv: one line per run (utc, job, status, trigger, run_id, summary). Newest %d lines kept.\n"
            "details/<job>_latest.txt: last 150 log lines of the most recent run of that job.\n" % MAX_LINES)
        sh(["git", "add", "-A"], d)
        sh(["git", "commit", "-qm", "ops %s %s %s" % (job, status, now)], d)
        r = sh(["git", "push", "-q", "origin", "ops-log"], d)
        if r.returncode == 0:
            print("opslog: wrote", row[:200]); return
        print("opslog: push retry", attempt + 1, r.stderr.strip()[:120])
    print("opslog: gave up (journal not updated)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("opslog: error", e)
