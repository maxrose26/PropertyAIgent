# Native PostgreSQL rehearsal candidate — inactive

This package is executable preparation, not executed PostgreSQL evidence. No native pass, production readiness, publication or workflow dispatch is claimed. Accepted AH consumer tests are not reopened. Application runtime and existing migration draft 001 remain unchanged.

## Scope and execution after separate approval

The workflow is stored here as `native-postgres.workflow.yml`, outside `.github/workflows`, because publication and execution are not approved. It is manual-only and rejects every ref except `refs/heads/verification/ah-native-ci`. A reviewed publication/dispatch mechanism is still required: GitHub manual dispatch normally requires the workflow to be present on the default branch. This package does not authorise changing master or silently adding a push trigger. [GitHub documents this dispatch requirement](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow). Resolve that publication boundary before execution (for example a separately approved workflow-only default-branch addition, with job execution still restricted to the rehearsal branch). No workflow has been published.

After that decision, publish the reviewed candidate without changing its code tree; record the published SHA. Dispatch only the rehearsal branch. The runner checks `GITHUB_SHA` and a clean checkout, validates candidate hashes, rejects inherited database/model inputs and repository environment files, and completes pinned driver installation before connecting. It does not load repository environment files or application model clients.

The job creates a PostgreSQL 16 service with disposable fixture credentials, loopback-only random host port, and no host bind mounts. The runner verifies the exact job service container ID, image ID, startup time, bootstrap identity, PostgreSQL system identifier and postmaster start before creating any schemas. Every subsequent connection rechecks identity and the runner-created database OID. Arbitrary DSNs, hosts, database names and roles are not accepted. The image tag is version-major pinned; the resolved immutable image ID and exact PostgreSQL version are recorded. Repeatability across future image updates is not claimed.

Four randomly named databases belong to an unprivileged migration owner. Runtime roles lack ownership, SUPERUSER, BYPASSRLS, CREATE ROLE and CREATE DATABASE. No Supabase or production credentials are used. Parent applications/sites/documents are minimal labelled synthetic FK fixtures, not copied production records. No real claims are imported.

## Exact artifacts and verifier

`003_ci_candidate.sql` incorporates the unchanged canonical table/constraint/index/append-only DDL from 001, then adds fixture-role grant/default-grant hardening. It is deliberately CI-only and is NOT the production migration artifact. `candidate_contract.json` binds every executable/schema/security artifact by SHA256. The reference database is independently instantiated from `expected_schema.json` plus `reference_security.sql` and the reviewed security contract, never learned from target state. The generated bound expected JSON records its reference catalogue hash and database version.

`native_exporter.py` reads all 13 catalogue sections: relations; columns including type/default/nullability; constraints; indexes; sequences; dependencies; triggers; functions; policies; expanded ACL including column/schema access; default ACL; roles; memberships. Unexpected public AH objects remain visible. Internal PostgreSQL FK trigger numeric names are normalized by constraint/function identity; user trigger identities and substantive definitions remain strict. Normal snapshots use repeatable-read/read-only transactions. Deliberate drift probes use explicit repeatable-read writable transactions and roll back, with the exporter itself still issuing SELECT only.

The comparator checks complete section equality and reference/migration/DDL hashes. Missing/extra objects, grants, policies, protections and definitions fail. A matching second install is deliberately rejected by the migration with the existing-schema message; the unchanged catalogue must still pass afterward. No idempotent migration no-op is claimed.

## Rehearsal cases and evidence

The runner exercises fresh install, partial install rejection, second-run rejection without damage, altered definitions/constraints/indexes/triggers/RLS/grants/defaults, tampered hashes, named-role default grants, dark-state denial, fixture-only bounded RLS read/append permissions, prohibited mutation/ownership/BYPASSRLS, append-only triggers, and evidence-preserving disable.

Raw SQL synthetic review events demonstrate database storage/append permissions only. They do not rerun or establish importer/reviewer application transition semantics, selected-claim projection correctness, or production reader activation. The fixture reader can see only site/application 1; this is not a production reader policy.

Disable first demonstrates that an in-flight writer prevents an exclusive lock within the bounded timeout. It rolls that fixture transaction back, acquires locks, revokes access, verifies denied reads/writes and identical evidence counts/hashes. Production requires draining or explicitly handling already-running transactions before declaring disable complete; revocation alone cannot retract an already-authorised statement.

Evidence includes versions, image/cluster identity, artifact hashes, reference and actual catalogues, bound expected schema, verifier, case results, permissions, append-only, drift/repeatability, disable counts/hashes, overall result, cleanup and file checksums. Failures stop acceptance and still upload available artifacts. Databases are dropped in `finally`; the workflow always stops the service and uploads evidence. Hosted job status AND cleanup evidence must pass; an earlier overall JSON alone is insufficient. Service-stop evidence is produced after runner checksums and is not covered by that runner manifest.

## Readiness decision

| Area | State | Blocker / next approval |
|---|---|---|
| Production migration | Not ready | Execute and inspect native rehearsal; then inspect actual Supabase role/default-grant/RLS contract and production parent identities/types under separate read-only authority. CI fixture role names are not Supabase proof. Review exact production migration separately. |
| Controlled cohort import | Not ready | Resolve new Focus production Document identities, approved registrar operation, reviewer identities and immutable manifest. No automatic backfill or synthetic import. |
| Reader activation | Not ready | Reviewed cohort allowlist, actual selected projection/RLS, cache invalidation and disable acceptance. Readers remain off. |
| Web deployment | Not ready for this increment | No runtime changes or deployment artifact prepared; future exact web release decision remains separate. |
| OpenAI extraction/verification | Not ready / intentionally disabled | No model calls. Future proposed-only extraction, budgets and independent review require separate approval. |

Next decision: review this executable candidate and resolve its workflow publication/dispatch route, then authorise one disposable native run. Production migration is not the next approval. Production import, reader activation, web deployment and OpenAI enablement each retain their own approval boundary. Discovery remains untouched; no claim of a fresh Render inspection is made.
