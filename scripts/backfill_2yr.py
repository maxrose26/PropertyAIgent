"""One-off: extend every council's backfill window from 1 year back to 2.

Runs app.pipeline.run_weekly --years-back 2 for each council in turn
(sequential, not parallel, to stay polite to any one council's portal).
Safe to re-run - the pipeline upserts by reference, never duplicates.
"""
import os
import subprocess
import sys

COUNCILS = [
    # bury, oldham, tameside, bolton, wigan already fully completed in
    # earlier passes - skipped to avoid redundantly re-scanning 25 months
    # of already-covered ground. stockport excluded entirely - confirmed a
    # total loss (portal-level blocking, needs its own separate retry after
    # a longer cooldown, not bundled into this run). salford/trafford
    # re-included despite partial earlier progress - both got cut short by
    # a duplicate-concurrent-process crash, safe to fully re-run since the
    # pipeline upserts by reference and skips applications that already
    # have scheme_intelligence.
    "salford", "trafford", "rochdale", "manchester",
]

# -u (and PYTHONUNBUFFERED for the child's own subprocess calls, if any)
# forces every print() to flush immediately - without this, the child's
# stdout sits in an internal buffer invisible to anyone tailing the log
# file until it fills or the process exits, making a genuinely-progressing
# run indistinguishable from a truly hung one.
child_env = {**os.environ, "PYTHONUNBUFFERED": "1"}

for code in COUNCILS:
    print(f"\n{'=' * 60}\n{code}\n{'=' * 60}", flush=True)
    result = subprocess.run(
        [sys.executable, "-u", "-m", "app.pipeline.run_weekly", "--council", code, "--years-back", "2"],
        env=child_env,
    )
    if result.returncode != 0:
        print(f"  [{code}] exited with code {result.returncode} - continuing to next council", flush=True)

print("\nDONE - all councils processed")
