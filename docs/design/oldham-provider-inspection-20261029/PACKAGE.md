# INACTIVE fixed provider inspection — Stage 4 OPEN

Approved preparation only. No timed registration, credential request or production
execution is released. The existing `oldham_inspection` entrypoint now has one
explicit `--provider-comparison` profile. It cannot accept SQL paths or queries.
The historical inspection default, registration namespace and SQL remain intact.

The profile binds `provider-comparison-readonly.sql` SHA256
`4e29bbf12027270cbc0e7685b8b3488a31dde84c8fa1135024046f210cb7ba93`.
It replaces the prepared predecessor hash
`92385277d49eb36b20764af428d3000e2fc536d92682ad2e84e9f8423f7403a4`:
identity/read-only state are now returned together and LIMIT clauses were removed.
No view definitions, statistics rows, function source or secrets are exported.

## Enforced route and limits

Existing hidden getpass input, exact route validator and reviewed verify-full CA
are reused. Destination: project `zcikcfgpblzuzpanpdqd`, session pooler
`aws-0-eu-west-2.pooler.supabase.com:5432`, database `postgres`, routing user
`postgres.zcikcfgpblzuzpanpdqd`; both observed database identities must be `postgres`.
No alternate destination, URL arguments, environment override or retry is allowed.

- One connection attempt, no reconnect or cancellation connection.
- Connection timeout3s. Startup options set default_transaction_read_only=on,
  statement_timeout=5000, lock_timeout=1000, idle_in_transaction_session_timeout=5000.
  Fixed BEGIN READ ONLY and SET LOCAL statements independently retain the guards.
- Existing session watchdog:30s active from credential-input completion, including
  preparation, work, rollback, closure and reporting; work alarm22s reserves closure
  and reporting. Hidden input has its separate existing120s ceiling.
- At most16 driver statements including rollback; seven planned. The last slot is
  reserved for failure rollback. There is no arbitrary SQL capability.
- Queries have no LIMIT. Client fetches expected cardinality+1 and refuses extra
  rows; driver-returned values also have a16KiB cap. Kernel memory controls remain.
- Combined output<=65536 bytes: all persisted files<=32768 plus terminal JSON<=32768.
  Journal events<=16384 reserve result space. Byte checks happen before save/print;
  overflow refuses rather than emitting a truncated successful result.
- Existing try/finally closes every opened connection. Failure attempts one counted
  ROLLBACK even after an uncertain BEGIN acknowledgement. Broken connection or hard
  process termination relies on server session abort; no positive closure is claimed
  without evidence. No client can promise an acknowledged rollback after connection
  loss. The kernel/process watchdog remains the terminal bound.

## Interpretation

Exactly four unique expected view/role rows and three expected function rows are
required. Every boolean is compared by type/value, not truthiness. False is a
named current mismatch with observed/expected values. Missing object/role, NULL,
malformed row/value, unexpected identity, duplicate, extra row, failed identity,
timeout or overflow is INCOMPLETE. Function overload count must be the integer1;
other nonzero counts are mismatches (extra returned rows also refuse).

`PROVIDER_COMPARISON_MATCH` exits0 only with CLOSED cleanup. MISMATCH and INCOMPLETE
exit1 and prohibit continuation. A match covers these provider predicate groups
only, not the full provider/recovery gate or historical cause. The comparison
includes view shape/hash/options, owner/extension membership and forbidden table/
column/schema privileges, plus C-function shape/signature/configuration/library/
ownership/extension. Separate monitoring-role/reset-EXECUTE gate predicates are
not claimed covered. Known mismatches remain visible when other evidence is
incomplete. Actual view hash and expected MD5 are exported; other comparisons
report named predicate booleans versus true, not arbitrary catalogue strings.

## Prerequisites by purpose

Inspection itself requires: REVIEW-approved clean candidate commit/tree; exact
bound files/SQL/CA hashes; an owner-approved short-lived registration in this new
namespace; owner Linux TTY with the existing Python environment and delegated
systemd scope; existing administrative credential via hidden input. No authentic
source packet, historical private receipt or standing qualification is needed to
read these catalogue facts. None of the host/credential availability is assumed.
No registration has been rendered/released during preparation.

Historical explanation additionally needs owner originals (final-result.json,
events.jsonl and publication journal if present) for consumed operations
`oldham-owner-capture-screening-once-20261028` and
`oldham-owner-installed-capture-screening-20261029`, plus completed
`oldham-activation-reconciliation-once-20261028` result/events and their hashes/modes.
Those private complete originals were unavailable in the inspected saved archives.
They do not block this inspection. Published prefixes at
`4700f6276203e6ba043897e1f914816e6713e6a6` identify the refusal but not the predicate.
Current metadata cannot establish historical cause if it changed.

Later cleanup/provisioning/processing still require authentic historical
reconciliation, private originals, explicit permissions and exact accounting.
Retained source/slot originals match origin
`d0eea18a7a9e1353ff4d281c68dc288dc3363196`; accepted qualification and owner acceptance
are available. They are not substitutes for those later prerequisites. Consumed
operations must never rerun.

## Supported proposal — DO NOT EXECUTE until separately approved

On the existing owner Linux host, use a CLEAN checkout of the exact REVIEW-approved
candidate in `$HOME/stage4-owner/pr122-storage-acceptance` and the existing
`$HOME/stage4-owner/storage-controller-venv/bin/python`. Before execution, REVIEW
must pin the candidate commit/tree and owner must approve registration/expiry.
The existing renderer supports the fixed profile (no custom queries/limits):

```bash
python docs/design/oldham-readonly-inspection-20261028/render_registration.py --provider-comparison --minutes 30
```

It prints JSON and a SHA256; only after explicit approval save that exact JSON
outside the checkout, e.g. `$HOME/oldham-provider-registration.json`. This is a
proposal, not an instruction to issue it now. Registration validation requires
current clean HEAD/tree, bound-path hashes, SQL/statement-set hash, controller/CA,
exact mode/authority/state, and expiry<=2h. The state directory is exclusively
created, preventing reuse. Do not alter these arguments to resume a consumed run.

With the approved SHA256 substituted, the supported production invocation is:

```bash
cd "$HOME/stage4-owner/pr122-storage-acceptance"
systemd-run --user --scope --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 \
  -p OOMPolicy=kill -p RuntimeMaxSec=180s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,sys;sys.path.insert(0,os.getcwd());from verification.ingestion_storage.oldham_inspection import main;main()' \
  --provider-comparison --registration "$HOME/oldham-provider-registration.json" \
  --registration-sha256 APPROVED_REGISTRATION_SHA256
```

After exit inspect outer scope status separately using the existing bounded
systemctl readback. This does not dispatch GitHub or run the standing operation.
The one-use evidence path is
`$HOME/.local/state/propertyaigent/oldham-provider-comparison-once-20261029/`.
No active registration/expiry/permit is included here.

## Accounting boundary

The historical standing batch measurement remains76 calls; adding11 reserved
preparation calls gives87/100. This inspection has no GitHub client. Development
publication calls are separate. Complete first-transition cleanup/provisioning/
qualification accounting remains unmeasured and held.
