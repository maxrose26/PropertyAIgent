# Tameside pagination — demonstrated fix and REVIEW handoff

Master Stage 4 OPEN. Current gate: demonstrated correction of the Tameside pagination refusal. This correction is ready for REVIEW. Live navigation beyond the first page, full council coverage and another bounded B intake remain unverified and unauthorised.

## Exact revisions and execution

- PR #211: `stage4/period07-followup-20261105`.
- Diagnostic code: `e0605d8d8f4564bceeffff284f9328b2cff42ecb`.
- Final corrected code: **`56a8a420ae21f60633dc2b8eea4c2f61ef5659a1`**.
- Existing owner checkout: `e191729bd9f05224932fef9903341d99d63650de`, verified clean; preserved unchanged.
- No production deployment, service environment/configuration change, source branch update or Render job submission occurred. The one diagnostic ran as an isolated child of the existing owner Web Shell using the existing operational supervisor, in `/tmp/propertyaigent-tameside-diagnostic-20261105-01`.
- Separate diagnostic identity/directory: `diagnostic-once`, exclusively created and marked consumed before execution. It is not an intake period and must not be rerun.
- Started **5 November 2026, 14:23:04.876996 UTC**. Source scope: Tameside RECEIVED, 27 October–2 November 2026 inclusive.

The diagnostic checkout was exported from the existing owner checkout, with the published diagnostic module, source-worker change and unchanged diagnostic-enabled pagination module transferred and hash checked. No alternate worker implementation was used. The source child received the existing supervisor's clean environment and no database credentials. Its stdout/stderr were suppressed; only sanitised output was read back. The initial ad hoc dormant check omitted the stable-verifier binding and refused; the unchanged stable-credential-aware validator then passed before execution. That refusal caused no write or source request.

## One live diagnostic: complete accounting

Exactly **3 physical HTTP requests**: FORM GET, SEARCH POST, SORT POST. Zero retries. No redirect hop was followed; any redirect is refused with automatic redirects disabled. The three-request guard checks before transport and includes every dispatched request. No PAGE or REFINE operation exists in this mode.

- Received bytes: **153,361** of 3,000,000 maximum; per-response ceiling 500,000.
- Supervisor elapsed: **7.273851525 seconds** of 45 maximum.
- Exit 0; limit_hit null; accounting_complete true.
- Source cleanup SESSION_BOUNDARY_CLOSED; supervisor cleanup CLOSED; survivors 0.
- Peak observed owned RSS: 105,963,520 bytes.
- Diagnostic result OBSERVED_FIRST_SORT_ONLY; coverage NOT_ESTABLISHED.

The original period07 intake retains its own three accounted requests. These three new diagnostic requests are separate; neither counter overwrites the other.

## Demonstrated cause and correction

The observed first sorted response reproduced CALIBRATION_NAVIGATION_AMBIGUOUS / NUMBERED_LINK_SKIPS_ADJACENT_PAGE. Both top and bottom pagers contain numbered links 2, 3, 4 and 5, plus explicit Next to page 2. The old `directions()` rejected the page-3 link simply because it was not the immediately adjacent page, before selecting the consistent Next action.

The correction validates later numbered links inside recognised pager containers, including exact same-origin route, label/target agreement, allowed parameters and bounded page number. They never authorise navigation. Explicit Next still must identify the adjacent page; conflicting Next controls, numbered-only navigation, changed parameters, malformed destinations and other ambiguities refuse. Later pages inconsistent with displayed totals also refuse.

The corrected decision on the sanitised observed response is exactly GET `/online-applications/pagedSearchResults.do?action=page&searchCriteria.page=2`.

A representative five-page fixture with both complete pagers on every page then exposed CALIBRATION_TRACE_BOUND. The correction deduplicates identical control maps in the trace and retains their occurrence counts. The original 8,192-byte trace limit, request limits, count reconciliation, duplicate detection, terminal-page checks and criteria readback remain intact.

The historical period07 DOM was not retained. This new observation demonstrates and reproduces the defective rule under the same window; it does not reconstruct the discarded historical HTML. Period07's original outcomes and receipt remain unchanged, including exact_navigation_cause UNPROVEN.

## Retained evidence and redaction

Only sanitised structural markup, allow-listed pagination labels/fields/destinations and fixed refusal codes were retained. Credentials, cookies, CSRF/session values, listing text, scripts and unrelated link targets were not retained. The original and sanitised navigation decisions matched before the original body was discarded.

- Original sorted body SHA-256: `ef21dfb5314dc7e858b2e9d2a3e0b744e79a0550306dff937c67cbecb67ac6d9` (hash only, no raw body archive).
- Sanitised observed fixture: `tests/fixtures/tameside_pagination/observed-first-sort-20261105.html`, SHA-256 **`06828e49e5e451ea2ca24b469db36d6b21c77d861db3b0191875ec48fcc9a323`**.
- Original compact diagnostic result file SHA-256: `e7bcc973542b551e1051edd15aad9aa49cd880c7a5863be64cc186c50e6c94c7`.
- Retained combined sanitised report and supervisor result: `tameside-diagnostic.json`, SHA-256 `07ca5ad23b60c5d0a28a9f6341e8f4e9bfc9bfa9e657e9a342ba427487d79454`.
- Frozen pre-fix directions function (test fixture only): SHA-256 `217c01f67ebfbab2dd8105d270b373bf3d2cd4d4d9ea38ea91dab32704348675`.

## Validation

**170 local focused tests passed** on the final code. These exercise the actual source worker, Requests session/adapter path and boundary with offline responses; fourth-request refusal before transport; redirect refusal/counting; disabled retries; unconditional stop for valid multi-page and terminal responses; token redaction; old-code refusal and corrected-code next action on the observed sanitised fixture; ambiguous mutations; multi-page capture validation; and existing pagination/calibration safeguards.

Hosted PostgreSQL 17 validation on final code, [run 42045703206](https://github.com/maxrose26/PropertyAIgent/actions/runs/42045703206), job `127307922379`:

- **98 focused diagnostic/navigation/settlement tests passed**.
- **31 targeted B readback tests passed**.
- **72 Attempt06 owner-path tests passed**.
- **92 connected restricted-ledger intake tests passed** (synthetic sources).
- Historical B-readonly suite: 16 passed, one frozen inventory assertion failed, as on the accepted baseline.

Overall CI is not green. The 11 legacy timeout continuation cases still fail (1,508 pass); they were previously reproduced identically on the accepted baseline. Two other suites retain baseline assertion failures: an application import of verification in unchanged `app/ingestion/batching.py`, and the old exact request-boundary digest assertion. The same offending path and actual boundary digest were independently confirmed on the accepted owner tree and final candidate. No historical hashes, tests or application guards were changed to suppress these unrelated failures. This is not a claim of whole-release readiness.

## Independent state verification

Fresh read-only checks before execution and at **14:29:41.316582 UTC** after execution verified:

- Period07 settlement receipt remains `b461d84c45aadbea3bab1960273cedcf55f75a19b967b5d71a205d587ba8fb44`.
- Archived marker and original artifacts unchanged; all three original hashes match.
- Tameside SAFETY_BLOCKED/RECOVERED, fence 2; attempt closed; checkpoint absent.
- Generation 9; global DAILY_INTAKE_SHARED_FAILURE active; manual stop and last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP.
- Temporary memberships 0; runtime sessions 0; stable restricted credentials dormant.
- Attempt06 history remains valid, including UNKNOWN historical cause/count and Manchester NOT_ATTEMPTED.
- All readback transactions rolled back; no database writes in this diagnostic task.

Bounded readback: `diagnostic-post-readback.json`, SHA-256 `daf2d1ec70716365e58251a2219150ffb5c7d651849d89c27eef035ffa68e0f5`. Render inspection confirmed scheduled collection remains suspended and auto-deploy disabled.

## Decision

**GO for REVIEW of the demonstrated pagination correction.** No further diagnostic request is needed for this fault. No owner action is required to finish this investigation.

**Not yet proven:** actual navigation to live page 2 or later, live terminal-page/criteria reconciliation, Manchester coverage, live capture/retention/screening/backlog with this correction. These require a separately authorised deployment and bounded intake test with a newly bound release and unused period. Period07 is consumed and must not be replayed. Stop clearance, runtime access reopening and intake submission remain on hold. Stage 4 remains OPEN.
