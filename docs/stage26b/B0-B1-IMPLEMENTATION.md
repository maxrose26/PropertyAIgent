# Stage 2.6B B0+B1 offline implementation

Date: 8 October 2026. Authority: Product Owner B0+B1 offline implementation instruction; Specification 029. Base: `8ec17e22e476209a88a1c162fb4b41a896a1af9e`. No live-source, remote-master or production-state claim is made.

## Evidence contract and reproduction

`tests/fixtures/stage26b/` is an additive evaluation dataset, not a policy benchmark. `case-index.json` preserves the 25-case qualified audit observations, six demonstrated scale/scope discrepancies and five unresolved cases. `sample-context.json` preserves 25 families/32 subjects as dated presentation observations, not ground truth. `retained-cases.json` contains nine minimal source-proposal/stored-intelligence wrappers, with reference, source URL, observation time, retained snapshot SHA-256 and audit-pack checksum. The immutable audit ZIP checksum was verified as `25c765339320d71e1892c88d67aaa93f98ada92f4080174c291f6685b73f724d`.

These wrappers combine dated public proposal descriptions with stored intelligence observations. The audit did NOT export each stored proposal, full extraction inputs, historic model response or all historic document versions. Consequently these are evidence-backed containment acceptance cases, not a replay proving production impact or original extraction fault. Synthetic granted/pending variants test both paths without upgrading the actual application's status. The full-pipeline probe deliberately normalises dates/status to exercise detectors and uses synthetic Stockport geography. Do not present its results as current production buyer results.

No full document bodies, contact/address records, private buyer records or credentials are retained. Public proposal fragments are limited to evidence needed for metric/scope evaluation. Source rights remain with the originating authority; original documents are not republished.

## Reproducible layer trace

Common code path: application proposal/source context → `housing_mix.extract_housing_mix` / `reconcile.reconcile_scheme` (historical inputs UNRESOLVED) → stored `SchemeIntelligence.total_units_final` → existing `resolve_applications` / phase grouping → `_resolve_approved_units` or `_build_active_position` → eligibility guard → existing `CountAssessment` → matcher/reporting/profile/export adapters.

Code inspection establishes that reconciliation can prioritise classifier `total_units_context` over housing-mix/portal totals. This is a possible route, not proof that a specific historic value came from the classifier. No extraction implementation changed. The before/after probes reproduce the downstream consumer behaviour with the retained wrappers.

| Case / site / app | Source and stored observation | Origin / relationship limitation | B1 treatment and downstream trace |
|---|---|---|---|
| World of Pets /248/578 | Dated RM proposal76; stored final116 | Exact historic116 source/version and operative supersession UNRESOLVED | Contradictory single current-scope claim withheld; neither portal76 nor text fallback repairs it. UNKNOWN until separately qualified current RM evidence supports replacement. |
| Stand Golf /16/18 | Proposal43 general homes +60 retirement apartments; stored total60 | Where component became total UNRESOLVED; no independently acquired package established | Component cannot stand for whole. Raw60 retained; separately scoped60 retirement subject remains eligible. No auto-total103 or private103 created. |
| Woodford /62/186 | Bridge/crossing RM; stored372 | Parent context/source of372 UNRESOLVED; other Woodford subjects remain separate | Current ancillary subject cannot claim parent dwelling scale. UNKNOWN; parent/legitimate phase evidence unchanged. |
| Walthew /336/526 | Commercial B2/B8 building; stored47 | Numeric origin47 UNRESOLVED | Non-residential claim cannot qualify new homes. UNKNOWN, not zero. |
| Strawberry Hill /371/552 | Acoustics building PlotA6; stored79 | Original79 and parent933 relationship/source not reconstructed | Non-residential count withheld. Existing material-parcel grouping changes plot_A6 to unphased in synthetic full feed; explicitly reported, not hidden as invariant. |
| Cedar Avenue /508/1100 | Replacement porches to56 existing dwellings; stored56 | Initial action/metric confusion layer UNRESOLVED | Existing dwellings affected are not new dwellings. UNKNOWN; no claim there are zero homes. |
| Bamford /215/296 |49 apartments+18 bungalows; stored final67, partial raw49 | Raw-to-final successful sum consistent with source; exact historical processing trace UNRESOLVED |67 preserved, compatible additive components remain valid. |
| Failsworth /28/42 | Stored pending; current refusal25September2026 | Freshness discrepancy demonstrated, invocation/parser cause not established |68 scale positive control unchanged. No B2 status repair or refresh run. |
| Southlink /25/29 |147 proposed; portal pending; Social Rent versus stored affordable rent | Historic tenure source/model trace UNRESOLVED; committee resolution not permission/S106 |147 scale positive control unchanged. No tenure, secured-status or denominator repair. |

Exact source identifiers/hashes/dates and unresolved observations are in the fixture index. No source verification timestamp is replaced with test time.

## Architecture and containment

One small request-local exclusion guard in `residential_count_eligibility.py` qualifies the existing count pipeline. It never supplies a new count. It uses only the exact application's already-loaded proposal and claim; no database query, network, extraction, model, persistence or generic evidence engine. The frozen `residential_count.py`, matching policy/mandates, identity algorithms, AH modules and security modules remain byte-identical to the base.

Affirmative contradictions are withheld: existing-stock works, ancillary bridges, commercial/non-residential quantities, component masquerading as whole, and a single incompatible proposal quantity. An affirmative dwelling-creation/conversion clause prevents incidental bridge/commercial/porch context from suppressing real housing. Only explicit additive links establish component rejection; “including” and historical variation alternatives are not added. Parent citations cannot donate housing creation to an ancillary proposal. No numeric correction is inferred.

Both approved and active positions share the guard. Same-source portal/legacy fallback cannot rescue a rejected SI claim with a different number. Independently supported eligible peers remain usable; source-local rejection does not poison them. Existing phase/parent relationships, supersession eligibility, range/approximation and non-overlap aggregation remain responsible for their current contracts. An unrecognized or absent proposal is NOT independently verified: this bounded guard does not promise to catch every unsafe stored value.

Legacy scalar consumers (dashboard fallback, common aggregation, entity search, allocation report/discovery) use the same gate. AH raw fields and AH adapters are not repaired. Identity construction is untouched, but eligibility can affect existing material-parcel membership: see the full differential, especially Strawberry Hill. No saved/monitored identity migration is attempted.

## Verification and differential boundaries

Run the two Specification029 workflow scripts locally under their existing syscall network guards. `verification/stage26b/check.sh` runs the focused dataset/differential and supplementary relevant suites. These are SELECTED regression suites, not every repository test. Existing refresh tests use mock model clients under the existing explicit synthetic positive-command plugin; they perform no actual model/network call. The normal security suite runs separately without that positive adapter.

`test_spec028_differential` checks identical qualified inputs against immutable deployed v8 objects across all six established assessment fields, mandate/evidence fingerprints and family logic. The B1 differential is separate: same raw wrapper before/after, qualified scale, all four buyer assessments, causal explanations and fixed synthetic family effects. The second probe exercises actual SQLite detectors/feed/families and the complete opportunity fingerprint builder, including a parent, legitimate child and ineligible ancillary child. It records membership, representatives, ordering, exclusion, full fingerprint values and query counts. No production rebaseline or prediction is implied.

Actual Streamlit dashboard/profile and related expansion render contained UNKNOWN scale; existing responsive/accessibility contracts are preserved and tested through the accepted journey/render suites. The count-export columns are serialized through the real CSV safety adapter. AppTest verifies widget labels and rendering, not a manual screen-reader or physical viewport certification. No CSS/layout changes are made.

## Release and rollback limits

This is an offline candidate only. Hosted CI is extended but not executed remotely in this instruction. Separate review must accept the evidence-driven buyer/family/fingerprint changes before publication/release. In particular, Strawberry's existing grouping can change a logical key, with possible future saved/monitoring consequences. A production transition decision is required; no frozen benchmark, monitoring baseline or stored row is rewritten to conceal it.

No schema/migration/backfill is required. A rollback to the old code would restore unsafe count eligibility; therefore rollback must keep affected trusted surfaces closed/withheld until the containment candidate or a reviewed repair is restored. Do not call unrestricted old-code rollback safe. No operational activation, cron, deployment or production data repair is authorised.

Next recommended slice is B2 freshness/provenance specification implementation, only after separate approval. Its source-refresh execution remains independently gated; Failsworth is a retained dated discrepancy, not authority to start ingestion. B3 AH, B4 typology, B5 deadlines, summaries and ranking remain deferred.
