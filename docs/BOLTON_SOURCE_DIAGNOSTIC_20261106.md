# Inactive Bolton source diagnostic

Stage 4 remains OPEN. This preparation follows Issue #212 and the project memory in #214. It does not authorise execution, deployment, access changes, settlement or stage advancement.

## Why this is the next bounded step

Independent review of PR #213 accepted its offline settlement path. The original retained Bolton proof has no recognised count or terminal marker; raw HTML was not retained. Seven rows cannot establish completeness, and the missing HTML prevents proving either a parser defect or the absence of an alternate signal. Another settlement framework would not resolve this collection blocker.

This diagnostic reuses WindowBoundary, strict form/sort handling and PrivateResponseBodies. It captures only FORM, SEARCH, SORT and REFINE for Bolton RECEIVED 3–5 November 2026. There is no PAGE, detail/document navigation, database, intake registration, screening or admission. No existing intake/private-body allowlist is broadened.

## Proposed execution, awaiting separate owner approval

Run the reviewed exact commit once on an existing authorised POSIX worker with a private writable directory. Do not deploy or restart intake to run it. Runtime availability and secure private-artifact access must be confirmed before any council request. If no existing route is available, return for a material execution-route decision rather than provisioning infrastructure.

From the repository root, with its existing pinned Python dependencies installed:

```bash
umask 077
private_dir=$(mktemp -d /tmp/bolton-source-20261106.XXXXXX)
python -m verification.discovery.bolton_diagnostic --private-directory "$private_dir" --observe
```

This is a proposal, not an instruction to execute now. `--observe` is explicit operational opt-in, not proof of owner approval. Never add it to cron or an automatic workflow. Record exact commit and run identifier with the private directory in the authorised private execution record. Do not publish the directory contents or raw HTML in GitHub, logs or chat.

Limits: four physical requests, zero retries, no redirect following, 45-second SIGALRM source deadline including blocking reads, 500,000 bytes per body and 2,000,000 total. This runtime requires POSIX main-thread execution with no existing alarm; it refuses other conditions. Each response is closed and the requests session is closed on return. Preserve partial private evidence on failure; do not retry automatically.

Expected success is FOUR_RESPONSES_RETAINED, not successful collection. SORT HTML is deliberately retained even when truncated or unrecognised; the report always says coverage NOT_ESTABLISHED. Matching REFINE criteria and all four successfully retained bodies are required before finishing the archive. Any new observation does not repair or establish completeness of the original run.

## Subsequent local inspection

```bash
python -m verification.discovery.bolton_diagnostic --private-directory "$private_dir"
```

Default mode makes no network requests. It checks private file permissions, sequence, bytes and hashes and publishes only counters/hashes. It checks archive integrity only, not the observation's scope or collection completeness. A reviewer then examines the private bodies through the authorised private route to determine whether a count and terminal signal exist, are unrecognised, absent, or remain unassessable. Only demonstrated evidence justifies a parser change.

## Validation and decision boundary

Synthetic transport tests cover exact operations/window, preservation of alternative and truncated HTML, privacy, failed retention stopping before further requests, wrong REFINE echo, tampering, timeout/no retry, no redirects, byte ceiling, PAGE/fifth-request refusal, signal restoration and session closure under timeout. The workflow runs offline tests only, with no production secrets. Fixture success does not establish council connectivity or production readiness.

Live execution remains NO-GO until owner approval and confirmation of an existing private execution/evidence route. No merge or deployment is required merely to review this proposal.
