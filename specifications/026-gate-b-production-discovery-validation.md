# Gate B — Production Discovery Validation (read-only release validation)

Status: **SPECIFICATION + OFFLINE IMPLEMENTATION.** The validation runner is built and proven offline only. Executing it against production requires separate, explicit Product Owner authority.

Related: `025-stage2-5b-acquisition-subject-decomposition.md` (families, phasing, v7), `023-stage2-commercial-evidence.md`.

## Question

> Does the completed Stage 2.5B / v7 architecture identify materially better real acquisition opportunities from the evidence PropertyAIgent already holds?

This is release validation of existing behaviour. It adds **no** opportunity logic, extraction, UI, report generator, AI summary or alert. It *reads* what the accepted architecture already computes and records it once.

## Intelligence layer / Site-centred justification

It improves no layer; it measures whether the Planning Delivery, Phasing and Family layers make a Site more intelligible to a buyer. Every output row is anchored to a Site (or an allocation) and carries its source subjects.

## Boundaries (hard)

Deterministic. Read-only. No model/OpenAI call, no scraping, no document download, no external API, no database or monitoring write, no mandate re-onboarding, no agent evaluation, no alert, no deployment, no cron. The runner never sums unit counts, infers residual capacity, claims availability, or invents evidence to raise yield.

## Funnel

current evidence → complete deterministic planning-delivery subject discovery (`load_buyer_family_inputs`) → qualified phasing derivation (the shared `AcquisitionPhasingEvidence`, via the existing B2 context) → `OpportunityFamily` construction → v7 matching per buyer (mandate read from the accepted profile store; scale bounds read from the mandate, never hard-coded) → comparison with the legacy flat buyer feed.

## One-read principle

One bounded read-only window loads the subject inputs **once** and the B2 site contexts **once** (buyer-independent, shared across buyers); every buyer is evaluated from that in-memory data. The output is one non-secret artifact (JSON plus a compact CSV). All REVIEW analysis uses the artifact, not production.

## Production-read safety (enforced by the runner before any read)

PostgreSQL backend required in real mode; the application's own engine route (`app.db.session.get_engine`) and `DATABASE_URL` from the environment only; `SET TRANSACTION READ ONLY` then verified (`SHOW transaction_read_only = on`); `SET LOCAL statement_timeout`; a statement allow-list (SELECT/WITH/SHOW and the two SET forms only — anything else raises); ORM write guard (`before_flush` with pending changes, `before_commit`); always rolled back; network guard (only the database host may be connected to); model-client modules must not be loaded. A synthetic mode (SQLite) exists for tests only and cannot be selected for production.

## Definitions

* **Phase subject** — a family member whose slot is a named phase. **Qualified phasing evidence** — the shared state (CURRENT_EVIDENCED_PHASE, PHASE_EVIDENCE_CURRENTNESS_UNKNOWN, HISTORICAL_PHASE_ONLY, NONE_IDENTIFIED). They are reported separately: a phase subject can exist while the qualified state is NONE_IDENTIFIED (address-only label, or no substantive granted anchor).
* **Oversized wider family** — a family with a wider (non-self-phase) planning-delivery subject for which `phasing_is_acquisition_relevant` holds for the buyer (above the mandate's discovery maximum, total-units mandate).
* **Comparable legacy window** — the legacy flat feed (`build_opportunity_feed`, buyer mode) called with the *same* limit N as the family shortlist, so the two result windows are the same size.
* **NEWLY_SURFACED** — a family shown in the new top-N for which the legacy window contains **no card for that site/allocation at all**. Mere regrouping never counts.
* **BETTER_REPRESENTED** — the legacy window contains card(s) for the site but the new representative subject is a different, strictly better-fit subject (fit rank), or several legacy cards for the site collapse into one family.
* **UNCHANGED** — the legacy window already presented the same representative subject.
* Absence from the legacy *window* is all that can be established; the legacy candidate pool is not re-derived, and the artifact says so.

## Ordering and shortlist

The shortlist is the first N (default 20) non-excluded families in the existing v7 family order (fit bucket, then lexical family key). Ties are **non-commercial**; the artifact states this. No new ranking is introduced.

## Negative / missed-evidence cohort (for a later, separately authorised Stage 2.6 audit)

Recorded from already-loaded facts only: oversized wider families with no qualified phasing; phase subjects without qualified phasing; currentness-unknown phasing; phase subjects without an exact count; families with no buyer-relevant scope. No document is read.

## Artifact

`run_metadata` (code SHA, policy/benchmark/fingerprint versions, timestamp, mandate digest, safety status), `aggregates`, `buyers`, `nesten` (population + review families + shortlist), `negative_cohort`, `efficiency`, `definitions`. No credentials, URLs or tokens. Deterministic for identical input and clock.

## Execution

Not authorised by this specification. See the Gate B preflight report for the proposed route and the exact authority required.
