# Reviewed local implementation contracts — before runtime changes

Base3291b2a8ee46b081051b68ecbdc9b233aa4b84be. Local engineering approval only.

Migration coexistence: preserve scripts/migrate_p0a.py byte-for-byte. Revisit
owns an explicit SQLAlchemy Core metadata registry, imported by its separate
migration/verifier; it is NOT injected into Base. This is an explicit component
boundary, not a hidden schema: combined verification enumerates Base tables plus
all five named revisit tables and rejects unknown tables. Existing P0-A verifier
continues to inspect every Base table, allowing only its original two missing
objects. Revisit verification permits either all five absent (pre-install) or all
five present with exact expected definitions; partial installation fails. The
revisit migration requires P0-A delta installed first. Combined verification is
read-only/repeatable before P0-A, after P0-A and after revisit; applying revisit
before P0-A fails, never installs P0-A on its behalf. No existing table is altered.

Five tables retained: work is mutable coordination; attempts preserve per-run
history; content versions deduplicate immutable bytes; observations retain every
completed check with immutable stage/date provenance; relationships retain typed
candidate/verified edges. Combining them would mix unrelated retention/mutation
rules. Revisit does not write AH claims, Document or selected intelligence.

Recovery: use existing verify_child and its real inherited lock. Every database
operation verifies matching running council ScrapeRun and full invocation, not
run ID alone. Reserve and finalise lock work rows, compare owner/run/generation.
Recovery calls unchanged terminal_evidence on the prior run's recorded identity
and the actually verified successor. Same invocation, unresolved prior identity
or missing proof cannot recover. It finalises interrupted attempts and advances
generation in the same transaction as releasing work. A stale completion must
fail the locked generation check. Existing P0-A reconcile/release functions are
not modified; revisit recovery runs only inside the admitted child, after normal
supervisor reconciliation, and reads the preserved old owner identity.

Fetch outside transaction. One commit inserts body versions, observations,
relationship candidates and newly discovered work, then advances cursor and
completion. Unique attempt/response tokens absorb ambiguous-commit replay. Crash
before persistence leaves attempt unresolved for proven successor recovery.
Unchanged bodies reuse versions and add check observations. No timeout lease.

Integration is dormant and local-recording-only in this increment. No live
transport is installed. It runs as a bounded stage inside the existing child,
under the inherited owner. Enabling recordings in a production runtime is
rejected. Existing new discovery retains precedence; cap revisit responses and
bytes, and read the actual supervisor deadline from its gated-exec child command
context only if safely available; otherwise defer, never invent a remaining
budget. The stage does not extend the supervisor/watchdog deadlines. Fairness
claims are limited to the tested admitted finite workload, not unbounded legacy
stages. Any stronger guarantee requires reviewed existing-stage allocation.

Native PostgreSQL execution requires existing guarded isolated cluster support.
No server binaries are present in this runtime; do not retry installation. Add
native tests and a scoped runner/handoff if feasible; collection or SQLite is not
native execution. Ordinary PostgreSQL migration stays blocked; reuse only the
existing disposable engine identity proof, with an independent revisit schema
verifier and migration allow-list. AH catalogue authority is unchanged.
