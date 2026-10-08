> Historical checkpoint at3607b245. See B1-INTEGRITY-CONTRACT.md and FINAL-OFFLINE-ACCEPTANCE.md for the separately authorised successor review.

# TO REVIEW — STAGE 2.6B B0+B1 OFFLINE IMPLEMENTATION COMPLETION

**Outcome: OFFLINE CANDIDATE PRESERVED; ACCEPTANCE BLOCKED. Not implementation completion or release approval.**

## Decision required

The required frozen v6/v7 dependency checks pin `app/reporting/scheme_reconciliation.py` byte-for-byte. B1's source/metric eligibility guard changes approved and active reconciliation in that module. Matching policy v8 and all golden benchmark expectations remain unchanged, and qualified-input invariance passes, but the three source-integrity assertions fail.

Independent review rejects silently retargeting the assertions to historical Git blobs or updating their pins. Moving the helper outside frozen CountAssessment preserved that module's integrity; avoiding every reconciliation edit would require a materially different adapter/proxy arrangement across scoped callers, with raw-ORM/source identity risks. That is not a proportionate routine correction to conceal this contract conflict.

Request **bounded REVIEW authority to reconcile the running dependency source-pin contract with the already-authorised raw-evidence eligibility change**, while preserving frozen matcher/golden expectations and strengthening the separate qualified-input versus corrected-evidence differential. If that is not approved, this candidate remains blocked. No next-slice, merge or deployment authority is requested.

## Candidate and scope

Local branch `feat/stage26b-b0-b1`, direct base `8ec17e22e476209a88a1c162fb4b41a896a1af9e`. Exact commit/tree and complete changed-path list are returned with the delivery. Documentation and machine-readable evidence are retained in this directory.

B0 adds 25-case/32-subject qualified context, nine source-linked case wrappers and layer tracing. Original audit-pack SHA was verified. Historical extraction origins remain unresolved. B1 excludes ineligible residential quantities in shared approved/active paths and legacy adapters without creating replacement totals, persistence or a matching engine. CountAssessment and policy/identity algorithms remain unchanged.

All six negative acceptance cases are contained under synthetic approved/pending variants. Bamford67, Failsworth68 and Southlink147 remain unchanged; scoped retirement60, legitimate child counts, conversions and mixed-use housing survive. Existing approximate100/101/102, hard bounds, ranges, non-overlap and variation tests pass. Unknown remains unknown, never zero. World of Pets is not repaired to76.

## Differential and commercial consequences

`evidence/qualified-differential.json` records previous/corrected qualified inputs, four buyer assessments, explanations and family effects for the nine wrappers. `evidence/universe-differential.json` exercises actual SQLite detectors/feed/families and full fingerprint construction, adding a parent/legitimate-child/ancillary-child control. It is not a production replay: geography, approval state and dates are deliberately synthetic.

Six shared synthetic universe subjects have changed fingerprints and unknown count; Strawberry's plot key is removed and an unknown unphased key is added by the existing material-parcel rule. Housing Association family order is unchanged; National Housebuilder, Nesten and Strategic Land order change. National Housebuilder's synthetic family900 representative changes from ancillary phase2 to the unphased subject; all buyers see Strawberry's key replacement. Exact membership, representative and order lists are retained.

Buyer classifications can legitimately change: Nesten World of Pets/Cedar Strong → Insufficient and Walthew Possible → Insufficient; National Housebuilder Woodford and synthetic bridge phase Strong → Insufficient. Stand Golf Not Suitable → Insufficient for three buyers because existing coherent-source selection no longer treats the unsupported whole-count source as a qualified source for its other matching inputs. This consequence is explicit, requires REVIEW acceptance and is not claimed to improve acquisition quality. AH source headline/tenure adapters remain identical; no AH repair occurs.

No algorithmic fingerprint change, production monitoring event, identity migration or rebaseline is performed. Future saved/monitoring identity effects require a transition decision before release. Request-local query counts are unchanged: universe15, family-input load13, each buyer52 except Nesten53 in the synthetic fixture.

## Exact selected test results

All final selections have zero errors, zero skips and zero deselections. Counts overlap; do not sum them as unique tests.

| Selection | Passed | Failed |
|---|---:|---:|
| B0/B1 focused fixtures/differentials |50|0|
| Stage2/Spec028/v8 selected regression |1752|3|
| Stage1 security |211|0|
| Actual rendered journeys including B1 dashboard/profile/related/CSV |24|0|
| Relevant reconciliation/status/material-change/AH/extraction/mix |211|0|
| Existing mock refresh compatibility |163|0|
| AH web-only acceptance |257 +10 passing subtests|0|

AH rendered CSV walkthrough also passed. Exact suite selections are in `verification/stage2/check.sh`, `verification/web_ah/check.sh` and `verification/stage26b/check.sh`. All used `/workspace/scratch/bd6a3a220c00/stage2-venv/bin/python`, cleared environments, synthetic SQLite and existing offline syscall guards. Mock refresh tests needed the existing synthetic positive-command fixture; no real model call occurred. Stage1 security ran separately without that adapter.

The three remaining failures are:

- `test_v7c_frozen_v6_oracle.py::test_the_supporting_modules_behind_the_imported_names_are_unchanged_since_v6`
- `test_v8_frozen_v7_oracle.py::test_pinned_definitions_unchanged_and_function_reads_only_existing_facts_fields`
- `test_v8_frozen_v7_oracle.py::test_the_residual_work_did_not_touch_the_pinned_supporting_modules`

No failure was deleted, skipped, xfailed, retargeted or hidden. Initial implementation/harness failures were corrected and rerun; only these three integrity gates remain. Hosted CI was not run; its offline job is extended for the new tests and exact Git baseline fetch.

## Remaining boundaries

No schema/migration/backfill is required or performed. No actual production-impact claim can be made from the limited retained proposal inputs. Historical origin and World of Pets eligible replacement remain unresolved; five audit count cases remain unresolved rather than fabricated truth. B2 freshness is the recommended next separately approved slice after this gate; no B2–B5 work began.

No production access, writes, credentials, role/grant changes, model calls, scraping, summary generation, cron changes, Gate B, rebaseline, re-onboarding, benchmark edits, AH repair, matcher/mandate edits, identity-algorithm changes, ranking, merge, push or deployment occurred. Validator inactive state and suspended crons were not rechecked; this offline work cannot independently certify their live state and did not touch them.

Rollback to old code would restore known unsafe eligibility. Any later release plan must keep affected trusted surfaces withheld/closed on rollback until a safe containment version is restored. No production rollback was rehearsed or authorised.
