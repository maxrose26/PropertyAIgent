# 022 — Stage 1 workflow coverage clarification

## Status and purpose

This is new documentation under the Product Owner's bounded authorisation. It does not reproduce the unavailable historical document or commit `6e4d3bc2738eb808ee008fba4446c92b47251140`. That artifact is superseded for publication due to unavailability; its clarification was accepted in intent.

## Workflow coverage

1. `.github/workflows/ah-web.yml` is a legacy, narrow AH web compatibility workflow. It is neither full Stage 1 acceptance nor full PropertyAIgent product acceptance.
2. Its existing `push`, `pull_request` and `workflow_dispatch` triggers remain unchanged by this documentation. This specification does not alter workflow execution or its guards.
3. Its tests preserve some broader behaviours, including aspects of selection/export identity and site/opportunity evidence, but do not establish comprehensive acquisition-intelligence coverage.
4. The five workflow-context tests concern the manual native PostgreSQL rehearsal. They do not establish full Stage 1 hosted compatibility.
5. Stage 1 publication evidence requires the complete exact-candidate renderer/verification pack (`verification/stage1-renderer-check.sh`) and independent review of the actual candidate and evidence.
6. Successful local authenticated verification, including preservation adapters, does not itself establish compatibility of the legacy AH hosted workflow entrypoint. That entrypoint requires separate compatibility evidence; this document claims no hosted execution result.

## Product and evidence boundaries

7. PropertyAIgent's core product outcome is buyer-specific acquisition intelligence. Affordable-housing and planning evidence are supporting evidence layers for that outcome.
8. Private-unit accuracy, comprehensive phasing, buyer ranking quality, mandate boundaries, maps/location evidence, HDT, land supply, current-use reasoning, NPPF reasoning and live-ingestion quality require separately scoped product evidence. Neither AH workflow results nor Stage 1 security acceptance alone establishes these qualities. This clarification introduces no Stage 2 implementation requirements.

## Candidate and release boundaries

9. Application commit `bbaca950d8b4567a1226fc5619e0aab863d182fb` (tree `477432c98677ef818a43876748e59057763fa06b`) has accepted LOCAL PASS evidence. That acceptance does not automatically transfer to this documentation descendant: the exact new candidate requires its own candidate-bound verification.
10. Original Git-history recovery remains blocked and is not pursued by this work. This new document and its forward commit do not recover, recreate or establish missing ancestry. Source archives and reports are not substitutes for original Git objects.
11. Branch publication, merge to master and production release are separate decisions requiring their respective evidence and explicit authority. Local verification or a branch-publication recommendation does not authorise any of those actions.
