# Specification 028 implementation and release gate

Date: 7 October 2026. Implementation authorised by the Product Owner; merge and production release require separate REVIEW decisions.

## Design and invariants

The implementation starts from documentation merge `29b5f2ca0e56b9342119e92e8b14b88632a0c17a`; application behaviour is compared with deployed v8 release `22636ddab7e0af9b6220c6466d400bc1ec98aafc`.

Existing matcher reason-emission sites record rule identifiers, semantic roles and decision contribution in request-local metadata. Existing precedence determines contribution. The original six-field assessment class definition and its serialised fields remain unchanged. No separate matcher, new policy predicate, schema, persistence or enrichment is introduced.

One shared presentation model separates positives, contributed classification causes, contextual limitations and investigation checks. Historical inputs without causal provenance remain partial or unavailable. Mandate-fit terminology does not verify acquisition availability, ownership/control or physical status.

Profile navigation carries an existing subject key and originating buyer key. The server resolves that key against the admitted active buyer's site-bounded subjects. It never substitutes a wider site or representative. Buyer switching clears navigation context; no private assessment cache is introduced. Four existing delivery queries are site-constrained for detail resolution; presentation of already-assessed cards performs no new database reads.

The existing policy remains v8. Family construction, representatives, membership, order, fingerprints and monitoring are not changed. AH qualification and Stage 1 security remain independent. Existing stored narrative and physical-status safeguards remain intact.

## Verification contract

- Run `bash verification/stage2/check.sh <test-python> <evidence-directory>` and `bash verification/web_ah/check.sh <test-python> <evidence-directory>` with their existing offline synthetic guards. These are selected acceptance/regression suites, not every repository test.
- The differential test archives the exact deployed Git baseline and compares 36,936 assessments across all four canonical buyers, ordered six-field outputs, serialization, mandate/evidence fingerprints and representative family outputs. Frozen v6/v7 expectations are not rewritten.
- Hosted offline CI explicitly fetches the immutable baseline and selects the new trace, differential, profile and presenter tests, alongside existing rendered journeys and security tests. Both hosted jobs must pass on the published candidate.
- `verification/spec028/check_browser.py --output <directory> --chromium <offline-chromium>` exercises actual shared renderers in a synthetic Streamlit host at 390, 768, 1366 and 1920 CSS pixels, with 1x/2x CSS zoom, keyboard expansion, related-subject expansion and real page-link navigation. Retain screenshots and ARIA snapshots. CSS zoom is an explicit browser-layout emulation; this host does not establish production authentication. Actual guarded application profiles and buyer switching are separately covered by AppTest.

## Proposed release and rollback procedure — not executed

Local verification completed on 7 October 2026: Stage 2 selected business suite 1,705 passed; Stage 1 security 211 passed; UI/profile/session journeys 23 passed; AH web suite 257 passed plus 10 subtests, with actual rendered CSV/walkthrough passing. Zero failures, errors or skips in these selected runs. The frozen differential and eight browser viewport/CSS-zoom combinations pass. Independent local review is GO; hosted publication and both exact-head CI results remain mandatory and are not claimed by this local record.

1. REVIEW approves an exact implementation head/tree after independent review, baseline integration history and both hosted jobs are verified. No merge or release follows from local passing tests alone.
2. Verify the separately authorised release SHA, production configuration pairing, existing closed-access controls and suspended cron states before deployment. Preserve existing secrets; do not retrieve or upload them for this presentation change.
3. Only with explicit production authority, deploy the approved web SHA through the existing release process. No schema migration, model call, rebaseline, re-onboarding, Gate B rerun or scheduled activation is required.
4. Check web health, owner-only admission, authorised buyer selection, same-subject dashboard/profile explanations, buyer switching, missing-context handling and existing AH independence. Compare classification/family/order invariants with retained release evidence; do not create ingestion workload.
5. Roll back the web release if startup/health, security, scope, causal explanation, classification or fingerprint invariants fail. Keep closed access throughout failure/rollback. Redeploy the last accepted application SHA `22636ddab7e0af9b6220c6466d400bc1ec98aafc` with its existing configuration; no data rollback is required because no writes or schema change are introduced.
6. Verify restored health/access and suspended crons before reopening access under the established release authority. Observe normal request errors and presentation latency without activating monitoring jobs.

## Deferred decisions

Targeted Stage 2.6 evidence validation may next be specified under separate REVIEW authority: prioritise missing source provenance, operative scope/version, physical status and ownership/control/availability evidence. Do not infer these from mandate fit. Stage 2.5C and commercial ranking remain paused until evidence-quality and buyer-validation acceptance criteria are separately approved and demonstrated. Stage 4 operational safety remains a prerequisite to any scheduled ingestion or monitoring activation.

Cross-agent Git bundles are exceptional recovery tooling. The implementation environment should publish its genuine feature history through supported authenticated Git transport. No credential, API commit reconstruction, deployment or operational activation is part of this implementation acceptance document.
