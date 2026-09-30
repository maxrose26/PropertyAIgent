# Specification 020 candidate repair review

Scope: repair of failed candidate a3fdbd6716e3ad167bd93ad88c8d5fa88147ef21, not release. Baseline remains c5b17a0ddb5a088502288bc58935ecc07ba05535. Matching policy remains 5. P0-A is untouched, Gate A remains open and discovery remains parked.

## Original evidence and construction defects

The uploaded WSL archive recorded candidate 152 passed / 36 failed, baseline 188 / 0, prior AH regressions 4 / 16, specification 020 23 / 4, no skips. Total candidate failures: 56. The archive and local checkout agree on the full candidate SHA.

42 failures originated in misplaced construction: 39 undefined `assessment`, 3 undefined `app`. `compute_percentage_reconciliation(scheme)` must use its supplied scheme only. `_position(scope_type, scope_label, app, fields)` now constructs its own legacy assessment using its actual application and scoped/override fields before building AffordablePosition. Single-application matching constructs its assessment from its own scheme, preserves application reference when available, and leaves unestablished scope unclear. Missing evidence gets an explicit unknown assessment. No ambient variables or invented provenance.

Four fingerprint failures came from one shared simulated packet used by four tests. That fixture now explicitly supplies AHAssessment. Production fingerprint access remains strict: a new test proves missing contract fields still fail and a source-qualification change changes the fingerprint.

## Individual review of the ten remaining matching failures

Names below are exact function names (all have the `test_` prefix). No existing assertion in these ten tests was removed or weakened. Eight fixtures now explicitly supply synthetic source-verified counts, matching the trusted-evidence premise their assertions were intended to test. Their old bare numbers remain unsupported under the new policy, tested separately for 0, 20, 48, 90 and 120.

| Test identity | Old expectation | Actual failed-candidate result | Specification 020 rule and cause | Resolution |
|---|---|---|---|---|
| test_buyer_matching::test_affordable_component_in_range_despite_total_exceeding_housing_association_max | A positive 120-AH scale reason despite 400 total homes | No positive AH scale reason | §§2–4 require qualified count evidence; intentional contract change, fixture lacked it | Explicit synthetic verified 120; retain original scale and other-buyer assertions |
| test_buyer_matching::test_below_affordable_minimum_is_not_suitable_for_housing_association | NOT_SUITABLE for trusted 20 against minimum 50, naming both | INSUFFICIENT_EVIDENCE | §§2–3 prohibit hard exclusion from an unsupported stored value; intentional contract change | Explicit synthetic verified 20; restore target/minimum detail in code explanation |
| test_buyer_matching::test_missing_affordable_evidence_is_insufficient_not_not_suitable_for_housing_association | INSUFFICIENT_EVIDENCE with explicit missing affordable-unit explanation | Same classification, expected explanation lost | §4 visible uncertainty; code explanation regression | Restore missing-count explanation alongside the shared assessment label; no assertion changes |
| test_buyer_matching::test_elton_reservoir_produces_materially_different_conclusions_per_buyer | HA remains insufficient, no invented AH estimate, missing-count reason | Classifications held; missing-count reason lost | §§2,4 do not manufacture allocation AH; code explanation regression | Same wording repair; no policy or fixture changes |
| test_buyer_mandate_v2_phase_b2::test_affordable_containing_scheme_matches_affordable_housing_package | Positive package relevance without availability claim | No package match | §§2,4 qualified count required; intentional contract change; replacement wording also omitted named strategy | Explicit synthetic verified 90; code names package relevance and retains nonavailability wording |
| test_buyer_mandate_v2_phase_b2::test_one_opportunity_compatible_with_multiple_acquisition_types | Same scheme supports distinct acquisition-type reasons | Land and AH match lists identical | §4 unsupported count cannot establish package relevance; intentional contract change | Explicit synthetic verified 90; preserve every original assertion |
| test_buyer_mandate_v2_phase_b2::test_affordable_housing_package_hard_mismatch_only_on_trusted_zero | NOT_SUITABLE for trusted zero | INSUFFICIENT_EVIDENCE | §§2–3 verified whole-scheme exact zero differs from unverified zero; intentional contract change | Explicit synthetic verified whole-scheme zero; raw-zero companion stays unknown/investigative |
| test_buyer_mandate_v2_phase_b2::test_explicit_housing_association_below_minimum_hard_exclusion_unaffected | NOT_SUITABLE and below-minimum reason | INSUFFICIENT_EVIDENCE | §§2–3 hard rejection needs qualified count; intentional contract change | Explicit synthetic verified 20; retain exclusion assertion and restore useful reason |
| test_buyer_mandate_v2_phase_b2::test_housing_association_b2_behaviour_developer_led_mixed_tenure | STRONG_FIT; developer-led/underway accepted, package availability not asserted | INSUFFICIENT_EVIDENCE | §4 count must be independently qualified; intentional contract change | Explicit synthetic verified 90; all original buyer-specific assertions retained |
| test_buyer_mandate_v2_phase_b2::test_same_facts_different_mandates_produce_materially_different_b2_reasoning | HA STRONG_FIT with distinct mandate reasoning | HA INSUFFICIENT_EVIDENCE | §4 qualified count relevance distinct from other mandate criteria; intentional contract change | Explicit synthetic verified 90; original four-buyer assertions retained |

The test helper is in tests only, uses example.invalid and synthetic passages, and is applied at eight explicit call sites. It does not upgrade `_facts()` globally, patch storage, claim real-source verification, or qualify production records.

## Additional defects and expectations exposed after construction repair

The first executable broad local run after repair reached all four original spec020 integration assertions: 208 passed, four failed across the selected 212 cases. The remaining four were parameter variants of `test_packet_uses_one_current_position_not_first_historical_status`. They expected unverified counts as plain KNOWN packet values. Under §4 these stay UNKNOWN; the selected application's exact reported count, reference and reported stage are retained in the explicit assessment. Tests now assert both halves, including raw zero and rejection of stale caller count 400. Percentage, status and denominator assertions remain.

Legacy direct MatchingFacts callers previously lost their reported value from reasoning when no assessment was supplied. They now retain it as unknown/unverified, never source-qualified. Buyers dependent on AH get investigation visibility for valid reported counts, not a numeric match. The existing feed's exception bucket is reused; no new recommendation taxonomy or generic bands. Completely missing counts stay unknown. Independent retirement/specialist exclusions still win.

Package relevance now uses threshold outcome rather than source verification state to distinguish exact versus likely matches: a verified source describing a range is still a range, not an exact count. A dedicated test prevents that range alone establishing STRONG_FIT on an essential package requirement.

## Verification and handoff boundary

Added/strengthened tests exercise the original four integrations, both builders with and without an application relationship, supplied overrides versus unchanged stored values, legacy versus verified counts, actual buyer-feed selection, minimum/maximum 44/45/50/55/56, range qualification, and strict fingerprint contract. Spec020 group is now 38 tests; prior AH group remains 20 and existing candidate/baseline groups remain 188 each. The summary completeness guard checks those exact counts.

Local tests run in a clean environment with temporary HOME, in-memory SQLite, plugin autoload disabled and a Linux seccomp filter denying socket creation and network send/connect syscalls. The launcher verifies network denial before importing tests. This is separate local evidence, not execution of WSL's mount/network namespace runner. Dependency versions and JUnit outputs are recorded with the exact committed SHA in the handoff evidence archive.

This environment cannot execute the user's WSL machine; local `unshare --net` returns Operation not permitted. The unchanged isolation guards in ah-wsl-run.sh are not bypassed. A fresh exact-commit bundle is prepared; WSL execution and review of its returned archive remain pending. Do not rerun a3fdbd6.

## Release

No release recommendation. See AH_PROVENANCE_STORAGE_PROPOSAL.md. No schema/storage writer, production change, evaluation refresh, paid call, push, merge or deployment. Source-linked real-record acceptance, rendered/export acceptance, named-component routing and measured deployed-version/invalidation impact remain open. A green synthetic suite cannot settle Focus School's legal position.
