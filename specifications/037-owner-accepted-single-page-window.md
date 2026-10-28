# 037. Owner-accepted single-page window (Oldham RECEIVED 15-21 October 2026 only)

Status: **proposal for owner review, implemented dormant and default-off in the accompanying candidate.** Depends on specifications 029, 033 and 036's evidence principles. Stage 4 remains OPEN. No live execution, registration, merge or admission is authorised by this document.

## 1. Intelligence layer and purpose
Planning Applications (the record layer that feeds every Site). The existing Oldham RECEIVED 15-21 October 2026 observation returned five verified records that the existing contract correctly refuses as complete: the page showed no pager, no total and no terminal marker
(`TOTAL_UNKNOWN`). The remaining question is the qualification of this single-page layout, not a demonstrated extraction defect. This specification lets the owner accept THIS ONE window, as an explicit, labelled, hash-bound decision, so that its five records can be
considered for retained capture through the unchanged gates. It is **owner-reviewed acceptance. It is not source-reconciled completeness and not a rule about short pages.**

## 2. Evidence this rests on, and what it does not show
All identifiers are SHA-256 digests; no record text, address or screenshot content is stored in the repository.
* **Source audit (immutable, stays UNKNOWN):** `97a3fe071da69a7fde32ee7bc663a19d8543c0e49fca5a127415c7e8c7ebc671` (evidence branch commit `d0eea18a7a9e1353ff4d281c68dc288dc3363196`, `slot-0/source.json`). Oldham, RECEIVED, 2026-10-15..21; one page of five unique records;
  `first`, `last`, `total` and `terminal` null; `enumeration_evidence` `TOTAL_UNKNOWN`; same-session post-enumeration criteria binding; four requests, no retry, redirect or cap. Its slot receipt carries source-bound `SOURCE_CGROUP_READBACK` supervisor evidence (elapsed 8.04 s).
* **Calibration (diagnostic evidence, not a registered collection audit):** one session over the wider window 2026-10-08..21 that the portal itself reconciled (`Showing 1 - 10 of 16`, `Showing 11 - 16 of 16`, last page explicit, a page-after-last response with an explicit empty-range marker for the same total, session criteria echo, invalid-page control different). The five records dated 15-21 October in it are equal to the original five by the joint digest of the complete records (identities, URLs, field states, values and locators).
* **Owner review:** a screenshot (SHA-256 `c57229ec99713bf9c75c35a46180da32d75b60e92eced076cc1a4ffef0287949`, 279,137 bytes) of the council results page with results-per-page 100, five applications, the bottom of the results list and the footer visible and no pagination controls. It does not show the searched dates.
* **Times are separate and not unified.** Source events: 2026-10-28T06:54:14Z to 06:54:19Z (the audit's own event times). Calibration: registration issued 2026-10-28T08:54:33Z; private response files written 08:54:43Z to 08:54:52Z (filesystem times, not source-attested; exact request times were not recorded).
  Manual review: the screenshot's screen clock shows 09:35 on 28/10/2026 and its file name 093601; the timezone is not stated; the searched criteria are not visible. The owner's decision time is UNKNOWN (recorded in conversation only). No common observation time and no retrospective certainty is claimed.
* **Not shown:** a source-stated total for this exact window (the portal states none at ten per page); that no later application will carry a RECEIVED date in the window; anything about any other window, council or observation.

## 3. The rule (closed, default-off, one window)
1. `IdoxListingContract` gains an optional `owner_acceptance` parameter, default `None` (behaviour unchanged). It takes only a KEY STRING; the contract resolves it in a closed, in-code registry (`app/ingestion/owner_acceptance.py`) holding exactly one entry, `OLDHAM_RECEIVED_20261015_20261021_V1`.
   A caller cannot pass an acceptance object, a file or a hash. The key must match the contract's council, date basis and interval.
2. It applies only to a source whose `enumeration_evidence` is `TOTAL_UNKNOWN` AND which is the exact bound audit: `digest(source)`, council, basis, requested and applied interval, applied-criteria hash, the single page entry (all pagination facts null, page-body hash, page size, row count) and the joint digest of
   the complete records (the informational `processing_screen` annotation excluded) all equal the registry entry. Any difference refuses. A source that carries a pager, total or terminal uses the normal rule; the acceptance is never consulted.
3. Every other existing gate is unchanged: collection-profile binding, supervisor evidence, resource and accounting bounds, criteria binding, response provenance, per-row validation, archive and readback, authority, stops.
4. Source pagination facts stay as observed (`terminal` is null in the receipt's segment). Acceptance is stored as separate evidence: the receipt carries `completeness_basis = OWNER_ACCEPTED_SINGLE_PAGE` and `owner_acceptance = {key, sha256}`.
5. `WindowEvidence` gains `completeness_basis` (default `SOURCE_TERMINAL`) and `owner_acceptance_sha256`. For the owner basis it is COMPLETE only with a null source terminal and a valid acceptance hash. Admission still requires COMPLETE; the basis travels with the window proof.
6. `completed_through` advances only over windows with basis `SOURCE_TERMINAL`. Owner-accepted windows never advance coverage.
7. Authority: the acceptance is code in the reviewed repository (its digest is pinned by a test); it is not data a runtime caller can supply. Use in an execution requires the later owner-approved Oldham package, which gains an explicit field `owner_acceptance` (new package version) and seals the acceptance digest in its
   qualification binding, beside the revision, tree and dependency hashes that already cover the registry module.

## 4. What this does NOT do
No automatic acceptance of future short pages or other windows or councils; no general human-override framework; no change to the source audit, its UNKNOWN classification or any historical evidence; no coverage advance; no nominee eligibility (frozen-v3 screening still decides every record, and a valid outcome is zero nominees);
no change to qualification, supervisor, resource, archive, stop or authority gates; no source or database contact.

## 5. Consumers traced
`IdoxListingContract.project` and `admission_window` (changed); `WindowEvidence.outcome` and `completed_through` (changed); `admit_identity` and `new_identity.execute` (unchanged: require COMPLETE; the contract re-derives the window proof, including the basis, from the archived receipt at admission);
`batch_plans` and the SQL batch binding (unchanged: bound by the capture digest, which covers the receipt and so the basis); `derive_nominees` (adds the receipt basis to the sealed nominee set); `operational_controller._execute` (its hard-coded `COMPLETE_METADATA_RETAINED` label becomes
`OWNER_ACCEPTED_SINGLE_PAGE_METADATA_RETAINED` with the basis for an owner-accepted receipt); `oldham_owner_package` (new version with the explicit field); `discovery_acceptance` (independent: takes complete councils as an input); the Bolton, Bury and Arcus paths and historical reconstructions (not wired to the acceptance).

## 6. Remaining qualification
Packet-specific carry-forward review of the returned metadata, criteria, enumeration, provenance and supervisor evidence; the archive and readback of the retained audit; the owner-approved execution package; frozen-v3 screening of the five records (nomination is separate and may be empty). Acceptance establishes none of these.
