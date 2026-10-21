# Addendum to the window-demonstration reconciliation (qualifications and a corrected count)

The original `RECONCILIATION.md`, the archived demonstration evidence and the originals' checksums are **unchanged**. This addendum only corrects a summary and qualifies two statements. All times are UTC on 2026-10-20; names containing `20261021`/`20261022`/`20261023` are identifiers.

## 1. Exception-count summary, corrected from the audit evidence
Authoritative source: the `control_observation` events of the policy ceremonies and the owner's `authorities_invalidated` event, all in the archives.

| Moment (audit evidence) | Bolton exception keys in the control record | State |
|---|---|---|
| Before the policy-v4 ceremony (capture-acceptance archive, `policy-v4-ceremony`) | **3**: `…CAPTURE_QUEUE_ONCE_20261018_CAPTURE`, `…STABLE_PIPELINE_AUTHORITY_ONCE_20261020_CAPTURE`, `…BOLTON_FORM_PROBE_ONCE_20261021_PROBE` | all `REVOKED_ZERO`, none unexpired |
| Before the policy-v5 ceremony (window archive, `policy-v5-ceremony`) | **4**: the three above plus `…CAPTURE_ACCEPTANCE_ONCE_20261022_CAPTURE` | all `REVOKED_ZERO`, none unexpired |
| After the window demonstration (owner event 183) | **6**: the four above plus `…WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE` and `…_SCREEN` | window pair revoked with a committed readback; the earlier four unchanged |

Corrections to earlier summaries: (a) the capture-acceptance run's screening allowance was **never registered**, so it has no key; (b) the names `HISTORICAL_0` and `HISTORICAL_1` appear only in the disposable test fixtures, never in production; (c) "the cap of three" is the registration limit counted over all keys including revoked ones: it was reached by the form probe, bypassed for the two named capture-acceptance allowances by policy v4 and for the two window allowances by policy v5, and is **unchanged for every other name**. No exception key has been removed or altered at any point.

## 2. Qualification: missing pagers
* What is established: on 20 October the recognised `p.pager` element was absent from one Bolton results page of 4 rows; the page body was not retained, so no other count or pagination signal can be confirmed or excluded.
* The only supporting observation is one earlier Bolton window (recorded 14 October; 8 rows; no pager). Two observations are consistent with the pager appearing only when results exceed one page. This is an **observed pattern, not proven council design**, and not an established rule.

## 3. Qualification: other councils
* Every retained non-empty accepted window for the other Idox councils (Bury 18, Oldham 14, Tameside 15, Wigan 17, Stockport 49) spans more than one page and shows an explicit total. That tells us how those councils present multi-page results; it tells us **nothing** about how any of them presents a single page.
* The single-page behaviour has been observed for Bolton only. It must not be generalised to any other council, and the proposed partial-observation scope is Bolton only for that reason.
* The window demonstration (24 references) shows the pipeline works for one multi-page window; it is not evidence about sparse days, other windows or other councils.
