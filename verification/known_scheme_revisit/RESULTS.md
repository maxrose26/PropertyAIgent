# Bounded offline increment — results, 30 September 2026

Base reviewed: 826045d0633b8074e8264ddf12dffdeffd60dbc0. CONTRACT.md was written before model.py. This is an offline executable contract, not a production revisit implementation. No app/, scripts/, database model, P0-A owner/admission or deployment file changed. No database connection, portal request, migration, paid evaluation or cron operation was attempted. Existing buyer results and deferred refresh remain unchanged.

## Focused verification

Command from repository root:

```sh
/workspace/scratch/fbbe3b115fa5/ah-test-venv/bin/python -m pytest verification/known_scheme_revisit/test_revisit.py -q
```

Python 3.12.14; pytest 9.1.1. 27 passed; zero failures/errors/skips. Test module blocks socket creation. No broad test suite rerun: production paths were not edited. git diff --check passed. Final exact commit and clean-tree status are reported after commit and re-running the same focused command.

Coverage: completed earlier intake with later document and unchanged summary; absent/misleading validators; same URL changed body and return to earlier bytes; unchanged-body deduplication; Focus original → variation → discharge frontier across JSON checkpoints; issue/publication/observation/stage separation; Hyde address-only and cross-council candidates; no claim transfer even on verified edges; wrong-application document rejection; inaccessible body/304 limits; last-success preservation and capped backoff/Retry-After; crash before checkpoint publication and replay; interrupted next page; early council success/later failure; council and oldest-attempt fairness; body/frontier caps and resumption; unavailable routes; cursor loops; independent unreviewed conflicting proposals.

A JSON round-trip simulates durable checkpoint reload. It does not establish atomic database persistence, fsync, owner recovery, real HTTP cache bypass, PDF parsing, portal relationship recall or live throughput. Fixtures explicitly supply verified citations; actual adapters must establish them. Reference normalisation reuses the unchanged P0-A helper. The model adds no independent process, queue service, lease or admission mechanism.

## Workload evidence

workload.py produces workload.json from six synthetic application identities: three Focus cases, two Stockport Hyde references, and the Tameside site313 negative control (synthetic reference SITE/313, not asserted real portal reference). One previously seen synthetic document body and one empty citation-search page per application: six body revalidations and six relationship page checks. These are fixture assumptions measured through the model, not likely production volumes. Total fixture body bytes144 has no capacity-planning value.

With four logical steps per slice and two per council, first slice leaves eight stage work items deferred. Five slices complete all twelve; zero identical-body versions recreated. No elapsed portal time is estimated. Related Cases tabs, multi-page registers and real PDF sizes are not included in this workload. Production monitored application count, likely document revalidations, relationship volume and deferred backlog remain UNMEASURED; no authorised production metadata source was accessed. No sites-times-buyers extrapolation or cadence approval follows.

## Remaining decisions

No migration needed to run these fixtures. Production integration will need reviewed durable stage/route checkpoints, immutable document versions/observations and relationship provenance. It must use the existing admitted P0-A child and owner reconciliation, atomically saving observation/frontier/cursor progress. P0-A release and verification of its scheduled identity contract remain prerequisites for live execution. This work does not solve or alter those gates.

Next smallest decision: review this contract and choose a bounded persistence/adapter integration design. Confirm database ownership-conditioned transactions and checkpoint representation before migration implementation or any live pilot. Do not commit to weekly/monthly cadence until stored inventory and permitted bounded timing measurements exist. Actual portal behaviour and source-qualified selection remain separate acceptance gates. Statement evidence cannot confirm operative tenure or acquisition availability. No automatic intelligence overwrite, AH import, buyer refresh or paid evaluation is provided.
