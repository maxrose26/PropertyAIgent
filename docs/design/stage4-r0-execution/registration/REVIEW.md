# R0 two-workflow registration — execution still requires confirmation

Master Stage4 OPEN. This document supersedes proposal-only/UNREGISTERED wording about registration status once this registration PR is integrated. Approved template comments are intentionally unchanged to preserve exact bytes; comments do not confer execution authority.

PR95 reviewed head0d14d47df9be96c4ff5a6459dc8fdb8dd6049710 was integrated at184798f2ba452c5935eaef0e538e88f027358b75, preserving reviewed tree56c8fe2db29d318a8599379809410499b503aeb2. All eight exact-head checks passed. No implementation/source/evidence/route/persistence changes belong to this registration change. Historical workflows and manifests remain unchanged.

## Registrations

| Destination | Exact reviewed template SHA256 | Git blob |
|---|---|---|
| .github/workflows/stage4-r0-identity-comparison-once.yml | e69dce37d39310549c376e976325daf0f7725e924e387f29e220fd1253c9a7c2 | df8c93fcf1cbcef7f56876f597e8e995150bd81a |
| .github/workflows/stage4-r0-untouched-recovery-once.yml | 9a7d50267abe60c11113d9edcf20e062f41e1f83a58760679924e09688f2e4bc | 7eeb078194c58fbc6789dd883f2f537057336c5e |

Exact template byte equivalence is asserted. Neither workflow has run under this registration instruction. Final master/tree, hosted checks and execution-history readback are supplied in the registration PR description and final REVIEW handoff, not guessed from the draft revision.

## Separate proposed execution inputs

Both use ref master and reviewed_sha equal to the final verified registered master revision — never a draft candidate SHA. These input sets are preparation only, not execution authority.

Comparison: workflow stage4-r0-identity-comparison-once.yml; manifest_sha cf31d3a5dd69da7c65348428473a0bb15cf38071caab41b5db76b6d5ea8845cd; authority AUTHORISE_R0_FIXED_80_IDENTITY_COMPARISON_ONCE. Exactly80 identities Bolton54/Bury26, all five final Bury references preserved. Existing stage4-production-canary and secrets.DATABASE_URL used in place. Exact-route validator, explicit verified BEGIN READ ONLY, statement15s/lock2s/idle20s timeouts, LIMIT2/exact predicates, rollback,160 maximum matching identity rows,100KB output,60s outer timeout+5s kill,5min job. No source/admission/B2 capability. Database absence remains UNPROVEN until this separately confirmed execution returns evidence.

Recovery: workflow stage4-r0-untouched-recovery-once.yml; manifest_sha 5e4170c781314ba76583682e39ef0072ec932926617f3be169316873485ee9ae; authority AUTHORISE_SEVEN_COUNCIL_R0_UNTOUCHED_WINDOW_RECOVERY_ONCE. Exactly28 original NOT_ATTEMPTED windows,17September–14October2026 inclusive, excluding Bolton/Bury.28calls/1120requests/299658240bytes/1900s/20MB; existing hard supervisor launches new recovery entrypoint/exact manifest,1930s shell timeout+10s kill,38min job. No protected environment/secret or database capability. Credential-free workers unchanged. Safe gaps remain UNKNOWN; security/identity/cleanup/accounting/unclassified failures stop. Parent R0 remains INCOMPLETE because Bury remains unresolved. No historical R0 resume.

Run1/attempt1 only for each new workflow, manual/master/exact workflow SHA/revision/manifest/authority checks, no arbitrary inputs, no automatic retry or resume. Before future dispatch recheck current master and complete execution history: an existing run must be inspected rather than duplicated. The consumed original R0 run38731487848 stays closed. No execution is authorised by registration alone.

## Tests and independent review

Registration tests pin exact content and semantic controls, byte equivalence, actual comparison secret-step mapping, actual recovery parent mappings, wrong/missing workflow SHA, wrong revision/manifest/authority and repeated run/attempt rejection. Existing offline entrypoint tests prove new recovery worker delegation and exact manifest under hard supervision. Mutation tests reject destination, environment/secret, deadline, worker, workflow SHA and checkout changes.

Oldham/batch environment allowlist changes admit only the exact content-pinned comparison workflow/job; all other exclusions remain. Recovery gains no environment exception. Both offline CI workflows include exact new workflow/test path triggers and invoke the new registration suite. No assertion was removed without equivalent stricter protection.

Independent registration review PASS. Reviewer independently ran76 network-denied registration/executable/Oldham/batch tests. Local combined affected suite139passed. Exact-head and post-merge checks must pass before readiness is returned. No live source/database or manual dispatch was used to test registration. Existing disposable PostgreSQL checks retain synthetic-only credentials and environment.

## Independent assessment freeze and residuals

Accepted bounded method remains executable-proposals/INDEPENDENT-PLAN.md (SHA25687f0add587ab6066cc9630bbec13cb78e2fd50c37588c2eb7a330c0a5fb8967d). Freeze assessor and primary session IDs, code/config/rule/manifest/method hashes and row ordering before observation. Separate blinded enumeration; record observation start/end, seal hash/time and subsequent reveal time. Seal before primary reference-output disclosure. No denominator is derived from primary output.

Manchester's proposed public-results entry remains explicitly unproven, with one-navigation feasibility condition and visible applied-criteria verification. If unavailable, retain UNKNOWN/NOT_ATTEMPTED and no alternate-route investigation loop. Other unavailable denominators remain explicit. Proposed independent caps28windows/168segments/1680refs/280navigation actions/90min, separate accounting; unmeasured browser network requests/bytes remain UNKNOWN. No observation begins in this instruction.

Bury stays UNKNOWN without further investigation. All83 overlap records remain context. Publication recall and unsupported latency remain UNKNOWN;15October onward is the explicit bridge. No production read/write/admission, source observation, model, scheduling, deployment, prospective acceptance or stage advancement occurs in registration. Final execution confirmation must bind exact registered master identities separately for the two scopes.
