# Fixed four-council source-only release proposal

Status: OFFLINE CANDIDATE. Stage 4 OPEN. No live registration, permit, stop
change, dispatch or source call has been issued. This does not activate ingestion.

## Scope and controlling decisions

Baseline `608aa07d496ff00ccd405dc77de31eb6bbfc6edd`, tree
`dab51f217310ef19b1e4a3d4c8e2de40df69e8ea`: integrated PR #180, nine-file proof
retention. Reuse [its recovery proposal](../four-council-proof-20261022/RECOVERY.md),
[Specification 029](../../../specifications/029-stage4-material-discovery.md),
[Specification 032](../../../specifications/032-stage4-stable-credential-pipeline.md)
and the accepted source contracts. No new parser, diagnostics layer, receipt,
writer, SQL, schema, privilege, scheduling or admission path.

| Order | Council | Basis | Inclusive source interval | Reader |
| --- | --- | --- | --- | --- |
| 1 | Bury | RECEIVED | 2026-10-08 to 2026-10-14 | Existing Requests/Idox |
| 2 | Rochdale | VALIDATED | 2026-10-08 to 2026-10-14 | Existing Playwright public register |
| 3 | Tameside | RECEIVED | 2026-10-01 to 2026-10-07 | Existing Requests/Idox |
| 4 | Oldham | RECEIVED | 2026-10-08 to 2026-10-14 | Existing Requests/Idox |

The exact URLs, including Rochdale's existing date-filter shape, are in
`manifest.json`. No RPC construction, retry, subdivision, detail retrieval or
replacement observation. Both `retain_proof=True` and `no_transport_retry=True`
are explicit. `finite_acceptance.read` is reused directly; its broader `execute`
manifest is NOT used. No Bolton work.

UNKNOWN means window completeness was not established. It does not invalidate
observed applications. COMPLETE here is a source enumeration result, not blanket
source qualification, coverage acceptance, identity admission or historical
public-availability proof. No completed-through or watermark is advanced.

## Executables and default-off selection

- `verification.discovery.four_council_release`: fixed manifest, renderer,
  validator, owner controller and private source child.
- `owner-launch.sh`: owner-local WSL/systemd entry, execs the controller in the
  existing dedicated operational scope. No browser/Actions dispatch is used.
- `finite_acceptance.read`, PR #180 projection and existing source supervisors.
- Existing `operational_publication.GitHub`: bounded requests, fsynced intent
  journal, expected head, non-forced update, Git blob identity and committed-path
  readback. Publisher credentials are never passed to source processes.
- Existing `OperationalMemory`: kernel 1 GiB source / 1.5 GiB aggregate containment,
  256 MiB controller, kept active through final publication. Owned subgroups are
  positively removed afterwards. No parent-limit permission or RLIMIT_AS workaround.

Necessary integration correction: the Arcus supervisor previously admitted only
hosted runners. An opt-in `four-council-owner-local` context is now admitted only
for the exact Rochdale proof scope. It checks real source/parent cgroup identities,
limits, swap prohibition, group OOM control and a minimal environment. Existing
hosted and default behaviour is unchanged. This is execution-context fixture
validation, not a claim of fresh live Rochdale qualification. Nothing for another
council or metadata route inherits it. No fake hosted-runner variables.

Review also found that the legacy Idox path had a six-page limit but no cumulative
60-row enforcement. The fixed child now explicitly selects `max_rows=60` through
a new opt-in control; the parser and all default paths remain unchanged. It stops
before materialising an over-limit page, retains its structural proof/body hash
and observed/retained row counts, reports ROW_CAP/INCOMPLETE and never fetches a
following page. No silent truncation is called complete. The launcher independently
rejects any returned audit over60 rows/six pages. Tests cover60/61 rows on one page
and a cumulative50+11 crossing. This is a missing resource-control correction,
not evidence of a historical parser defect.

## Proposed stop treatment: approval still required

The original Salford global stop and historical manual stops remain untouched.
Specification 032 contains later stop generations; `STORAGE_TEST_STOP` is not
misrepresented as the current manual-stop value. Registration binds that retained
specification's baseline/path/hash. No current database stop state is claimed.

This database-free controller cannot read or synchronise the database stop table.
Its proposed owner-controlled external permit is a NEW, exact four-source-only
stop treatment, not an existing ledger exception, Bolton exception or blanket
release. It is inactive by default. Product Owner approval must explicitly accept
this boundary before an enabled control is published. If live DB-stop
synchronisation is mandatory, this package remains NO-GO: that requirement cannot
be met with zero DB access. Do not silently add a DB read or owner role.

An enabled control must be published by the authorised release owner on the
existing evidence branch. Local files or queue membership alone authorise nothing.
Every slot requires the exact registration, unexpired permit, unused remote history,
verified previous publication and unchanged control/evidence head.

The permit binds the release ID, revision, tree/dependencies/package versions via
a registration-binding digest, manifest, expiry and retained stop evidence.
That digest excludes ONLY `evidence_head`: including the commit containing the
control would create a self-reference. The final expected evidence head is
independently fixed in the approved registration and checked before claim.

### Stop-all and cancellation

- Only a qualified COMPLETE result with verified publication and positive closure
  permits the next slot. FAILED, UNKNOWN and INCOMPLETE seal evidence and stop all
  later scopes. Four is a maximum; Bury UNKNOWN may be the only observation.
- Any identity/criteria, security, accounting, export, publication or cleanup
  failure stops the package. Unsupported/malformed proof is not exported.
- The owner is the sole dispatcher. Ctrl+C is safe local cancellation. No second
  terminal, audit watcher, event counting, polling by the owner or duplicate launch.
- Before each slot, two bounded GitHub reads verify head and exact control bytes.
  While a source runs, the controller checks the immutable expected head every two
  seconds (one GET, five-second request timeout). A visible change or failed read
  aborts. No mutation by another publisher is silently reconciled.
- Detection is at most seven seconds AFTER a cancellation/head change is visible
  to this API. GitHub replication/cache propagation is UNKNOWN; there is no
  proven absolute end-to-end remote cancellation bound. This residual limit needs
  explicit acceptance. The hard package/worker deadlines remain independent.
- Active interruption kills the whole source cgroup and reaps its leader. Source
  placement occurs before exec, so cancellation cannot miss a worker that has not
  imported its modules. Nested new-session processes remain inside the cgroup.
  Owned-group closure has five seconds plus one second for leader reaping. Missing
  positive evidence is UNCERTAIN. Local Ctrl+C does not depend on GitHub visibility.
- A changed/unreadable control holds later scopes, even if no source started.
  Expiry is checked on every API operation and source supervision poll. It does
  not grant permission for another execution. No automatic recovery or replacement.

## Budgets

All below are proposed release ceilings, not new live authority. No borrowing.
The renderer freezes these values; the launcher rejects a changed manifest.

| Metric | Each Idox slot | Rochdale | Entire package |
| --- | ---: | ---: | ---: |
| Observations | 1 | 1 | 4 |
| Source requests | 10 | 80 | 110 |
| Source bytes | 3,000,000 received-body | 20 MiB existing Arcus combined metric | 29,971,520 mixed-accounting bytes |
| Source worker seconds | 45 | 45 | 180 |
| Active source supervision | 60 seconds | 60 seconds | 240 seconds |
| Pages/segments; rows | 6; 60 | 6; 60 | No automatic split |
| Source/aggregate memory | 1 GiB / 1.5 GiB | Same | Sequential |
| Worker audit | 512,000 bytes | Less than 65,536 bytes | Existing lower bounds win |
| Slot exported envelope | 512 KiB | 512 KiB | 2 MiB total, including final envelopes |
| Slot elapsed | 480 seconds | 480 seconds | 1,920 seconds |

Each slot retains 260 seconds setup / 60 active / 160 closure-publication. These
are maxima, not additive entitlements beyond 480 seconds. The first slot includes
registration/claim setup. The package clock is cumulative; fresh processes cannot
reset it. systemd independently enforces 1,920 seconds. Source polling/closure is
reserved inside the 60-second active allocation. The existing 45-second source
contract is unchanged. Exhaustion stops, never refetches or skips ahead.

Additional explicit API ceilings: 320 GitHub requests during execution, including
control reads; at most 80 of those for publication. Each API call has the existing
five-second timeout. `GitHub.publish` costs `6 + 2*n` calls for `n` files. Normal
four-slot publication uses 10 claim + 4*12 slot + 12 final = 70 calls; control and
unused-history reads count separately. A lost acknowledgement consumes requests
and exported bytes too. These counts concern the existing publisher's logical
calls, not total wire traffic. Registration preparation is a separately approved
release action, not permission to make additional source calls.

Source received-body bytes, Arcus combined accounting, exported bytes and API
calls are distinct. None measures total network traffic. Interrupted source
accounting remains UNKNOWN with a reservation; zero exported observations is not
a claim that zero requests happened. Observed lower bounds and reserved maxima
are reported separately. No reconstruction of historical accounting gaps.

## Release rendering and single-use bootstrap

No active registration or expiry is committed in this PR. Rendering is local and
network-free. Default output is INACTIVE. `--propose-reviewed-stop-treatment`
creates reviewable proposed bytes only; it performs no publication or execution.

The later authorised release operator must:

1. Verify integrated revision/tree, exact dependency and runtime package versions,
   clean checkout, WSL memory delegation and existing GitHub keyring access. No
   repeated sign-in or database input. Missing prerequisites fail before sources.
2. Select one never-used release ID and UTC issued/expiry timestamps, at most
   24 hours apart. Inspect complete consumed history for that ID.
3. Render proposed registration and control locally; review their hashes and the
   explicit source-only stop treatment. Publish control to its exact bound path
   under the existing evidence branch with an expected-head check. No source call.
4. Use the returned control commit as final `evidence_head`; rerender registration.
   The control's binding digest stays unchanged because it excludes only this
   moving head. Verify the content at that final commit, file SHA256, dependencies
   and unused history. Publish the exact registration blob/hash for owner handoff.
5. Only after the grouped live decision, the owner launches once. The controller
   probes `claim/consumed.json`; any existing record refuses even from a fresh
   computer. It then publishes its consumed marker and manifest before any source
   call. Concurrent claims race on one expected head; only one can commit.
6. The root/audit path is unique and exclusive. A consumed registration cannot be
   rerun, even after failure. Any ambiguous submission/publication is reconciled
   read-only; it never triggers a second launch.

An illustrative OFFLINE render command (not execution authority):

```bash
python -m verification.discovery.four_council_release render \
  --release-id four-council-review-example \
  --revision 608aa07d496ff00ccd405dc77de31eb6bbfc6edd \
  --tree dab51f217310ef19b1e4a3d4c8e2de40df69e8ea \
  --evidence-head 0f55c27f4c339f9028a216807f849812d762bfb2 \
  --issued-at 2026-10-22T00:00:00+00:00 \
  --expires-at 2026-10-23T00:00:00+00:00 \
  --output /tmp/four-council-INACTIVE.json
```

Those historical example identities/timestamps are not a candidate or release.
The final reviewed successor must bind the later integrated implementation.

## Owner handoff and results

The complete final command is published only with real released hashes; no
placeholder is presented as runnable authority. Its tested invocation form is:

```bash
bash docs/design/four-council-release-20261022/owner-launch.sh \
  /absolute/path/to/released-registration.json \
  RELEASED_REGISTRATION_SHA256 \
  REVIEWED_INTEGRATED_REVISION
```

Reuse `$HOME/stage4-owner/pr122-storage-acceptance` and the existing
`storage-controller-venv`. Verify/check out the exact integrated revision before
this command; no new authentication or token mechanism. The script verifies the
clean checkout/hash and execs the memory-contained launcher. It makes no GitHub
Actions dispatch; no browser fallback or automated concurrent dispatcher exists.

One owner launch, zero DB credential entries, zero new runtime accounts and no
protected-environment approval are required by THIS owner-local path: it does not
read environment secrets or activate a hosted protected job. This is a proposed
execution arrangement, not permission to bypass an environment-required approval.
If an existing organisation rule requires a protected approval, release is held
until it is honoured. Existing GitHub owner access/keyring is reused.

Maximum attendance: one finite package up to 32 minutes plus pre-launch binding
verification. Visible `[n/4]` start and result lines explain progress. The terminal
ends with status, reason, cleanup and audit paths. No audit watching or second
terminal is needed. On a non-complete or uncertain result, do not rerun.

Results live at `~/.local/state/propertyaigent/RELEASE_ID/`: complete operational
`events.jsonl`, separate final-publication `publication-events.jsonl`, retained
returned audits and `final-result.json`. No arbitrary exception text is emitted.

## Evidence publication and closure

Destination is only `stage4/narrow-continuation-evidence-20261016`, under
`docs/design/ingestion-operational-execution-RELEASE_ID/`. The original head is
fixed at release. Every own verified publication advances the expected head.
Any other movement stops; no force push, overwrite, fallback branch or merge.

Each slot publishes its original structured audit, receipt and SHA256 index,
then verifies their exact bytes and committed membership. A validated returned
failure audit is published before stop-all. Malformed/unbound proof remains local
with a hash/path in the result; no unsafe body is exported to explain a failure.
Unwritable or oversized output stops without truncating it or claiming COMPLETE.

All source processes are closed on success AND failure. After positive source-group
and socket/child checks, final publication occurs with the existing controller
256 MiB and aggregate1.5 GiB limits still enforced. Then memory.close removes the
owned subgroups exactly once on success or failure, with no subsequent API call.
The parent memory.max is never changed. Outer systemd scope removal on process
exit is not retrospectively claimed.

The complete source/control/publication-prefix chain is sealed before final archival
and hash-verified. Its cleanup is explicitly PENDING_MEMORY_SCOPE_CLOSURE; only the
local sealed result after final publication and memory.close may say CLOSED.
The final archive includes that exact `events.jsonl`, the before-publication result
and `HASHES.json`. Its own publication intent/ack chain is necessarily separate:
an archive cannot contain the acknowledgement of its own upload. The local sealed
final result reports the verified evidence commit and cumulative publication costs.
The final-publication receipt remains local; do not describe it as archived in the
commit it records. Any later receipt archival requires reconciliation, not a source
rerun. This is an explicit evidence boundary, not an omitted operational chain.

On moved head, lost acknowledgement or unavailable publication, preserve all local
files and report publication HELD/UNCERTAIN. No blind retry or compensating write.
Access/DB state is unchanged throughout; zero database connections and application
writes. Final process/socket closure is checked again after publication; a failed
check overrides earlier CLOSED. Global security/accounting/cleanup stops prevent
later sources. No accepted production IDs or ledger records are touched.

## Later decision needed

Approve only after exact-tree CI and independent review:

- Dormant integration of this candidate, separately from execution.
- The explicit database-free external permit and its lack of DB-stop synchronisation;
  local cancellation plus the stated remote visibility limitation.
- One released four-slot registration, exact bindings, finite budgets and expiry.

No source-local continuation. No retry, replacement, admission/B2, unit facts,
backlog rollout, scheduling, deployment or Stage advancement. The four historical
coverage gaps remain open until evidence supports their separate reconciliation.
