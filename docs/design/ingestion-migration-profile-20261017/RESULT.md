# Migration contract correction — integrated, rehearsed, held

PR125 candidate `3fc9255a3d0f58616bc65db9b0ef7ee78d961894`, tree `68bf766cda023b1f15a19a63978903995391ec46`, integrated at `7cf8d32547b63d485de872afc2f717c3dce55322` with guarded expected-head update and [skip render]. All9candidate and7post-merge checks passed. Independent candidate, registration and owner-handoff reviews passed. Evidence predecessor013eb1c820e1634197604a5818d648c9c678387b is preserved.

## What changed

The migration-only postgres gate now matches the accepted immutable run38907801607 evidence: NOSUPERUSER, CREATEROLE, CREATEDB, BYPASSRLS. This does not change a production role or grant stronger access. A safe identity/prerequisite event precedes evaluation; exact current/session identity and flag drift stops before installation. The one catalogue SELECT also checks PostgreSQL17, schema/database grant options, unused fixed roles and absent ledger objects.

Restricted logins remain NOBYPASSRLS without owner/admin/issuer/barrier-releaser membership. All installation/activation/revocation/readback SQL, writers, endpoint, CA and verify-full are unchanged.

## Complete disposable proof

-42local focused tests;21restricted PostgreSQL tests;10native tests including the entire actual-gh controller. Negative cases cover identity/type/flag drift, missing grant options, worker BYPASSRLS, operator CREATEROLE, owner/issuer/releaser membership; existing interruption and uncertain-effect cases remain covered.
- Full supervised controller: installation and committed readback → actualgh encrypted mapping → activation →3blocked items plus control → duplicate no-op/reconnect/readbacks/8permission denials → revocation/secret deletion/absence → CLOSED cleanup.
- Complete real-gh run:1.3627368899999937fresh supervised seconds;2.6460478550009583including carried prior spend;106814audit bytes;outer kernel peak27041792bytes;sampled owned RSS127053824bytes. These are distinct counters, not interchangeable memory claims. No max/OOM/OOMkill events, no forced cleanup, populated0, group removed, zero reported owned survivors.
- SQL/controller accounting rehearsal separately measured138cumulative driver commands and8cumulative connections, including prior4commands/1connection;40storage commands/4storage connections;10teardown commands;9452returned database data-value bytes. Its substituted secret boundary is distinct from the full actual-gh supervised proof. Actual production helper additionally enforces its accepted principal check; fixture measurements are not an exact production usage promise.
-10loopback HTTP requests include1fixture-setup GET and9controller requests. The isolated fixture uses synthetic auth and its own CA; actualgh performs public-key lookup, sealed-box encryption,2PUTs,2DELETEs and absent-name listing. It does not establish production secret-store write permission.
- Independently ran officialgh2.45.0 (matching owner version), verified release checksum79e89a14af6fc69163aee00e764e86d5809d0c6c77e6f229aebe7a4ed115ee67, synthetic upload/delete/absence under RLIMIT_FSIZE0. This standalone test is separate from the complete hosted PostgreSQL proof.

Original PostgreSQL artifact12109896385, run39057031218/number178/attempt1, SHA2563103174be027947eefa1201f81d3f2b4c971de9c070fd08a292e199819ffd68e is archived unchanged. Native artifact12109474550, run39057031217/number209/attempt1, SHA2560c5db3d66b565907d8663f502a7e11a261b64b1b304208d087c4aef1e910c518 is also archived. These are offline CI runs, not production attempts.

## Successor and remaining allowance

Prepared unused registration SHA256`43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3`,3779bytes, binds integrated revision and all13reviewed file hashes. Both consumed registrations/audits and their UNCERTAIN classifications remain unchanged. Distinct successor latch; no old file is deleted, renamed or reused. Original expiry remains18October2026 08:54:58.469465UTC (09:54:58.469465BST).

Remaining238.71668903499903supervised seconds and12connection attempts; prior4commands/.26088705100028164DBactive seconds/39data-value bytes carried forward.256MiBfrom-exec kernel bound/swap0, unchanged phase/closure reserves,2MiBcombined exports with16KiBprior reservation. No process/artifact/registration reset. Returned data-value bytes are not total network traffic.

## Exact hold / grouped prerequisites

No production query, provisioning, mapping, storage test or teardown was executed by this correction. Production storage acceptance remains NOT_RUN. The current instruction explicitly forbids a live query/provisioning/rerun.

The specific remaining decision is release of this exact successor while retaining both historical UNCERTAIN classifications. The prior attempts stopped before installation/password generation/secret mapping/seed effects; the second acknowledged native DB closure and an empty/removed owned group. These facts do not retrospectively establish CLOSED. No uncertain provisioning/seed/secret commit is being concealed or automatically repaired.

Current grant options, role/object absence, exact flags, ownership transfer and ambient permissions remain grouped controller gates. Existing keyring metadata access does not prove future secret write/delete access. Any failed gate or uncertain effect stops without stronger credentials, scope expansion, compensation or replay. If expiry passes, report it; do not silently renew.

See OWNER-HANDOFF.md for the independently reviewed exact command, marked HELD. Preserve IDs1504–1508, Salford stop and all consumed historical authorities. Stage4 OPEN; storage acceptance, operational readiness and backlog completion remain distinct.
