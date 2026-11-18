# PA-TAM002 v1.4: archived restoration and joined preparation

Stage 4 OPEN. Inactive until independent REVIEW and acceptance of the amended
executable/order. Source: `9524503fa90228f31d48d16a58121c45d3eb90b8`; tree:
`b52191eb31482ca995dc930c0c158b82e2a5316e`. Package pin is the documentation commit
containing this file and artifact-pins.json. Existing v1.2 scope and expiry remain.

The archive-compatibility correction and complete evidence map are in
[JOINED-REHEARSAL.md](JOINED-REHEARSAL.md). Read and verify the linked archived
baseline before recovery. No new grant is authorised if that read is unavailable.

## Choice and exact ordering delta

Use the already-supported STOP15 installation, rather than admitting a namespace
under STOP14 or raising old journal limits. The order becomes:

1. Existing current owner/provider/address/TLS/permissions/overlap preflight.
2. Exact guarded Bolton recovery under STOP14; independent committed STOP15 read.
3. Existing exact journal namespace installation under STOP15; independent body,
   owner, search_path and restored-membership/schema-privilege readback.
4. Save and independently decrypt the restoration checkpoint in that namespace.
   Save/read each provider intent before its effect. Build the exact candidate,
   independently observe its commit, resuspend, restore original settings/env.
5. Continue the existing stopped dispositions/writer installation, independent
   manifest readback and deterministic policy/campaign installation. Reuse the
   journal established in step 4; never reinstall/reset it or call fresh().
6. Existing conditional STOP16 release, registration, finite restricted access,
   single Tameside submission, outcome readbacks and independently usable cleanup.

Recovery and journal installation now happen **before deployment**. A failed build
can therefore leave Bolton recovered at STOP15 with the namespace installed.
That is supported stopped state, not rollback to STOP14 or permission to replay.
The original ordinal55 ciphertext and all original evidence remain byte-identical.
The original journal retains its existing cleanup capacity; normal writes remain
limited through47 and the new journal retains all16 reserved cleanup snapshots.
No new database/table/Vault/credential/worker is introduced.

## Actual entry point and fixed inputs

Use the corrected source checkout as cwd with the existing owner runtime, and the
separate clean #213 checkout at f027ba28af69ae70208eab5ed047e4a8a81c6337. The existing
short-command/receipt route may call the following entry points; it must not call
old Pilot.run/build. Verify the candidate checkout and immutable remote ref
`pa-tam002/9524503fa90228f31d48d16a58121c45d3eb90b8` both resolve to that full SHA
before effects. No moving PR branch is a deployment pin.

```python
import os
from verification.ingestion_storage.tameside_owner_database import database_type
from verification.ingestion_storage.tameside_preparation import (
    pinned_modules, original_checkpoint, prepare_stopped, CHECKPOINT_SHA,
)

# frozen_root is the existing verified #213 checkout path, not a new route.
pinned, recovery, journal_source = pinned_modules(frozen_root)
db = database_type(frozen_root)()
assert db.address == '18.169.28.97'
original = original_checkpoint(pinned, db)  # private; never print this value
binding = recovery.binding(db)             # original hash/closure/identity checks
api_factory = lambda: pinned.Render(os.environ['PROPERTYAIGENT_INTAKE_RENDER_API_KEY'])
api = api_factory()
try:
    current = api.call('GET')
    environment = pinned.env_values(api.call('GET', '/env-vars?limit=100'))
    pinned.complete_inventory(api.call('GET', '/jobs?limit=100'), 'job')
    deployments = pinned.complete_inventory(api.call('GET', '/deploys?limit=100'), 'deploy')
finally:
    api.close()
assert pinned.service_guard(current) == original['original_guard']
assert environment == original['original_environment']
state = prepare_stopped(
    db, pinned=pinned, recovery=recovery, binding=binding,
    journal_source=journal_source, api_factory=api_factory,
    revision='9524503fa90228f31d48d16a58121c45d3eb90b8',
    checkpoint={'ordinal':55, 'sha256':CHECKPOINT_SHA},
    baseline={'service':original['original_service'], 'environment':environment,
              'deploy_ids':[d['id'] for d in deployments]},
)
assert state['status'] == 'STOPPED_BUILD_READY'
# Publish only allowlisted status/deployment/revision/checkpoint hash metadata.
```

On continuation after an interruption, use the **retained initial baseline** from
the encrypted new checkpoint, not current modified provider state as a replacement
baseline. Construct StoppedDeployment with the same pins and baseline; its prepare()
reconciles existing intents and does not dispatch them again. The independent
recover_and_install inspector recognises only the original journal body or the
exact source-derived revised body. The latter inspector clones just that inventory
expectation; the original frozen recovery module and other checks are untouched.

The loader isolates frozen relative imports from candidate modules. Journal
construction explicitly supplies the configured period, because the existing
recovery binding configures the frozen module after its Python defaults were
created. The existing Vault codec and SQL/CAS implementation are unchanged.
Frozen service_guard digests are captured before encrypted JSON serialization;
recomputing them from reordered dictionary keys is not used as a restart check.

Build command, exactly:

```sh
pip install -r requirements.txt && python -m verification.ingestion_storage.tameside_build_receipt
```

The build prints non-secret execution binding and performs no database/provider/
council calls. Fresh service/environment, dormant roles and STOP15 are checked
again before build effects. Environment contains only PYTHONUNBUFFERED, LANG, TZ,
OPENBLAS_NUM_THREADS if originally present. The default command stays /bin/true.
Resume is the sole build dispatch; POST /deploys and POST /jobs are not used here.
Provider IO retains frozen response/HTTP bounds, plus 40 calls, 40 elapsed seconds
and 786432 aggregate decoded bytes per preparation invocation. Pending builds
may be read back within the original 20 observations / 300 seconds maximum; no
resume resubmission. A completed or uncertain invocation is not a new allowance.

## Interruption and uncertainty handling

- Recovery lost COMMIT: independent exact inspector; never repeat if committed.
- Journal installation lost acknowledgement: compare exact installed body and
  restored privileges independently; never reinstall an already matching body.
- Journal save lost acknowledgement: independently decrypt and compare the exact
  intended state, including reserve accounting; missing/different state stops.
- Provider INTENT without a matching effect: UNKNOWN, no redispatch. Build polls
  only read the same operation. Multiple new deployments/wrong commit refuse.
- Completed provider effect with lost acknowledgement: independent readback,
  then durable acknowledgement. Restart does not repeat the provider mutation.
- Terminal-only containment remains independently callable via
  StoppedDeployment.contain(). It verifies terminal inventories, suspends,
  restores and checks exact original configuration/environment using the existing
  reserve. An incomplete normal restoration is not blindly repeated: current
  state must be one of the exact staged/original states before a separately
  journalled containment restoration. Original pending intents are preserved.
  Drift, nonterminal activity or failed restoration requires reconciliation.
- Contained operations cannot return to normal preparation; no new build or
  collection is inferred. Cleanup can run after expiry; new preparation cannot.

## Connected validation

Current v1.4 final executable: **56 passed, no failures/errors/skips in75.412s**,
PostgreSQL17.11. The actual joined run is included; its receipt is in
[joined-validation.json](joined-validation.json). It uses authentic archive22→55,
the sealed package, actual CLI and owned synthetic source, paged independent
backlog, provider handoff/restoration and database access closure.

Historical v1.3 local connected test (superseded by the v1.4 joined proof): **1 passed in 57.37s**, PostgreSQL17.11. It calls the
actual prepare_stopped/recovery/install/encrypted Journal/owner access entry points,
starting STOP14 with the unresolved Bolton fixture and a real 56-row old encrypted
journal at ordinal55 (normal-write refusal proved). It exercises 19 interruption
points, three changed-prerequisite refusals, lost recovery/provider/journal replies,
independent reads, no duplicate build, exact restoration and unchanged old history
and permissions. The same database/new journal then continues through dispositions,
writer/campaign installation, manifest/STOP16, registration, activation, synthetic
Tameside capture/retention/screening/backlog, private evidence and actual closure.
37 focused regressions passed, zero skips, in0.88s. Hosted run44175111923 passed all45 changed component/connected tests in74.86s, but its later broad regression step reached the180s test timeout without an assertion failure. The final workflow separates that existing runtime test file into its own180s step and preserves every test and all production bounds. Required final hosted results are
linked in the PR handoff; they must pass for final REVIEW acceptance.

Explicit fixture projections: disposable localhost database/credentials, synthetic
historical work and evidence hashes, synthetic checkpoint ciphertext/hash and
provider responses. The frozen recovery module retains the established fixture's
identity/inventory projections; its source bytes match the separately loaded frozen
module. Only synthetic new-namespace rows are reset between fault scenarios, never
original history; there is no proposed production reset. Provider completion is
mocked, and no live council requests occur. These results prove integration and
recovery behavior, not a deployment or newly populated production records.

## Scope and decision

Accept the exact changed pins and the above recovery-before-deployment ordering
only after independent REVIEW. Existing owner operational authority then covers
routine phases without further approvals. Expiry remains18Nov2026 20:00London,
latest binding19:25, with all remaining execution/cleanup time required. No automatic
extension. One Tameside RECEIVED15–21Sep2026 submission, max_runs1,10requests,0retries,
6pages of5,3MB,45s source/60s supervisor and existing aggregate/cleanup limits remain.
TLS verification, approved-address membership, single-address/no-fallback and
execution-time credentials/permissions/STOP checks remain mandatory.

All-ten follow-on: Manchester, Bolton, Tameside, Bury, Oldham, Rochdale, Salford,
Stockport, Trafford, Wigan. No other batch is authorised here. Permanent no-replay,
UNKNOWN historical facts, consumed inspections and fenced v1.3 stay preserved.
Production retention, screening, qualification, saved facts and discoverable backlog
must be reported separately from independent reads after the approved live run.
Stage advancement remains an owner decision.
