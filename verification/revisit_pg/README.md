# Durable revisit local checkpoint — not release acceptance

The implementation contracts were written in
verification/known_scheme_revisit/INTEGRATION_CONTRACT.md before runtime edits.

## Implemented, awaiting native verification

app/revisit/schema.py declares five additive component tables, separate from
Base and explicitly included in combined verification. P0-A migration artifact,
Base models, owner/admission, recovery functions and watchdog are unchanged.
app/revisit/migration.py composes original P0-A verification with its own table,
column, constraint and immutable trigger checks. Revisit apply refuses missing
P0-A prerequisites, unrelated tables and partial revisit installations.
Only an attested disposable engine is accepted; ordinary migration remains off.
The verifier supports the stated Base/P0-A/revisit schema composition, not an
arbitrary deployment containing additional independent component tables.

storage.py implements owner-verified reservation, terminal-evidence recovery,
generation fencing, content deduplication, per-check observations, typed
relationships and transactionally coupled frontier/cursor progress. It never
writes selected AH/intelligence. Existing phase successes survive partial work.
Network/body acquisition occurs before finish's database transaction.
These are implemented behaviours, not established native PostgreSQL passes.

The dormant hook in run_weekly.py sits after ordinary discovery/document stages
and invokes stage.py only with an explicit local recording configuration.
Production recorded mode is rejected. It does not seed work or migrate.
Store still requires the attested disposable engine; the ordinary pipeline
engine is intentionally not adopted. The native harness supplies that engine
and real inherited local owner descriptor to the same stage function. A full
run_weekly main-process walkthrough has NOT been demonstrated; no production
adapter or ordinary engine enablement is provided.

The stage conservatively derives remaining allowance from recorded council
start/effective timeout, reserves30 seconds for cleanup and takes at most10
seconds, two logical responses, eight recorded requests,4096 bytes per response
and16384 cumulative bytes (one sentinel byte may detect oversize). Pending work
is reported. Frontier limit32 is a finite local-fixture allocation, NOT a
production backlog design. No schedule or auto-requeue of completed work is
implemented. Configurable production cadence remains a future inactive contract.

## Actually executed here

Python3.12.14, pytest9.1.1. Existing pinned dependency preflight passed, including
psycopg3 and libpq imports. Forty-two offline tests passed with no failures,
errors or skips:15 adapter/boundary cases +27 accepted reference-model cases.
Seventeen native tests COLLECTED ONLY; none executed or counted as passes/skips.
This runtime has no existing PostgreSQL binaries. No installation retried.

The Idox document path calls existing _find_document_links on synthetic
Idox-shaped HTML. No saved genuine portal HTML captures were found under tests.
Relationships consume synthetic parsed response records: actual browser search,
pagination parsing and reference verification are NOT integrated or validated.
Focus chain/Hyde negative controls therefore remain bounded synthetic evidence.
No source counts are extracted from fixture prose or promoted to operative truth.

Native tests cover all/absent/partial migration composition, rollback,
wrong-scope rollback, duplicate response, unchanged bytes with new observations,
changed bodies, immutability, same-connection recovery, reservation concurrency,
owner mismatch, unresolved owner, exited-process identity successor fixture,
frontier scope and finite stage deferral. The successor test uses a real exited
process identity but constructs its stored reservation; it is not a full
kill-during-fetch end-to-end process test. Broader crash fault injection and a
mixed full pipeline/council/new-discovery admission walkthrough remain gates.

## Guarded WSL verification

run.py/inside.py/bootstrap.py are a separately scoped derivative of the accepted
AH isolation runner. Unchanged shared cluster provisioning and dependency setup
are reused; AH migration/catalogue verification is not broadened. Native tests
apply the canonical revisit schema in the runner-created restricted-role case
DB after existing Base prerequisites. No alternate DDL or guard monkeypatch.

Transfer bundle bootstrap verifies checksums and exact commit/clean tree, rejects
inherited database/model inputs and environment files, installs pinned packages
in a fresh venv, creates private OS namespaces and a disposable PostgreSQL16
cluster, and emits ONE revisit-postgres-results.tar.gz. Cluster identity and role
checks precede schema work. Shutdown failure fails the runner. Inspect returned
archive before any native acceptance. Missing prerequisites remain BLOCKED.

## Remaining gates

Native archive inspection/repairs first. Then genuine recorded portal adapter
captures, full child execution with reviewed non-production engine wiring,
crash fault injection and finite mixed-workload integration. Merely running after
ordinary discovery preserves its precedence but does not prove revisits cannot
be starved by long existing stages. Stronger fairness requires review of those
stage allocations without changing P0-A owner/admission or deadline guarantees.
No production throughput/cadence is measured. Production schema/privileges,
P0-A release/identity activation, approved live trial and buyer-source review are
separate gates. Stored matching refresh remains deferred.

## First WSL archive and repair

See WSL_REVIEW_20260930.md: the initial17-case native run had3passes,2failures
and12setup errors, with no skips. All failures stopped at the same check-expression
comparison. The revised comparison has49offline passes and20native cases prepared;
the latter require a new guarded WSL run. Earlier collection-only statements above
describe the original checkpoint and are superseded by that inspected evidence.
