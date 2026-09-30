# Specification 020 local integration review

Local implementation checkpoint, not acceptance or release approval. Base e6f0e2197ef988005af42f7fd86c2e020c24f09e on review/ah-downstream-audit. P0-A untouched. Specification 019, production data, histories, matching version 5 and production configuration unchanged.

## Implemented locally

- Immutable AHClaim/AHAssessment/TenureClaim contract, independent count and percentage review, explicit bounds and source/scope qualification. Missing dates remain missing. No quantitative prose parser, percentage-derived count, private-unit subtraction or invented tenure.
- Shared min/max assessment, inclusive threshold-relative 10% band for qualified approximate points only. A component cannot establish a whole-scheme maximum. Compound bounds are applied to each same conflicting alternative, never different favourable alternatives.
- Legacy adapter retains reported count, percentage, tenure and narrative; a populated record is not a qualified estimate. Current records lack structured count provenance and therefore have unknown qualification.
- Both buyer facts paths carry an assessment. AH-scale/package decisions use it, separately from percentage review. Estimates remain investigation candidates, not STRONG_FIT solely on an estimated essential criterion. Independent specialist/retirement exclusions remain in place.
- Explore manual and parsed bounds share one joint assessment, with explicit minimum/maximum activation and separate investigation/unknown selection. Selected-record CSV includes the same assessment columns. Cross-application tenure merge removed from those rows; private counts retained under an explicitly unverified legacy-scope column, not silently corrected.
- Operative detail/headline, feed labels and packet carry assessment qualifications. Packet's plain known count requires qualified exact whole-site evidence. Agent prompt and fingerprint carry the structured assessment, so a changed qualification cannot be silently ignored by agent identity.

## Actual verification and limits

Executed: 23 standard-library tests (9 threshold, 14 assessment), all passed, no skips. Python compilation of changed application/test/verification modules and shell syntax checks passed; these are not ORM/matching passes. Diff whitespace check passed.

Prepared but NOT executed: four new SQLite integration tests for same-record filter/detail/feed-facts/packet/CSV projection; both matching builders; independent count-versus-percentage handling; retirement exclusion. Existing 188 affected tests, 20 prior AH regressions and filter test have NOT been rerun for this checkpoint. Their old passes at 6d31f1e do not transfer here. Runtime Python and the primary runtime both lack pytest; SQLAlchemy import also fails. No installation attempts or substituted mocks.

The WSL runner preserves baseline c5b17a0ddb5a088502288bc58935ecc07ba05535 and existing 20-case group; adds separate spec020.xml expected to contain 27 cases (23 pure plus 4 ORM). Four bounded groups require the outer guard to be 1300 seconds instead of 950; individual groups retain 300-second limits. Empty/incomplete reports remain failures. Disposable SQLite and blocked-network/production-input guards unchanged. Same-record projection checks are not real browser-render or production CSV acceptance.

Expect existing assertions about unqualified raw count matching or packet KNOWN state to require assessment: record actual failures first, distinguish deliberate contract changes from defects, and do not edit assertions merely to turn green.

## Concrete provenance blocker — implementation is not complete

SchemeIntelligence has affordable_units_final, percentage, tenure text and classifier narrative/confidence. It does not persist count qualifier, explicit bounds, source document identity/date/passage linkage, verification state, or independently scoped tenure quantities. Document has a source URL and download time, but no claim link or authoritative document-date field. An application-to-document relationship alone does not establish which passage supports a particular count. Download/extraction time must not become document date.

Consequently no production row is promoted to a qualified estimate by this checkpoint. Qualified contracts work with explicit source-linked inputs, but there is no production claim acquisition/storage adapter. Named component lead routing beyond existing scope selection is also not complete. This intentionally blocks release: otherwise every legacy count would lose numeric-match eligibility without a way to qualify credible leads.

Smallest proposed follow-up for Product Owner review: one nullable structured AH claim payload attached to the existing application intelligence row, containing source-linked count and explicit tenure alternatives with scope keys, stage, source date and reviewed state. A bounded adapter would validate it and preserve legacy fallback; no automatic parsing/backfill, no historical overwrites, no model calls. Compare this with an explicit reviewed claim relation if review history must be independently auditable. No schema addition or writer is implemented or approved here. Do not use arbitrary prose parsing or a fabricated in-memory ORM attribute to hide this gap.

## Known remaining acceptance gaps

- Focus School: retain reported 72/82, disputed whole-scheme100/all_units and source narrative. No final legal classification chosen. Production claim linkage remains unresolved; not a verified numeric match.
- Confirmed-zero authoritative record, selected real CSV, actual cohort-specific buyer evaluations and source/decision/condition linkage remain unverified.
- Detail's legacy residential mix/tenure and dashboard compact metrics need actual rendering acceptance alongside the new operative qualification label. No claim of complete UI equivalence from projection tests.
- Production policy version usage and invalidation counts remain unmeasured. Available connector discovery exposes Render-hosted Postgres querying, not this Supabase database; no safe Supabase query route was established in this turn. Do not substitute the Render database tool or infer counts by multiplying sites and buyers.

## Version impact and release boundary

Global matching version remains 5. compute_buyer_mandate_fingerprint includes it; agent input hashes include mandate fingerprint and matching policy version. All otherwise-identical recomputed v4 mandate hashes differ under v5, including unrelated strategies. AH assessment semantics now additionally enter planning-delivery agent hashes. A changed hash is not a paid call: mandate recomputation is deterministic and explicit; run_persisted_evaluation is the separate possible future model-call boundary. No evaluations or histories refreshed.

Before release: establish deployed version and actual stored combinations, review any existing v5 semantics collision, execute WSL comparison and resolve candidate defects, approve a truthful claim-storage/source-linking approach, complete representative real-source and rendered/export acceptance. No release recommendation at this checkpoint. Rollback would be a separately approved return to an earlier executable; no migration or production data change needs reversal here. Parked discovery and P0-A Gate A remain unchanged.

## Subsequent failure repair

The a3fdbd6 WSL run failed 56 candidate cases against a clean 188-case baseline. That supersedes the dependency-free-only checkpoint above. See AH_SPEC020_FAILURE_REPAIR.md for individual dispositions, new local execution evidence boundaries and pending WSL comparison; see AH_PROVENANCE_STORAGE_PROPOSAL.md for the separate design-only storage follow-up. The original checkpoint is retained as history, not current acceptance.
