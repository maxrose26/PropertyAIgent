# 033. Retaining and screening verified records when window completeness is unknown

Status: **proposal for review; nothing here is implemented.** Depends on specification 032 (sections 12-14). Stage 4 remains OPEN.

## 1. Intelligence layer and purpose
Planning Applications (the record layer that feeds every Site). Goal: a verified listing record should remain usable and screenable even when the *window* it was found in cannot be proved complete, **without** any claim of completeness, absence or coverage.

## 2. Evidence this rests on (and what it does not show)
* 20 October 2026, Bolton RECEIVED 16 October only: the source returned 4 verified rows on one page; the recognised `p.pager` element was absent; every other count or pagination signal could not be assessed because the page body was not retained. The existing contract (correctly) refused completeness (`TOTAL_UNKNOWN`) and the run stopped fail-safe.
* An earlier real Bolton observation (recorded 14 October, window 19 February 2026) saw 8 rows and no pager. Two Bolton observations are consistent with the pager appearing only when results exceed one page: an **observed pattern, not proven council design**.
* Every other retained non-empty accepted window (Bolton 22 and 24, Bury 18, Oldham 14, Tameside 15, Wigan 17, Stockport 49) is multi-page with an explicit total (Bury also has one explicit-zero result, a different signal). **No other council's single-page behaviour has been observed**; nothing here is evidence about them.

## 3. Principle: two claims that must never be conflated
* **Record claim** - "this reference was listed by the council with these literal fields at this observation time, with this provenance". Verifiable per record.
* **Window claim** - "these are all the records for this window". Needs an explicit source signal (today: `COUNT_RECONCILED`).
A *partial observation* asserts the record claim only. Its window claim is the constant `NONE`.

## 4. The partial observation (a new receipt kind, not a weaker receipt)
`LISTING_OBSERVATION_V1`, distinct from `LISTING_RECEIPT_V1`. Fields: council, requested interval, applied-interval echo evidence (hash), `records[]` (each with reference, source key, literal fields, page body sha, row ordinal, observation time), resource accounting, source and supervisor hashes, and the constants `window_claim = NONE`, `enumeration_evidence = TOTAL_UNKNOWN`, `completeness = NOT_CLAIMED`, `absence_inference = PROHIBITED`, `coverage_watermark = NOT_ADVANCED`. There is **no field from which completeness could be read**, so it cannot be mistaken for a receipt.

## 5. Admission (initial scope: Bolton only, evidenced behaviour)
Admitted only when **explicitly enabled by the registration** (default stays the existing fail-safe stop) and **all** hold: the form GET is valid and one form request only; the criteria echo strictly equals the requested interval; exactly one results page with no next link; no `p.pager` element and no other parsed count signal; rows at most the page size; every row passes the existing strict row validation (identity present and unique, date inside the interval, canonical URL); zero redirects and retries; the unchanged ceilings. Anything else - a pager that disagrees, a next link without a pager, an echo mismatch, a duplicate reference, a row outside the interval - stops exactly as today. Zero results for Bolton are unobserved and out of scope.
Admission does **not** infer completeness from the short page; it records that a bounded set of valid records was observed and that completeness is not claimed.

## 6. Prohibitions (enforced in code, not convention)
P1 no completeness claim; P2 no absence inference ("no other applications were received"); P3 no new-application detection or "seen before / not seen" logic using the kind; P4 no completeness watermark or coverage metric advance; P5 never supersedes or downgrades a `LISTING_RECEIPT_V1`; P6 every consumer that needs a window claim must reject the kind by type.

## 7. Reuse (no rewrite)
Unchanged: window runner and request boundary, `parse_page`, resource ceilings, durable archive before checkpoint, queue, publication-before-closure, authority invalidation, the allowance machinery (a partial-capable run is bound by an ordinary registration; no generation-agnostic policy is introduced). Split, not duplicated: the adapter's checks become `validate_records` (record validity, shared) and `validate_window_completeness` (receipt only). Record-level screening (`listing-screen-v1`) is window-independent and is reused as is, with the child item recording its source kind. Council enablement is a configuration list (`bolton`), so other Idox councils stay on the stop until they have their own evidence.

## 8. Outcome vocabulary
A partial run reports `PARTIAL_OBSERVATION_RETAINED_SCREENED_AUTHORITY_INVALIDATED` (never `...COMPLETED...`), with `window_claim: NONE` shown prominently in the owner and hosted results and the reconciliation note. It is an accountable outcome, not a fail-safe stop, only because the registration enabled it.

## 9. Open decisions (before implementation)
Whether to require rows below the page size; how repeated observations of one day are shown together; presentation wording in product surfaces ("observed listing sample, completeness not established"); retention period; whether a later complete receipt may annotate (never replace) earlier observations.

## 10. Acceptance criteria
1. **Schema separation.** The kind has no completeness field; a contract test asserts `window_claim == NONE`, that no `COMPLETE` value is representable, and that it cannot be parsed as a receipt.
2. **Fixture admission.** The archived 20 October 4-row single page (as a loopback fixture through the real source boundary) is retained as `LISTING_OBSERVATION_V1` when enabled and stops with `IDOX_WINDOW_BINDING_OR_COMPLETENESS` when not enabled (existing behaviour unchanged).
3. **Anomalies stop.** Each admission condition in section 5 has a failing fixture that still stops.
4. **Prohibitions hold.** Behavioural tests: absence queries return `UNKNOWN`; the new-application logic and watermark/coverage writers reject the kind; every existing completeness consumer rejects it by type.
5. **Screening parity.** The same records screen identically whether they come from a complete receipt or an observation (golden test), with the source kind recorded on each child.
6. **Durability and closure.** Raw archive before checkpoint, owner verification of retention, publication-before-closure and invalidation behave as for complete receipts, proved in the disposable lifecycle including the real memory scope.
7. **Ceilings and policy unchanged.** No ceiling, retry, redirect or policy change; no generation-agnostic allowance; enablement only by an explicit registration field validated by the owner.
8. **Provenance.** Each record carries page body sha, row ordinal, observation time and source URL; the receipt carries the requested interval and echo-evidence hash.
9. **Reporting.** Results and notes state the partial status and `window_claim: NONE`; a reconciliation template distinguishes recorded from recomputed values.
10. **Dedup and conflict.** Records dedupe by (council, reference); a conflicting repeat is flagged, never overwritten.
11. **Scope.** Only `bolton` is enabled; any other council stops as today.
12. **No live attempt is needed to prove the specification; a first live use needs its own approval.**
