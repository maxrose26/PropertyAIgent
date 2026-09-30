# Bounded AH buyer walkthrough

Latest: `mandate-review-evidence/` uses the supported evaluate_buyer_fit entry point and database-built B2 context for matching and packets. Earlier directories preserve previous runs. See docs/AH_RETIREMENT_PREFERENCE_REVIEW.md for the full signal audit and unimplemented persistence contract. The retained50 threshold is an illustrative fixture only.

## Current balanced-rule increment

`balanced-rule-evidence/` records the current runner: four source/scope cohort records plus the existing legacy negative control, three emitted CSVs, and explicit ACCEPT/EXCLUDE/UNSPECIFIED local retirement outcomes. Focused checks:112 tests+10 subtests passed; seven existing matching tests passed (18 intentionally deselected); no failures/errors/skips. The previous failure is resolved with preservation and non-qualification assertions plus a narrowly required presentation correction. See the newest section of the acceptance record for exact test modules, scope and release gates. Runtime hashes bind the captured evidence to the delivered code.

The `evidence/` directory and result counts below are retained historical evidence for182bce8, not current failures.

## Previous increment and runner instructions

Run only in an authorised offline, non-production checkout with the dedicated test dependencies:

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=. /path/to/test-venv/bin/python verification/ah_workflow/run.py
```

The runner creates a new temporary SQLite file; it never accepts a database URL. Repository environment files are rejected, dotenv is disabled and outbound socket access is denied. Supplied excerpts and application scaffolding are test fixtures, not production imports or new source retrieval. Existing schema and import/review paths run only in that disposable file. No paid evaluation or external operation occurs.

`evidence/selected-records.csv` and `selected-50plus.csv` are actual Streamlit download-button media bytes, captured via AppTest's real MemoryMediaFileStorage and parsed. The only patched dependency captures that media store; application/business functions and database guards are not substituted. Browser HTTP download delivery is outside this evidence. Four actual detail pages, Explore filtering, matching, feed-fact attachment and in-memory packet assembly are checked. Feed discovery/ranking and persisted evaluations are outside it.

`runtime.json` records the pre-commit worktree and hashes of executed runtime files; the delivery commit contains those same files. The final delivery reports exact commit/clean-tree checks. `checksums.json` covers the retained evidence (no disposable database included). Versions: Python3.12.14; pytest9.1.1; SQLAlchemy2.1.1; pandas3.0.6; Streamlit1.64.0.

Focused command:

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONPATH=. /path/to/test-venv/bin/python -m pytest -q tests/test_ah_workflow_presentation.py tests/test_residential_mix.py tests/test_ownership_control_reporting.py verification/test_ah_count_threshold.py
```

Candidate:95 passed,1 failed,10 subtests passed, no skips/errors. Baseline35d439f on the same existing three modules:91 passed, same1 failed,10 subtests passed. The baseline lacks the four new regression tests, all of which pass on the candidate. Shared failing test: `test_residential_mix_never_mixes_affordable_and_total_across_versions` expects unqualified legacy count30 in a source-qualified headline; both returnNone. No baseline failure is silently excluded. The walkthrough itself passes. No broad suite/native PostgreSQL rerun or release acceptance is claimed.

See `docs/AH_SAME_RECORD_REVIEW_20260929.md` for the observed/expected matrix, party-role integration limits, source/legal distinctions and separate release gates. No synthetic whole-scheme zero is promoted to real-source acceptance.
