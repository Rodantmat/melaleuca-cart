Run journal of the automated jobs (reprice, bb_web, feed, heartbeat).
ops_log.tsv: one line per run (utc, job, status, trigger, run_id, summary). Newest 4000 lines kept.
details/<job>_latest.txt: last 150 log lines of the most recent run of that job.
