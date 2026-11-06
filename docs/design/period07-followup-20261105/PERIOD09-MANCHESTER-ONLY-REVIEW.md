# Period09 Manchester-only successor — REVIEW handoff

MASTER STAGE 4 OPEN. Current gate: safe Manchester-only continuation preserving accepted Tameside. Next gate: REVIEW authorises one bounded live verification. This is offline implementation and validation, not live readiness or accepted Manchester coverage.

## Exact releases

- Baseline: PR211 code `32410a68d06412a2c74c0aff818b4a19471e8ab0`; preceding evidence `11e1be43ee4dc7b65c56f5665658c21b0a1114f0`.
- Pinned scraper: `c7e8b51eac69686f8d54ac2c295f5cb2f0002dd7`.
- Scraper tree: `897c97b47dfe2bbe6282affa34f806ace19b1124`.
- Workflow SHA256: `946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9`.
- Manifest SHA256: `f78c0abf53ea7b414c6a093fc7d3bd4f4c257223701a015deadf7aa3b641bfe1`.
- Owner code/pin: `856554c963f2914be2fd57f6258fde32472c9a5b`. Owner pin changes do not change the pinned scraper tree or bound manifest bytes. Final handoff/test-fixture-only revisions can be descendants; the executable owner code remains this revision.
- Source branch: `prep/b-timing-pg17-current-20261103`, observed through GitHub at `3adb65d06d0492d3b8f9b798e49e3be20699b082`. Compare with the scraper candidate: ahead31/behind0, same merge base. No source-branch move or production deployment occurred.
- Fixed successor: `b-dbpilot-20261027-1102-09`; owner journal namespace only `b-dbpilot-20261027-1102-09_owner`. Runtime run ID is allocated once by the existing path, not fabricated in this handoff. Fresh live absence is UNVERIFIED pending authorised read-only preflight.

## Changes and boundaries

`scripts.owner_period09` connects the existing owner operations. `period09_successor` checks the exact period08 receipt, original four artifacts, prior06/07 histories, completed Tameside fingerprint and generation11 stop tuple. Its transaction appends only a receipt-bound failure disposition to period08 history and clears the exact two reviewed failure stops. Generation11, last_hard_stop and all other ledger content remain unchanged.

The existing namespace migration adds only period09_owner and atomically installs an exact registrar variant. The variant admits Manchester-only for this fixed period, fixed window and retained disposition; other database-pilot periods keep the two-council requirement. Registrar ownership, ACL and search_path remain exact. Temporary SET membership/schema CREATE and issuer permission are removed before commit. Mixed old/new namespace/registrar pairs refuse. `intake_finish` and the worker SQL remain byte-identical.

Activation, policy validation, restricted runtime qualification and independent finalisation select Manchester only for period09. Re-entering a consumed period09 refuses before source work. No generic council-selector, stop clearer or recovery framework was added.

The actual PostgreSQL sequence uses the owner CLI for inspect/dispose/readback, actual namespace/registrar migration, registration and activation, then the actual runtime entry point through source validation, archive write/readback, capture, screening, metadata batch, backlog, finalisation and access closure. Only provider transport/immutable fixture identities are substituted. One synthetic Manchester record is retained; the browser test separately exercises60 records/six pages. Disposable proof does not establish production provider state.

Cross-run reconciliation uses the existing `backlog_page` reader with both council contracts and separate capture/archive/run provenance. It returns all24 accepted period08 Tameside records plus the new Manchester record. Tameside's fingerprint,24 screenings,five metadata batches and prior outcomes remain unchanged. The period09 result itself covers Manchester only; it does not relabel period08 as successful or claim Tameside was recollected. The period-scoped runtime backlog command remains scoped to its policy; the shared cross-run reader provides the combined view.

## Measured file ceiling

Chosen: **2MiB per file**, only for the exact Manchester period09 source-worker plan (VALIDATED,2026-10-27..2026-11-02, no fixture or extra plan fields). Other collection paths remain512KiB. The consumed diagnostic retains its independently approved20MiB limit and is not rerun.

Real Chromium on Ubuntu24, real loopback TLS transport with fixture-only DNS resolution and all other DNS denied, private HOME/TMPDIR, exact retained filter DOM, six pages/60 unique records:

| File ceiling | Outcome |
|---|---|
|512KiB|Navigation BROWSER_Error;0 records|
|1MiB|Navigation BROWSER_Error;0 records|
|2MiB|COUNT_RECONCILED;60 records|
|4,8,16,20MiB|COUNT_RECONCILED;60 records|
|Actual patched worker,2MiB|COUNT_RECONCILED;60 records;zero survivors|

A writable, unlinked2MiB browser file was sampled in the8MiB trial. Short-lived files can evade the2ms sampler; sampled sizes are lower bounds, not proof that smaller files suffice.2MiB is the smallest passing tested ceiling, not a proof for every possible live Salesforce response. The actual-worker test uses production file-limit selection and the real probe, with the finite-reader provider call delegated to the loopback fixture. It is not a live-source test or a replacement for the supervisor/transport regressions.

Actual-worker peak browser-process RSS657235968 bytes; all trials stayed below1GiB and had zero survivors. Each trial made one physical loopback request; zero council requests. Browser SHA256 `ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e` matches the retained isolated diagnostic browser. Retained measurement: `PERIOD09-FILE-MEASUREMENT.json`, SHA256 `e4a34b49fd615865b74c5f687e08f79f2c3894d845c4543ff811ee695b63d986`.

Unchanged ceilings: Manchester80 requests,20MiB combined network bytes,60 listings,six pages,75s source/CPU,1GiB source group,512KiB retained source output and960s aggregate intake runtime. Existing stricter intermediate audit limits and SOURCE_SAFETY remain. GitHub publication NOT_REQUESTED; scheduled collection stays suspended.

## Validation

Pinned scraper workflow42111348922:
- PostgreSQL17 + scope contracts: job127539421175, **34 passed /86.54s**, artifact13454881513.
- Actual browser/worker measurement: job127539422174, **passed /37.74s**; eight bounded fixture trials.
- Unchanged diagnostic/transport/supervisor regressions: workflow42111349095/job127539422356, **47 passed /9.64s**.
- Period08 settlement/Tameside preservation: workflow42111348994/job127539421752, **26 passed /40.91s**.

Owner pin/migration-pair workflow42111958071:
- job127541515139, **34 passed /61.43s**, artifact13454412377.
- job127541515778, browser/actual worker passed /37.14s, artifact13454691837.

The34 checks cover successful/incomplete intake, duplicate refusal without recollection, altered receipt/stops/generation/release/Tameside/used-period refusal, SQL-level wrong council/period/receipt/binding refusal, rollback before commit/after update/after registrar replacement, unchanged ACLs/temporary permission removal, lost-acknowledgement reconciliation on independent readback, historical evidence and cross-run backlog preservation. No expected failure was turned into a passing coverage claim.

Broader CI is not wholly green. Baseline32410 and scraper candidate have the same frozen shared-file hash mismatch (`decc2b...` versus `188198...`) in `test_stage4_direct_registration`, reproduced in baseline workflow42104495756/job127515621329 and candidate42111348888/job127539421218 (384 other tests passed). B2/Oldham/reusable offline workflows hit that same check; their native jobs passed. Historical hashes were not rewritten.

Discovery offline baseline42104495416/job127515618042 and candidate42111348907/job127539422229 show the same11 failures in old IDOX timeout/three-council-isolation fixtures, with1508 passing; these paths are not used for Manchester-only continuation. The frozen-v6 import-oracle failure also matches baseline42104495405/job127515617606 and candidate42111348931/job127539421726 (1867 other tests passed); web tests passed. The earlier read-only SQL candidate inventory failure is also present on the baseline and its frozen SQL was not rewritten.

The new period-aware source plan exposed four old polling unit-fixture objects missing `args.period`. The fixture now supplies a period, retaining all assertions. Six focused source-poll/unknown-accounting regressions passed locally /9.57s; hosted confirmation is now complete below. The actual CLI always supplies period. Neither historical UNKNOWN request counts nor polling causes are changed.

Final validation revision `86e00b649cd146af73467b5d15cfa9fa7de4369c` (test-fixture and handoff changes only after owner pin): workflow42112786946, successor job127544423140 **34 passed /84.65s plus6 polling/accounting checks passed /9.53s**, artifact13454832923; browser job127544423771 passed /36.67s, artifact13453688477. The earlier four polling-fixture failures are resolved. No production bound file changed after the pinned scraper commit. Independent offline comparison confirms owner and scraper registrar inventories match, registrar body SHA256 `0235773e54127d7c822f86efa0e576eaa29e43cf3c2d2e240d97b2771f024869`.

## Live state and held actions

Reused accepted evidence: period08 settled/consumed, receipt `838d00b6b6a87dba856027bf5a4e60852d0f3ae3688db3e5baae4f35d0b1f24f`; Tameside fingerprint `959cc7c96a9fcd90446472da56e2209cacedbbef4fa3ea441d82d215fcf62f09`; original period08 run `768e1bd059474281ae9dc5113db42a99`/job `job-dbmacl5g1s2s73civi60`. Original8 Tameside+1 Manchester requests, failed Manchester coverage and original UNKNOWN cause remain intact. The isolated navigation opportunity is consumed. Prior06UNKNOWN and07outcomes remain intact.

Fresh period09 absence, current DB stop/permission/access state, current provider baseline/isolation and future artifact are **UNVERIFIED in this task**. Automatic approval review rejected observing the signed-in Render shell because the instruction is offline-only. No alternate route was attempted. Only the PR review branch and disposable environments changed. No production deployment, live DB write, stop clearance, runtime reopening, council HTTP or intake submission occurred.

## Smallest proposed live sequence — INACTIVE, requires REVIEW approval

One approval should cover fresh read-only reconciliation, the exact receipt-bound disposition, namespace/registrar migration, branch fast-forward/artifact preparation, one Manchester-only submission and monitoring/cleanup. No replay or scheduled restart. Refuse before mutation if any material prerequisite differs.

1. On the existing configured owner route, privately verify the settled08receipt, all4archive hashes, original journal ordinal56/hash `6cd68c0f6fc43bfda8b884eb08ae9dc873e24e95ca10d4626d53da22af8d6d4f`, Tameside fingerprint, dormant NOLOGIN/memberships0/sessions0/stable verifiers, no active marker/hazards, exact old namespace/registrar metadata and usable SET/schema/issuer authority. Verify period09 absent from policies,work revisions,evidence and owner journal. Verify provider baseline, cron suspension, no competing job/deploy/owner operation, required credentials/browser/cleanup capacity. Retain previous nonsecret release setting privately if changing service configuration; this procedure instead sets the pinned release only in the owner shell process.

2. Verify the source branch still equals3adb65d... and is an ancestor of c7e8b51...; use GitHub's conditional update_ref with expected_sha3adb65d..., sha c7e8b51..., force=false. Independently read back c7e8b51... . Do not move any other branch or deploy the owner web app. Refuse a changed branch.

3. Use the existing owner checkout/environment. The following commands are for the Render owner Web Shell (no secrets copied into chat):

```bash
set -e
git -C /opt/render/project/src fetch --no-tags origin 856554c963f2914be2fd57f6258fde32472c9a5b
git -C /opt/render/project/src worktree add --detach /tmp/propertyaigent-owner09-856554c9 856554c963f2914be2fd57f6258fde32472c9a5b
cd /tmp/propertyaigent-owner09-856554c9
test "$(git rev-parse HEAD)" = 856554c963f2914be2fd57f6258fde32472c9a5b
export PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-dbpilot-20261027-1102-09
export PROPERTYAIGENT_INTAKE_SOURCE_RELEASE='{"execution_binding":{"revision":"c7e8b51eac69686f8d54ac2c295f5cb2f0002dd7","workflow_sha256":"946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9","manifest_sha256":"f78c0abf53ea7b414c6a093fc7d3bd4f4c257223701a015deadf7aa3b641bfe1"},"tree":"897c97b47dfe2bbe6282affa34f806ace19b1124","branch":"prep/b-timing-pg17-current-20261103"}'
python -B -m scripts.owner_period09 --action inspect
```

Expected PRE_DISPOSITION_VERIFIED/ROLLED_BACK. Do not run through a failure. If the worktree already exists, inspect its exact HEAD and clean status rather than deleting or replacing it.

4. Only after all prechecks pass:

```bash
python -B -m scripts.owner_period09 --action dispose
python -B -m scripts.owner_period09 --action inspect
```

The dispose command commits one transaction then opens a new connection for independent readback. Expected DISPOSITION_COMMITTED_VERIFIED; global_stop null,manual_stop null,generation11,last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP unchanged; exact retained disposition/history and temporary permissions absent. An uncertain acknowledgement means run inspect, never repeat dispose. Exact pre-state proves rollback; exact post-state proves commitment; any mixed state stops.

5. Prepare only after disposition readback:

```bash
python -B -m scripts.owner_period09 --action prepare-successor
python -B -m scripts.owner_period09 --action verify-successor
python -B -m scripts.owner_period09 --action status
```

Preparation atomically adds09_owner and exact registrar variant, then uses existing journalled build/startup operations. Independently verify both function bodies/ACLs/owners/search_path, no temporary permission, unchanged ledger/evidence and dormant roles. Artifact must match all five pinned release fields; its reported browser hash must equal the measured `ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e` before collection. A different browser requires offline revalidation, not automatic acceptance. Startup must prove clean checkout,zero runtime authentication attempts and zero council requests. Verify exact scraper config/environment restoration and suspension. On an uncertain migration/build/startup acknowledgement inspect database,encrypted journal and Render history before deciding whether to continue; never repeat preparation to discover whether a build/job ran. `status` alone is not sufficient for a lost pre-journal migration acknowledgement: read back the namespace/registrar pair and confirm absence of journal/provider intent first.

6. If readiness and fresh Dashboard isolation (no inherited environment groups/credentials,secret files,competing jobs/deploys/owner operations; cron suspended) are independently verified, record the observation time and execute once within300s:

```bash
P09_OWNER_CHECKED_AT="$(date +%s)"
python -B -m scripts.owner_period09 --action run-successor --owner-checked-at "$P09_OWNER_CHECKED_AT"
```

Timestamp must follow the actual Dashboard observation; the command does not make the observation. Monitor the existing job to terminal. Lost submission acknowledgement requires durable journal + provider job history reconciliation; never resubmit. The run command owns registration, activation, qualification, one job and cleanup. On interruption use supported read-only status and, only if indicated, existing close-successor cleanup. A failed/consumed successor is not replayable.

7. Independent outcome readback must verify Manchester terminal traversal/coverage, exact archive body hashes, completed capture/screening/metadata batches, discoverable backlog and zero extra Tameside source work. Read the shared backlog separately with both council contracts and inspect provenance: all24 period08Tameside records remain identical, while Manchester records belong to09. Independently verify both logins disabled,memberships0,sessions0,temporary permission absent,authority expiry0,stable verifiers unchanged,exact scraper configuration/environment restored and suspended. If any outcome is partial/unknown, report it and recommend NO-GO for acceptance. Expiry alone is insufficient closure evidence.

Recommendation: GO for review of this bounded proposal, not GO for live readiness or Manchester acceptance. The smallest remaining decision is approval of the sequence conditional on fresh live prechecks. Stage4 stays OPEN.
