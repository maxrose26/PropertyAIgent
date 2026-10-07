# Stored mandate correction (mandate sync) and the v7 production transition sequence

Status: **SPECIFICATION + OFFLINE IMPLEMENTATION.** Built and tested offline only. No production execution, no production launch scope, no production read or write is authorised by this document.

Related: `025-stage2-5b-acquisition-subject-decomposition.md`, `026-gate-b-production-discovery-validation.md`, `app/policy/mandate_sync.py`, `scripts/sync_nesten_mandate.py`.

## Why

Gate B1 evaluated Nesten with the **stored** mandate (preferred 50–100, discovery 45–110). The accepted canonical Nesten brief (commit `f8e1c9b61f6d2624d60959dc62a41cc4ddd8d20e`) is preferred 50–200 (discovery 45–220), with no wholly-affordable exclusion. That commit changed the code **template** only ("no production row change"); no code path ever updated an existing stored mandate's rule fields. This is stored-configuration drift, not a matching regression, and neither re-onboarding nor reseeding can fix it.

## Five things that must never be conflated

| # | Concept | Owner | Changes rule fields? |
|---|---|---|---|
| 1 | **Canonical buyer template** — the product-approved intended strategy (`app/policy/buyer_profiles.py`) | code, reviewed | is a seed/default only |
| 2 | **Stored buyer mandate** — the `BuyerMandate` row matching actually uses | database | only by an explicit sync |
| 3 | **Mandate sync / correction** — an explicit, Product Owner-approved update of named rule fields of one mandate | `mandate_sync` | **yes, only the approved fields** |
| 4 | **Re-onboarding** — recompute and stamp the baseline (fingerprint, time, summary) from the stored mandate under the current policy | `mandate_reonboarding` | **never** |
| 5 | **Buyer matching policy version** — the deterministic matching semantics (v7) | `BUYER_MATCHING_POLICY_VERSION` | n/a |

## The Nesten correction, reconstructed from git history

From `f8e1c9b^` to `f8e1c9b` (`git diff` of `app/policy/buyer_profiles.py`), exactly three fields of the `NESTEN_HOMES` template changed:

| Field | Old (stored in production) | Approved |
|---|---|---|
| `target_unit_max` | 100 | 200 |
| `wholly_affordable_is_exclusion` | true | false |
| `notes` | the original three-sentence brief | the same text **extended** with the real Nesten Land Requirements (the real brief; site size, region, infrastructure and JV recorded as investigation context, not rules) |

`target_unit_min` stays 50. Discovery is derived (`discovery_bounds`): 45–110 → 45–220. Whole-policy sha256 (the full form of the Gate B digest): old `cc45186babbf1043a7d3319e1dc1d043ba31e56b4c40c2ccabf827442a31d607`, approved `ee54c5eae327b3eb2f0235ce0e7a00cc47402ba409ed925e2c9addb1835068f1`. The old digest's prefix equals the digest recorded in the production Gate B1 artifact for the stored Nesten mandate, so the expected pre-correction state is pinned to what production demonstrably held.

## Scope of the sync

Not a generic "overwrite from defaults". The only authorised correction is `APPROVED_CHANGES["nesten_homes"]`. **Syncable rule fields** (the only columns the mechanism may ever write): the canonical-template rule/brief columns (`primary_requirement`, scale min/max/metric, accepted planning states, the four behavioural flags, `notes`, the five B1 structural fields). **Preserved instance/operational fields** (never written): `id`, `buyer_id`, `mandate_key`, `display_name`, `status`, `source_template_key`, the whole onboarding baseline (`matching_fingerprint`, `onboarding_completed_at`, `onboarding_summary`), `created_at`. For Nesten only `target_unit_max`, `wholly_affordable_is_exclusion` and `notes` are approved; any other difference between the stored row and the template is **refused**, not synced.

## Dry run (default) and the plan

Selects only. The report is deterministic and non-secret: the field-level diff (`field`, `old`, `proposed`, `reason`), identities (buyer, mandate, workspace), the expected-old / stored / proposed whole-policy digests, the matching policy version, derived discovery before/after, and the baseline staleness before and after the correction. `status` is READY, ALREADY_CORRECTED, DRIFT, TARGET_NOT_APPROVED or MANDATE_NOT_FOUND. The `plan_digest` binds identities, policy version, expected and stored and proposed digests and the diff.

## Apply

Stage 1 operator command check (`@command('buyer.write')`), the exact confirm phrase, the digest of the **reviewed** plan, and READY status (stored state == the expected old state, resulting state == the pinned approved state). One transaction: the row is re-read under a row lock and re-verified, only the approved columns are written, one commit; any failure rolls back. (The row's automatic `updated_at` stamp changes with the write; that is the ORM audit stamp, not a preserved field.) A changed stored mandate between review and apply refuses. Nesten is the only target; applying the reviewed Nesten plan to any other buyer refuses. The command does **not** re-onboard, run monitoring, reseed, call a model, scrape or alert.

## Baseline after correction: recommendation A

The onboarding baseline is **left in place and becomes stale by computation** (the stored fingerprint no longer equals the fingerprint of the corrected rules; `is_buyer_mandate_baseline_stale` becomes true). Rejected alternative B (clearing the baseline columns): it destroys the record of when the mandate was last reviewed, conflates "corrected" with "never onboarded", and adds a second write with no benefit — staleness is already derived, never a flag. No mixed state exists: the baseline is untouched and stale until the separate V7C re-onboarding restamps it.

## Plot decision (Product Owner)

A material plot may be a valid acquisition subject. A plot does **not**, merely by existing, establish `CURRENT_EVIDENCED_PHASE` or any qualified acquisition-phasing evidence (plot subject ≠ qualified phasing evidence) unless later qualified documentary evidence establishes the phased-delivery fact. The phasing derivation is unchanged; Stage 2.6 may later qualify documentary plot/phase relationships. Pinned by a test.

## Updated production transition sequence

Proposed by REVIEW (steps 0–13) with corrections:

0. Scheduled paths suspended (weekly sync, processing, rebuild, scrape crons stay suspended, Auto-Deploy off).
1. **Correction:** the DB-side tools (mandate sync, re-onboarding, previews, Gate B) run from the Product Owner machine against the production DB from a clean checkout of the exact merged SHA, so they need **no web deploy**. The web service is not deployed or reopened until step 12.
2. Read-only transition previews (ordinary monitoring sync preview).
3. Nesten mandate-sync **dry run**.
4. Product Owner reviews the exact field diff.
5. Separately authorised Nesten mandate-sync **apply** (needs a production grant of `launch:sync_nesten_mandate` and the `buyer.write` action for the machine identity; not granted by this gate).
6. Prove the Nesten baseline is stale (the apply report carries `verified_after.baseline_stale`).
7. **Challenge — Gate B rerun here, before re-onboarding:** the rerun reads the stored mandate and does not depend on the onboarding baseline, so it can validate the corrected production state immediately. Doing it before step 8 means that if the commercial result shows a further mandate problem, no baseline has yet been stamped under a wrong mandate (otherwise another correction forces another re-onboarding cycle). REVIEW may keep the original order (rerun after re-onboarding); both are safe, this one is cheaper to recover from.
8. V7C re-onboarding **dry run** (all stale mandates; same-universe v6/v7 parity).
9. Separately authorised re-onboarding **apply** (parity PASSED, digest-bound).
10. (If not done at 7) Gate B rerun against the actual corrected production mandate; exactly one rerun.
11. Benchmark / release verification.
12. Product Owner deployment and reopen decision.
13. Cron activation remains a separate decision.

Every production step needs its own explicit Product Owner authority; none is implied by this specification.

## Gate B1 evidence record (preserved, not rewritten)

The first Gate B artifact (`gate_b_validation_e0f37b10_20261007T093336Z.json`, sha256 `8de026513e23e60787685b4a1529c66a5e808008c61da6ddf0f398eab5c08786`; `.csv`, sha256 `e2fc38a3ea0193586bb60bde75275f1ac028dd2098c70f011aaea5c299e9bbcf`) is recorded as **TECHNICALLY VALID, BUT NESTEN COMMERCIAL RESULTS INVALID DUE TO THE STALE STORED MANDATE**. Preserved as valid: the phasing population, database efficiency, the other three buyers' results (their stored mandates equal the current templates), the Site 371 decomposition example, and the Stage 2.6 evidence-gap indicators. Not valid: Nesten's fit population, shortlist and order, oversized counts, and the 16 not-suitable.
