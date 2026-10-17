# Finite storage memory correction — Stage4 OPEN

The owner attempt at integrated dd6a94c171c7658b5c699c526d19e345fa6bef7b consumed
registration 802a4eae09ec897c1cc9c27704abeb9f6913eaeb919252ed64e98a452a055279.
Its owner-pasted journal is preserved here, with all five chain entries and exact
1573-byte SHA256 f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0
verified against the reported supervisor digest. This is the supplied journal,
not an independently accessed owner machine. Historical cleanup stays UNCERTAIN,
zero reported survivors. The failure preceded DB connection, install, password
material, secret mapping, activation, seed and teardown. Zero DB attempts/effects.

Normal owner gh account/secret-name calls succeeded; only DATABASE_URL existed.
A real gh --version under RLIMIT_AS=256MiB exited2 with Go's "failed to reserve
page summary memory". Address-space reservation is not actual memory usage.
Do not change authentication, credentials, SQL, TLS, existing permissions or route.

## Correction and authority boundary

Remove the worker's RLIMIT_AS. Require a dedicated systemd USER scope with
MemoryMax=268435456, MemorySwapMax=0, OOMPolicy=kill and Delegate=memory applied
BEFORE Python exec. No sudo/root production fallback. Existing secure TTY and
D-Bus/keyring environment are inherited through --scope, not a background service.
This kernel ceiling includes supervisor, inherited interpreter memory, worker and
all descendants, so it is stricter than limiting the worker alone. Cgroup charged
memory includes more than RSS; report its peak separately from sampled owned RSS.
The supervisor additionally retains its existing aggregate-RSS checks.

The controller verifies the exact dedicated scope, exclusive PID, effective kernel
limits and writable delegation before credential input or authority consumption.
It moves itself to a supervisor leaf, enables memory only in that private scope,
and births the worker into a separately limited child before any gh/source/DB
operation. The outer bound prevents inherited-memory charges escaping the ceiling.
Outer and child limits/events are checked throughout and before success. All
worker descendants inherit containment, including processes leaving a session.
Failure/unavailable accounting/enforcement stops; no process-by-process fallback.

Cleanup attempts cgroup.kill independently of successful memory accounting, then
requires kernel populated=0 and child-group removal. Existing process/socket
closure checks remain. Enforcement/setup failures cannot declare storage success.
If an outer OOM kills the supervisor too, there may be no final JSON. The durable
last intent is authoritative; missing final closure remains UNCERTAIN and blocks
all replay/mutation. Kernel/systemd scope termination does not prove DB commits or
secret-store outcomes. Never infer rollback from process death.

The original audit directory is neither renamed nor deleted. A successor requires
its exact prior SHA before input and has a new fixed durable single-use latch.
The old registration cannot be reused. Its0.11050213100043038 supervised seconds
are deducted: at most239.88949786899957 further supervised seconds,13 total DB
connection attempts (none spent),256MiB actual memory and2MiB combined exported
evidence. Reserve4096 bytes for prior audit/result output; the successor journal
uses the remaining allowance with the unchanged32KiB closure reserve.
Phase/storage/connection/output limits and closure reserve remain unchanged.
Successor registration must retain the original expiry, not silently extend it.

## Validation and readiness

Focused local pure controller/helper regression:27 passed. Native validation must
use real Linux gh under the worker file/core restrictions, from-exec kernel limit,
non-root delegated access, excessive-memory whole-scope termination and positive
kernel cleanup. PostgreSQL rehearsal keeps actual restricted SQL logins and the
existing fixed seed/readback/denial/uncertainty scenarios. CI root is used only to
create a disposable delegated scope, then drops to runner UID before Python.
No production credentials, source calls or secret changes occur in validation.

Do not execute this draft. Required exact-head checks, final independent review,
integration and explicit successor registration remain prerequisites. Production
WSL must support a systemd user manager and delegated cgroup-v2 memory controller;
unavailable support is a concrete pre-credential blocker, not permission to weaken
memory enforcement. Do not reset authentication or request a new token.

Preserve IDs1504–1508, Salford stop, all consumed authorities and historical data.
This package has no source, application/factual, consumer, scheduling or deployment
allowance. Storage acceptance remains separate from operational pipeline acceptance.
