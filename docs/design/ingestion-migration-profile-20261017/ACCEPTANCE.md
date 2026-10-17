# Migration contract correction — Stage4 OPEN

This correction permits offline/disposable validation and guarded integration only.
No live query, provisioning, rerun, credential/permission change or scheduling is
released. A prepared successor binding is not permission to execute it.

## Exact account contract

Accepted original run38907801607/number1/attempt1, evidence
b48769539effa9e209f79cd392120e7919c5bc07, result path
`docs/design/ingestion-storage-tls-preflight-result-20261016/result.json`, records
SQL postgres, rolsuper=false, rolcreaterole=true, rolcreatedb=true,
rolbypassrls=true, rolcanlogin=true, rolinherit=true, rolconnlimit=-1.
The controller had incorrectly demanded migration NOBYPASSRLS. This does not
justify changing a role or using stronger access. Preserve exact current/session
identity postgres, non-superuser and the accepted four capability flags. Do not
infer a fresh tuple from the failed attempt's39returned bytes.

One bounded SELECT records allowlisted identity fields BEFORE evaluating them and
groups PostgreSQL17, schema USAGE/CREATE WITH GRANT OPTION, database CONNECT WITH
GRANT OPTION, unused fixed role names and absent fixed ledger objects. Any drift
stops before install.sql. Unexpected values are not dumped into evidence.

The reviewed installation, activation, revocation and readback SQL are unchanged.
Runtime logins remain NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOBYPASSRLS, with exact
non-administrative memberships and no owner/issuer/barrier-releaser membership.
The migration principal's existing administrative boundary is not worker access.

## Complete rehearsal

Use PostgreSQL17, representative non-superuser CREATEROLE/CREATEDB/INHERIT/BYPASSRLS
migration fixture, real restricted logins and the exact same controller phases.
Real Linux gh executes user/metadata checks, public-key retrieval, sealed-secret
PUT, DELETE and absent-name LIST against an isolated HTTPS loopback GitHub API
fixture. It receives a disposable authentication sentinel and a fixture CA with
hostname verification; no production host, account, token, secret or TLS setting
is used/changed. API store accepts ciphertext only and never logs request bodies.
Only external transport/auth/store are fixtures; actual gh process, encryption,
stdin custody, SQL, supervision, accounting, resource limits and phase ordering
are exercised. These tests cannot prove production GitHub write permission.

Preserve the existing focused interruption/uncertain-COMMIT/secret-operation and
memory enforcement tests. Add negative identity/type/capability and grouped
prerequisite tests, real missing-grant-option denial before installation, and
BYPASSRLS/admin/owner/issuer/releaser drift denials before password mapping.
No new extractor, source adapter, queue or infrastructure capability is added.

## Both consumed attempts and cumulative allowance

1. Registration802a4eae09ec897c1cc9c27704abeb9f6913eaeb919252ed64e98a452a055279,
   audit1573bytes SHA256f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0,
   .11050213100043038s,0DBconnections, historical cleanup UNCERTAIN.
2. Registrationcfc38625cca22de33d973f42851d3ea908d0b35f2a9e2ccc7e7000e52b42b082,
   audit7005bytes SHA2565dda1e97c8dfc2a9a899c839e9c60d88f3c08bff05d5172579ad2efe1ade279e,
   1.1728088340005343s,1DBconnection,4commands,.26088705100028164DBactive seconds,
   39returned data-value bytes; connection_closed acknowledged, no install.sql,
   memory group empty/removed, no reported survivors; historical cleanup UNCERTAIN.

Both exact owner files are required before successor credential input. Neither
latch/file is renamed or removed. New fixed successor latch is distinct. Original
expiry remains2026-10-18T08:54:58.469465Z (18October09:54:58BST), enforced in code.

Remaining total:238.71668903499903supervised seconds;12of13DBconnection attempts;
provisioning phase retains the earlier1.2833109650009647s and1connection spend.
Budget counters start at prior1connection/4commands/.260887051active seconds/
39returned bytes. Storage/teardown retain existing limits/reserves. Kernel256MiB
from-exec memory bound unchanged. Combined2MiB exports conservatively reserve16KiB
for both preceding audits/results, retaining32KiB closure reserve. A new process,
registration or artifact never resets spend. Data-value bytes are not wire bytes.

## Grouped production prerequisites and recovery disposition

| Requirement | Retained evidence / remaining live condition |
|---|---|
| Existing endpoint, CA, verify-full, migration account | Accepted TLS/catalogue and owner connection; no route/credential change. Exact current flags must still match future safe readback. |
| Secure owner GitHub authentication and WSL kernel containment | Owner verified keyring/account/environment access and actual from-exec cgroup closure. Reuse; do not restart sign-in. |
| Grant options, role/object absence, ownership transfer | Grouped catalogue gate then unchanged transactional install checks. Actual grant options were not measured by the consumed four-statement attempt. No successful production installation is claimed. |
| Ambient/public permissions and exact statistics exception | Existing reviewed activation gate, read-only before generating passwords; never broaden an exception or alter shared PUBLIC grants. Disposable checks are not proof of current production ACLs. |
| Protected-secret write/delete capability | Real gh/API-shape rehearsal; actual protected-store operation remains a finite authorised production condition, not proven by metadata read access. No overwrite of pre-existing test secrets. |
| Teardown | Exact SQL/commit acknowledgement, NOLOGIN/membership/session readback, exact secret deletions/name absence, sockets/process/cgroup closure. Any ambiguity stops without automatic repair. |
| Prior cleanup classification | Both remain UNCERTAIN. Positive connection_closed and empty owned worker group are narrower facts, not retrospective CLOSED. No provisioning/secret/install/seed commit was attempted, so there is no uncertain persistence to reconcile through a new live write/query. REVIEW must accept a scoped successor without erasing historical uncertainty before another execution. |

All remaining production conditions are explicit gates, not claimed outcomes.
No further live diagnostic loop is requested. If current production prerequisites
fail, report their safe grouped evidence and stop; no replacement observation.
A future owner-local command must use the exact integrated controller, reviewed
unused successor and existing hidden-input mechanism, only after execution is
specifically released. No production command is run by correction validation.

Preserve IDs1504–1508, Salford stop, historical evidence and all held scopes.
Storage acceptance remains separate from pipeline readiness/backlog completion.
