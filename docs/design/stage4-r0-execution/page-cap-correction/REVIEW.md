# TO REVIEW — PAGE-CAP CORRECTION AND FIXED-80 QUALIFICATION PROPOSAL

Master Stage 4 remains **OPEN**. The current gate is cron-suspension source-date catch-up.

The offline transport correction and bounded proposals are ready for review. **Live execution is not ready or authorised:** aggregate qualification supervision and single-use registration remain outstanding. No merge, registration, source call, production query, admission, retry, model call, schedule or deployment occurred.

## Baseline and preserved evidence

Base/master: `1db78f4f44dd8ff9f28140a98ad15116ca1d5ee0`.
Tree: `5bf6f27756b587e7d35d9b2302ad3e3acb6a2d3c`.

Comparison run **38742149312** is accepted and consumed: 80 ABSENT at `2026-10-15 13:28:37.830429+00:00` — Bolton 54, Bury 26; known, duplicate and unresolved counts all zero. This proves snapshot absence, not eligibility or commercial value.

Recovery run **38744118357** is consumed: it safely stopped after Manchester's first window reached PAGE_CAP, retaining 60 of 73 records. The other 27 primary windows were not attempted. Recovery coverage and database catch-up remain incomplete.

The execution evidence is preserved at commit `c93c33f4f5668ffd83fbcefdb0f3bfaee6c39139`. No historical workflow, authority, manifest, audit or seal was altered. This candidate adds a byte-identical copy of the consumed recovery ZIP as a regression fixture; it does not rewrite the historical result.

## Transport correction

`verification/direct_reference/instrumented_probe.py` now calls `classify_ui_enumeration` immediately after the actual `enumerate_ui` call.

- COUNT_RECONCILED behaviour is unchanged.
- PAGE_CAP with completeness INCOMPLETE, no listing exception and no prior failure/safety flags produces `listing_outcome=BOUNDED_PAGE_CAP` without calling the fatal handler.
- Candidates, criteria and segments remain retained. Coverage remains INCOMPLETE.
- Prior failures are never cleared. No recovery-caller safety flag is bypassed.

The existing recovery guards still stop wrong identity/destination/criteria, source exceptions, security failures, uncertain accounting, cleanup failures and unclassified outcomes. Neither the 60-reference/six-segment cap nor any COMPLETE rule changes.

The new offline regression drives actual `enumerate_ui` using finite locator doubles, actual segment qualification and transport classification, then actual `finite_acceptance.read` and `r0_recovery_proposal.execute` with intercepted supervision. It proves retained candidates and uncertainty, safe continuation to the next untouched window, and hard-failure mutations stopping before a second source call. It does not claim live-browser proof.

## Missing-total path

The retained Bury Idox observation has `TOTAL_UNKNOWN`, no source failure, qualified criteria/identities, certain accounting and closed cleanup. It already passes the existing recovery safety/local-gap checks. The finite Idox child entry writes that observation without converting missing count evidence into a source exception. No Idox correction is justified.

Arcus currently has no admitted ordinary missing-total marker shape. Missing or malformed markers raise a listing exception under the existing parser; they remain fatal. This change does not reinterpret those exceptions or qualify a new source shape. No Bury or other live source investigation occurred.

## Fixed-80 qualification proposal

Manifest: `fixed80-qualification-manifest.json`.

SHA256: `1c4cb696cfd352532a0c19fe9e919e86059908cc3cf21ed37f8be2ec8ab23b12`.

The exact identity set/order matches the accepted comparison manifest:
`cf31d3a5dd69da7c65348428473a0bb15cf38071caab41b5db76b6d5ea8845cd`.

All five Bury UNKNOWN-window candidates remain: **73755, 73748, 73743, 73742, 73741**. Exact official URLs, source keys and listing fingerprints come from the retained original R0 candidate ledger. No fresh lookup supplied them.

| Council | Records | Approved destination family |
|---|---:|---|
| Bolton | 54 | `https://paplanning.bolton.gov.uk/online-applications/applicationDetails.do` |
| Bury | 26 | `https://planning.bury.gov.uk/online-applications/applicationDetails.do` |

Each exact URL and literal query ordering is frozen in the manifest. Existing destination validation permits only HTTPS, the exact council host/path, the frozen `keyVal`, and `activeTab=summary`; no extra query, fragment, search, address lookup or document route.

### Implemented proposal code

`verification/discovery/r0_fixed80_qualification.py` provides a finite caller requiring explicit reader and checkpoint injection, a create-only fsync checkpoint helper, and a worker-only CLI. It has **no parent execution CLI or registered workflow**.

Its 80 closed cases delegate to the existing instrumented owned-process supervisor, existing Idox worker and existing projector. There is no new parser, factual writer or persistence model. An actual Popen-interception test verifies the exact worker module/case and seven-key credential-free child environment; this is stronger than checking a source string alone.

The proposed parent rejects database, Supabase and model credential contexts. It does not execute engines, admission or B2. B2 eligibility is observed, not changed or persisted.

| Dimension | Proposed result |
|---|---|
| Identity | Fresh exact displayed reference, correct council and frozen official destination |
| Facts | Existing reference/status/decision/date field states, supported literals and body fingerprint |
| B2 eligibility | Existing result plus rejection diagnostics, unchanged |
| Materiality | Retained conservative outcome and original qualification labels/reasons |
| Site relationship / role | UNKNOWN unless separately qualified; no automatic site, link or opportunity |
| Admission readiness | ELIGIBLE_FOR_REVIEW_ONLY or WITHHELD_PENDING_EVIDENCE; never creation authority |

Unknown scale or relationship does not cause exclusion. Existing Ignore/admin/non-residential labels remain visible for qualification; they are not silently promoted or discarded. No new confidently non-material exclusions are invented. Existing parser rejections remain truthful withheld outcomes, not council-wide unsupported classifications. Missing optional facts retain their existing states. No evidence/B2 semantics change.

### Budgets and stop rules

| Layer | Limit |
|---|---|
| Existing Idox worker | 2 requests total, including its accepted internal retry; 2,000,000 received bytes; 40-second reference deadline; 1,000,000 bytes per response |
| Worker process | Existing CPU 30 seconds/address space 512 MiB; supervisor 45 seconds/1 GiB RSS; wait 5 seconds plus owned-process cleanup 3 seconds |
| Reservation | 55 seconds per record; worker audit below 65,536 bytes |
| Fixed cohort | 80 sequential calls; 160 requests; 160,000,000 received bytes; 4,400 seconds; 8,000,000 audit bytes |

Capacity derives from **80 × the existing per-record limits**, not an arbitrary three-record batch size. The caller reserves worst-case cost before each call, validates counters through the shared projector and requires a checkpoint before proceeding. A checkpoint failure stops it. No retry/resume beyond existing bounded HTTP behaviour; rate limits are not retried.

Closed, certainly accounted TIMEOUT, SOURCE_UNAVAILABLE or RATE_LIMITED observations may be withheld while subsequent records continue. Ambiguous identity, partial/unapproved destination, malformed audit, parser/generic exception, security/resource/cleanup uncertainty and unclassified failures stop the cohort. PARSER_FAILURE is deliberately a hard stop because generic worker exceptions share that code.

**Aggregate hard supervision is not yet implemented or execution-qualified.** Registration must reuse the existing owned-process outer-supervisor pattern, binding the exact fixed manifest/module, a 4,400-second deadline, 1.5 GiB RSS, bounded aggregate output and durable checkpoint collection. Proposed workflow backstop: 4,500 seconds plus 10-second kill grace, 80-minute job, with cleanup/upload reserve. A shell timeout alone is insufficient for independent child process groups.

Before execution, tests/review must prove actual outer delegation, output collection, credential-free workers, exact SHA/workflow SHA, clean master checkout, run 1/attempt 1, new single-use authority and zero prior runs. No protected production environment or secret is needed.

Proposed workflow, currently **absent**:
`.github/workflows/stage4-r0-fixed80-qualification-once.yml`

Proposed authority:
`AUTHORISE_R0_FIXED80_EXACT_RECORD_QUALIFICATION_ONCE`

These are proposals, not dispatch inputs. Final registered revision/blob identities must be reviewed later. Qualification cannot automatically freeze or admit a production cohort. Admission must independently protect against current duplicates/races; snapshot absence is not future absence.

## Exact 27 untouched windows

Manifest: `untouched27-manifest.json`.
SHA256: `f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d`.

Its rows/order exactly equal the consumed recovery artifact's `not_attempted` list:

| Council | Windows |
|---|---|
| Manchester | 24–30 September; 1–7 October; 8–14 October |
| Oldham, Rochdale, Salford, Stockport, Tameside, Wigan | 17–23 September; 24–30 September; 1–7 October; 8–14 October |

No Bolton, Bury or Trafford. The capped Manchester 17–23 September window is excluded. The cut remains 15 October 2026 00:00 Europe/London; 15 October onward remains the bridge.

Derived limits: **27 calls; 1,040 requests; 278,686,720 bytes; 1,900 seconds; 20 MB audit**. These equal 11 Arcus calls at 80 requests/20 MiB and 16 Idox calls at 10 requests/3,000,000 bytes. No increase to prior ceilings.

No 27-window executable binding or workflow was registered here. A new reviewed binding must freeze this manifest and test actual outer wiring and single-use restrictions. The consumed 28-window workflow must not be repurposed or resumed.

Proposed authority: `AUTHORISE_R0_27_UNTOUCHED_PRIMARY_WINDOWS_ONCE`.

## Separate unresolved-window proposals

**Manchester, 17–23 September, VALIDATED:** 60 of 73 references retained; overlap-only coverage gap. Do not replay the window or raise caps. If full source-date coverage is required, propose separately frozen partitions **17–20 September** and **21–23 September**, retaining existing per-call caps: at most 2 calls/160 requests/40 MiB/110 seconds worker reserve. Counts below cap are unproven; another cap stays INCOMPLETE. Independent observation would require the checkpoint amendment below. No partition execution or manifest is authorised now.

**Bury, 8–14 October, RECEIVED:** five candidates retained, count/terminal contract unresolved. No concrete parser defect is established. Recommend retaining the explicit UNKNOWN residual while progressing the 80 target candidates and 27 untouched windows. If REVIEW requires resolution, propose one separately authorised exact-window ordinary UI count/terminal assessment: at most 6 segments/60 references/10 navigation actions/15 minutes; browser request/byte totals UNKNOWN if unmeasured. No new route or investigation loop. An inconclusive result stays UNKNOWN; it does not authorise automatic follow-up or replay of R0.

Neither residual needs to block safe independent qualification work. Neither proposal accepts a blanket publication-recall limitation.

## Independent evidence and procedure

`independent-only-candidates.json` preserves **283 unique references** not established as primary detections:

| Council | Retained references |
|---|---:|
| Manchester | 10 |
| Oldham | 43 |
| Rochdale | 53 |
| Salford | 114 |
| Stockport | 47 |
| Tameside | 16 |

Window groups retain literal references, official URL, seal provenance and criteria/timing evidence where retained. Database presence remains UNKNOWN_NOT_QUERIED; primary detection NOT_ESTABLISHED; individual date membership UNKNOWN where no literal date exists. Tameside's 16 references retain unproved criteria/count. These are not 283 proven material misses or opportunities. No lost reference set is reconstructed, and the consumed fixed-80 query is not expanded.

Reuse the 12 complete independent windows only where retained criteria, count, terminal state, literal identities and observation chronology support the exact comparison. Other rows remain partial/not attempted. Later source changes may explain differences; do not automatically call them parser misses or copy primary output into a denominator.

The Manchester stopping-rule deviation and browser-reset retention/accounting losses remain acceptance limitations. Original sealed ledger hashes remain unchanged:

- `715da66d96a643800c7a30df9ae88481e7fc2576d89fc55a4ec93484a2049f17`
- `7a46aa77843e85b226f1f1a0982feff79a2d111a4a93596a37ad953a0c7ceb23`

`ASSESSMENT-CHECKPOINT-PROCEDURE.md` proposes the smallest procedural amendment: persist action intent/budget reservation before navigation; fsync bounded segment evidence/counters before the next action; no multi-window runtime batches; immutable numbered checkpoints and seals; pending actions UNKNOWN after reset; no budget reset/replay; stop on checkpoint/accounting uncertainty. Strict cap-stopping language remains explicit. This is not a new browser platform or monitoring service.

## Validation and review

- **125 affected tests passed**, network denied, zero failures.
- Independent reviewer separately passed **32 focused tests** and found no material defect.
- Actual supervisor argv/environment interception was added after review feedback.
- Consumed ZIP and original seals remain byte-identical.
- The discovery workflow invokes both new test suites and adds fixture/test path triggers.
- Applicable exact-head hosted results will be reconciled on the published draft; no stale check is counted.

Initial test-harness issues were corrected without changing production guards: finite synchronous coroutine driving avoids the network-denied wrapper's prohibited asyncio socket pair; the Popen test supplies an explicit synthetic process namespace. No live source was used to test the correction.

`CODE.patch` records the code/CI/test diff against the exact base. The PR provides the complete changed-path diff, including manifests, fixtures and documents.

## Decision requested

Review the exact candidate and hosted checks. If accepted, authorise guarded `[skip render]` integration of the correction and bounded registration completion for the two proposed new scopes: fixed-80 fresh qualification and exact-27 untouched observation. Registration must finish/test hard outer bindings and return final master/tree/workflow blobs/manifest inputs for exact execution confirmation. **Neither execution is authorised by this pack.** No extra canary or diagnostic programme is proposed.

After fresh qualification, REVIEW may freeze an eligible cohort for the existing shared admission/B2 path, with automatic current duplicate/race protection and bounded committed readback. No routine approval per arbitrary three-record batch is proposed.

Publication recall, unsupported latency and the 15 October onward bridge remain unresolved. No admission, evidence relaxation, site/opportunity automation, Trafford work, Stockport reinvestigation, prospective acceptance, model call, schedule, deployment or Stage 5+ work occurred. Stage 4 remains OPEN.
