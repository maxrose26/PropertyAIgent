# Verified checkpoint read and inactive runtime inputs

17 November 2026, 17:18:33–17:18:35 UTC. Stage 4 OPEN.
The exact v1.5 approval is consumed. v1.4 remains consumed; v1.3 fenced.
No recovery, installation, deployment, stop clearance or collection occurred.

## Receipt and approval

Owner approval: Issue #214/6955392174, linked before dispatch in #227/6955418780.
Live receipt: #227/6955473758. Exact launcher revision 07dab22a74d0ffdcb70cd7eb14ef6f0fd986e679 and SHA e0d6837dde8a6ac9cc2d2beb1e032af019411ad9df101dd31c4aaf117c6c5a71.

The hourly worker completed at 17:09:56.537214Z and its checkpoint recorded no
competing dispatch. Before launch the actual hostname/service/deployment/cwd
matched the proposal, invocation directory and launcher were absent, and a
bounded /proc command-line match found no checkpoint/Bolton/owner/release-candidate
process. This is the observed local process scope, not an assertion of global
absence of all possible actors. Exclusive invocation and worker claims remained
in force. The single launch produced its ACK; a browser reconnect to the same
instance was followed by the separate receipt-read command, not another launch.

`checkpoint-v1-5-receipt.json` is the allowlisted result captured from the pinned
readback. Its ACK and completion objects were independently canonicalised locally
and BOTH hashes exactly match the returned hashes, preventing transcription drift:

- ACK: 0d0740eadd4292e9067e52a0aaea327b14da850a412189680379a5e55635e7d6
- Completion: 8675b698b6f3eed8a9927095f23155b560b1c2ac050a09355f9747efb5491259

One connection; six attempted/completed statements; 2967 ms overall including
bootstrap/cleanup; 22916 returned-value bytes, 27012 including metadata reserve.
Ordinal 55 and expected stored/computed checkpoint SHA passed before decoding.
The successful pinned control flow verifies postgres/postgres/postgres identity,
READ ONLY, statement timeout 10s and lock timeout 3s before the checkpoint query.
The receipt does not separately repeat those values; this conclusion is based on
its success under the exact hashed implementation. Rollback acknowledged TRUE;
connection closed TRUE, independently reported. No retry.

## Recovered inputs and adaptation

The historical profile copies agree; no requested historical field is missing.
Retained target is crn-d9sv93vavr4c73f98rb0, deployment dep-dbmq3d3rjlhs73c6t2dg,
build ee9dbb7b9dccca161aad46526248f14a9661ce9c, POOLER route. Resource ceilings:
2 GiB aggregate, 1 GiB source, 256 MiB controller, 512 MiB reserve; historical
browser-source ceiling 75s. Historical stable credential verifier equality is
TRUE; no credential or verifier value is published.

`tameside-runtime-inputs.json` now carries recovered inputs separately from
unverified current values. The existing offline campaign planner recomputed
canonical period S4_FINITE_677f555670666bcf21f45860, RECEIVED 15–21 September,
source-plan SHA d90fe1a7effd84d05593a8cbdc782d97c9b42fa904c45b29312c5fc03d6dae06,
max_runs=1 and generation16. The original digest-bound release-proposal is preserved byte-for-byte; v1.5
consumption is recorded in this receipt and #214/#227, separately. Its existing
disposition compiler still accepts the unchanged proposal. Nothing is
registered or installed. Sealed policy/manifest/enabled build remain null, rather
than silently promoted from historical or fixture values.

Source review narrows the dependency: `daily_intake_runtime.require_source_context`
and the source-worker profile use the browser only for Manchester. Tameside uses
its existing HTTP Idox path with 45s source/60s supervisor limits. Do not require
an unchanged browser canary to release Tameside or insert render_profile into the
campaign policy (its exact schema does not accept that field). Preserve the
browser profile for the all-ten follow-on, including Manchester, not as proof of
current browser installation. Bolton and Trafford remain explicitly in scope.

The old #213 scripts.owner_pilot_job command has a literal old-period allowlist,
and is absent from the #227 candidate tree. It MUST NOT be reused verbatim.
The existing supported new runtime command is tameside_candidate with the canonical
period above, a sealed policy file and fresh output directory. Its source already
rejects admin credentials, dirty build identity, route mismatch and reused output.
Use the existing owner lifecycle for activation/restoration; do not execute the
new runtime directly in the owner shell. The old binding's absolute deadlines are
expired historical evidence and cannot become the new policy expiry.

## Precise outstanding current fact and smallest resolution

The checkpoint proves an old configuration was restored, not that the restricted
service is currently suspended, auto-deploy disabled, and its cron command,
schedule, branch, build command, root and plan still match configuration digest
78b5f3a8f5b2730f5d675d214192b53e339edb07ceeb14e188ed1d2c3ab14257.

Smallest next external check is ONE read-only Render get_service for
workspace tea-d9qbf8jm8hqs7385cu0g / service crn-d9sv93vavr4c73f98rb0.
Compare its returned non-secret service JSON offline using unchanged #213
intake_owner_io.service_guard: exact service, cron_job, suspended, autoDeploy=no;
all start/cron commands /bin/true; schedule present; hash its sorted-key canonical
walk of command/schedule/branch/build/root/plan fields against the retained digest.
Output only the match booleans/digest and differing field names. No environment
secret fetch, SQL, deployment, process launch or mutation is needed for this check.
It was NOT performed under the checkpoint-only approval. A match closes present
provider-configuration reconciliation, not current credentials or a future build.
A mismatch identifies the exact configuration drift to resolve in the combined
operational package, not authority to change the service.

Actual new build identity, restricted-role authentication/restoration and current
STOP/permissions must be checked by the existing guarded operational sequence
under its later combined approval. Historical closure flags and expired deadlines
cannot substitute for those checks. Post-recovery manifest hashes are generated
by the already-tested independent readback recipe, never predicted.

Recommendation: accept the checkpoint receipt as completed; NO-GO for release.
Complete the current provider comparison, then finish/seal the adapted owner
lifecycle and exact enabled build/command for distinct REVIEW and one operational
owner decision. Do not ask to repeat v1.5 or rerun the passing recovery suites.
The fixed expiry ceiling remains 18 November 2026 20:00 UTC. Existing production
stops and live flags were not modified. No newly retained listings, screening,
qualifications, facts or backlog were produced by this read.
