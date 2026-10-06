# Stage 2.5 acceptance (preflight + Stage 2.5A)

Contract: `specifications/024-stage2-5-buyer-discovery-and-opportunity-decomposition.md`.

## Identity and authority

- Branch: `stage2.5/opportunity-decomposition` (created from master `ee8fd78a3f26e9bf3ee7a3e2068dcf57591bbaef`).
- Accepted code head: `b0001c7e40e24a8a09e2e05b79643c8b0415db96`,
  tree `8a84e8742de27f8e2629f209a752e56ea0673faf`.
- Accepted by REVIEW. **Not merged to master. Not deployed.** Stage 1 production
  readiness remains separately gated.
- Execution environment: GitHub-hosted Actions (mandatory). No local test execution
  is claimed; local review was static only.

## Accepted commit chain

| Commit | Content |
|---|---|
| `73f2581` | Gate 1 — safe phase aggregation |
| `c312529`, `86cc7c1` | Gate 2 / 2H — residual planning-capacity primitive and hardening |
| `508dc33` | Gate 3 — operative supporting-source preference |
| `fba099b` | Gate 5B — evidence-aware completion filtering |
| `de1731d`, `9691c47`, `0c81df4` | Stage 2.5A — discovery envelope, POSSIBLE_FIT, policy v6; feed import fix; acceptance fixtures |
| `48cebff` | Hosted coverage: `tests/test_buyer_matching.py`, `tests/test_buyer_mandate_v2_phase_b2.py` added to the offline Stage 2 job |
| `1463e3b`, `b0001c7` | v6 hardening — N1-B affordable percentage non-blocking, N2-B approximate development-type corroboration, builder docstring; N2 fixture fix |

Gate 4 (fingerprint/monitoring transition review) required no code.

## Final accepted hosted evidence

Run `37430072540`, attempt 1, head `b0001c7`, both jobs success:

| Suite | Result |
|---|---|
| Stage 2 (commercial evidence 77, unit phasing 167, buyer matching 25, Buyer Mandate V2 phase B2 76) | 345 passed |
| Stage 1 security | 199 passed |
| Journey / profile | 10 passed |
| AH | 257 passed + 10 subtests |
| Rendered CSV walkthrough | PASS |

Zero failures, errors or skips. All 21 N1/N2 cases and every Stage 2.5A, Gate 3 and
Gate 5B test passed by name in JUnit.

## Earlier intermediate runs (not acceptance evidence)

- `37368234996` attempts 1–2: no hosted runner assigned (GitHub incident); attempt 3 passed Gate 3.
- `37381137115` (`de1731d`): collection ImportError — POSSIBLE_FIT imported from the wrong module; fixed in `9691c47`.
- `37381771730` (`9691c47`): 2 failures — an over-strong `test_k_l` expectation and a feed fixture missing `opportunity_type`; reconciled in `0c81df4`.
- `37385202652` (`1463e3b`): 1 failure — the N2 input-order test inserted duplicate application references; fixed in `b0001c7`.
- `37382357041` (`0c81df4`) and `37382579314` (`48cebff`) passed and preceded the final hardening.

## Pending release / operational work (NOT performed)

- reviewed v4→v6 Agent Evaluation Benchmark rebaseline (fixtures unchanged);
- monitoring-transition dry run and reviewed `rebaseline_ids` for Category A (Gate 3)
  and Category B (N2-B) development-type derivation drift;
- v6 buyer-mandate re-onboarding;
- production deployment and recomputation, only under separate authority.

## Carry-forward register (record only — not implementation work)

1. Stage 2.5B acquisition-subject decomposition.
2. Canonical 500-home outline / 125-home RM decomposition.
3. Residual-capacity opportunity interpretation.
4. Buyer-configurable discovery tolerance.
5. Asymmetric discovery ranges.
6. Qualified affordable-percentage evidence (Stage 2.6).
7. Broader real-world evidence validation (Stage 2.6).
8. General count-variance policy beyond the accepted 100/101/102 case (Stage 2.6).
9. Richer physical-status evidence (Stage 2.6).
10. Additional buyer archetypes such as an SFH investor — separate product scope.
11. v4→v6 benchmark rebaseline.
12. Category A + B monitoring rebaseline.
13. v6 mandate re-onboarding.
14. Gate 3 R2: diagnostic visibility for missing development type, where still relevant.
15. Gate 3 R3: buyer-matching / site-profile consumer parity coverage, where next relevant.
16. Gate 2/2H: consumers must not use diagnostic `subtracted_children` of withheld results for unofficial arithmetic.
17. N2-B `provenance_reference` is computed but not yet consumed.
18. Cosmetic: some v5-era test names in the newly hosted suites no longer match their v6 assertions.
