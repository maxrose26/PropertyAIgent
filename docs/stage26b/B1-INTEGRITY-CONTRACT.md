# B1 historical and successor dependency integrity

8 October 2026. Authority: Product Owner's bounded frozen dependency contract reconciliation. Offline only. This supersedes the source-pin blocker reported at `3607b245c8f346e6fd7184f00300551cdf7d4914`; it does not erase that report or claim production acceptance.

## Investigation: original contract

`test_v7c_frozen_v6_oracle` originated in `c3b7fc5cc942aa74d56b2bdc9d278287b342ea74` to prove the verbatim frozen v6 matcher could safely delegate to unchanged live helpers. Its dependency test whole-file-pinned five supporting modules, including scheme_reconciliation. `test_v8_frozen_v7_oracle` carried the same conservative dependency check into the v7/v8 transition, plus the later residual-work integrity assertion. The three failing checks therefore protected both provenance and live-dependency independence. They did not encode a product requirement that unsafe upstream count eligibility remain unchanged forever.

Both historical source commits, `3cce0815fd6d243993edf5ca511094ae3a795285` (v6) and `60dcbd99649d4d1e8506590257416ef7741e5939` (v7), contain exactly the same reconciliation file: SHA-256 `9eaafa1d502acc12be56a19a4b0d701c9ada132f778a842df547905eb5af62d1`. Verified directly from both Git objects. The exact bytes are retained in `tests/fixtures/stage26b/integrity/scheme_reconciliation.v6-v7.py.txt` with Git blob identity and both provenance commits in the manifest. This is historical evidence, not a replacement runtime module.

The matcher oracles accept already-qualified MatchingFacts. Raw reconciliation and fact-building adapters are upstream; they are not invoked to requalify those facts by assess_buyer_fit. The broader buyer_matching module does contain reconciliation imports for fact construction, so it would be incorrect to claim that the whole module depends only on constants. Existing definition pins and behavioural goldens remain important.

## Four independent gates

1. **Historical source:** original matcher modules, provenance, function hashes, dependency constants and checkpoint/golden files remain byte-identical. Original supporting hashes are not replaced. Historical reconciliation fixture must match that ORIGINAL hash and its Git blob identity.
2. **Current B1 dependency:** named `stage26b-b1-reconciliation-v1` manifest pins the reviewed B1 eligibility helper, changed reconciliation definitions, critical count/scope/supersession adapters and legacy fallback consumer definitions. Other original supporting modules retain their old live whole-file pins. The manifest itself is pinned and cannot silently change version or lose an entry.
3. **Qualified-input behaviour:** existing six-field v8, family, fingerprint and explanation differential tests remain independent. A new negative test makes raw reconciliation entry points raise, then calls frozen v6/v7 and current v8 with exact/approximate/range/unknown qualified facts for all buyers. Calls succeed without consulting the raw boundary.
4. **Corrected-evidence effects:** separate baseline-to-B1 probes retain raw evidence, source/hash/date provenance, eligibility decisions, full qualified input, assessments/explanations and actual synthetic universe/family/fingerprint differences. An additive expected-consequences fixture now locks membership, order, representative, classification and investigative flag per buyer. It is labelled synthetic and is not a rewritten policy benchmark.

Each former failing assertion now requires **historical AND live successor integrity** for reconciliation. It has not become an archived-source-only assertion. All other paths retain their original assertions. Test node names remain stable for traceability.

## Structural coverage and mutation resistance

The five intentional reconciliation definition changes are `_scheme_total_units`, `_portal_estimated_units`, `_contain_count_assessment` (new), `_resolve_approved_units` and `_build_active_position`. Current source hashes pin those reviewed definitions. All other reconciliation definitions remain semantically identical to the historical AST; comments/formatting outside pinned definitions need not be byte-identical. Duplicate/missing definitions, new module-level assignments/imports and changed decorators are rejected. This prevents a later rebinding or decorator from bypassing a function-body hash.

Legacy adapter changed definitions are pinned without freezing their entire source file. Module-level binding and decorator envelopes protect their execution bindings. The eligibility helper is small and wholly dedicated to this contract, so its entire source is pinned. Existing frozen CountAssessment source plus behavioural tests continue protecting unknown/approximation/range/hard bounds. Compatible aggregation, parent/phase containment and supersession are tested by existing phasing/reconciliation suites; no second count engine is introduced.

Mutation tests prove failure for altered historical bytes, manifest version, existing-stock eligibility, approved/proposed functions, portal fallback, legacy fallback, fact constant, late rebinding, unrelated reconciliation definition and decorator. Future intentional changes require an explicit successor contract review; historical hashes must never be updated to impersonate a new historical truth.

## B1 scope proof

No application code changes were made for this reconciliation task. Baseline8ec17e2 → B1 changes exactly four existing reconciliation functions and adds one; source inspection found no unrelated top-level delta. This turn changes tests, versioned verification fixtures, verification commands/probe detail and documentation only. Frozen matcher files, benchmark fixtures, matching policy/mandates, CountAssessment, phase/subject/family algorithms, AH modules, fingerprint algorithms and Stage1 security remain unchanged.

## Strawberry Hill conclusion

Conclusion **1: a necessary consequence of the existing material-parcel rule for these inputs**, not a B1 edit to subject-construction algorithms. `_phase_unit_count` previously supplied79; `is_material_development_parcel` accepted it against threshold10. After containment, no eligible count remains and the existing proposal fallback does not establish a residential parcel count. Existing `group_applications_by_operative_scope` therefore folds plot_A6 into the unphased scope.

The new subject remains UNKNOWN; it does not inherit parent housing quantum. The application is not deleted. Preserving the old key solely for continuity would require special handling that is not implemented. This demonstrates the behaviour of the current identity rule, not independent proof that no commercial parcel exists. The key replacement, representative/order changes and possible saved/monitoring effects remain release-significant and require separate transition approval. No production repair, identity migration or rebaseline is authorised.

## Publication and release gates

A clean offline candidate may be prepared for ordinary feature-branch publication and the two existing hosted jobs. This task does not merge, deploy or activate anything. Hosted verification and remote base reconciliation remain outstanding. REVIEW must separately accept corrected-evidence consequences and decide how to handle changed subject keys before production release. A code rollback must not silently restore misleading trusted counts; affected surfaces must remain withheld/closed until a safe version is restored.

B2–B5, data repair/backfill, source refresh execution, models, generated summaries, ranking and operational activation remain outside this work.
