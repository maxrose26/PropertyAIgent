# Storage memory correction — ready checkpoint

Stage4 OPEN. Production storage acceptance NOT RUN; operational activation NOT authorised.

## Identities

PR124 https://github.com/maxrose26/PropertyAIgent/pull/124
Reviewed candidate023e352473cf5a6b2851eb0af18130f97de36dc0.
Tree258c35bf37859e9f5bfd4c453e2e953ba15e0ccf.
Guarded [skip render] integration dc8d266224097c35cc1475964b0fd7a54f31490e,
parents dd6a94c171c7658b5c699c526d19e345fa6bef7b and reviewed023e352.
Master readback/tree verified. All9 candidate checks pass; final postchecks in CHECKS.json.
Independent final code and successor-binding review PASS, see REVIEW.md.
No deployment, production DB/source access or credential operation performed here.

## Preserved failed attempt

Old controller registration802a4eae09ec897c1cc9c27704abeb9f6913eaeb919252ed64e98a452a055279
is CONSUMED_FAILED_BEFORE_DB, never reusable. Owner-supplied five-entry1573-byte
journal reconstructed exactly: SHA256f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0,
chainheadc65ed1b8cb338fe73e2cf28fad1a22ee0a0bcaebadb733c03f50c9643d6ac751.
Historical cleanup UNCERTAIN, zero reported survivors; no retrospective CLOSED.
0.11050213100043038s,58138624bytes peak owned RSS. Last checkpoint owner_access INTENT;
no DB connection, SQL, credential generation/mapping, activation or seed reached.
Normal owner gh account/environment metadata calls passed; only DATABASE_URL present.
Real owner gh under256MiB RLIMIT_AS failed to reserve Go page-summary memory.

## Correction / bounds

Require a dedicated unprivileged systemd user scope with memory.max268435456,
swap.max0,oom.group1 before Python exec. This covers supervisor, inherited
interpreter memory, worker and every descendant. No RLIMIT_AS; virtual reservation
is allowed. Retain separate sampled aggregate worker RSS checks. Kernel-charged
memory and sampled RSS are different metrics, neither is virtual size.

Outer and worker limit configuration/events checked throughout and before success.
Missing delegation or invalid limits stops before credential input/consumption.
Cgroup kill/populated=0/removal and existing process/socket checks govern closure.
An outer OOM may kill the supervisor too: no final JSON is then possible. Preserve
last durable intent and UNCERTAIN, no retry/compensation; reconcile SQL/secret
outcomes before any further mutation. Kernel process death proves no DB outcome.

Unchanged SQL/roles/TLS/endpoint/mapping/manifest. Prior time deducted: at most
239.88949786899957s more supervised time,13 DB connection attempts (zero spent),
256MiB memory,2MiB combined exported evidence (4096bytes conservatively reserved
for prior audit/result, unchanged32KiB closure reserve). Existing40 storage
commands,30 active DB seconds and phase/closure reserves unchanged.

## Focused evidence

Local27 focused checks PASS. Hosted run39053582473 / number165 / attempt1,
job117456913619, exact candidate023e352, offline/disposable only:
- Real non-root Linux gh startup from-exec scope: PASS, whole startup-scope peak
  73744384bytes, worker child peak55103488bytes, no max/OOM events, empty/removal.
- Deliberate excess while real gh waits on disposable loopback HTTP: whole scope
  killed; systemd Result=oom-kill and empty ControlGroup verified. No external API.
- Existing restricted SQL/failure-recovery15PASS,0fail/error/skip (one supervised
  test deliberately moved to focused kernel harness, not omitted).
- Focused controller/kernel10PASS,0fail/error/skip,1.473s; separate destructive
  OOM test invoked directly because it must kill the entire containing scope.
- Full storage worker .630712707s, sampled worker-tree RSS74997760bytes,
  CLOSED,0survivors,98078auditbytes. Its nested fixture child charge peak4984832
  and case-parent5001216 do NOT represent full harness resident memory. The whole
  focused harness was separately constrained by a from-exec256MiB systemd scope.
- Exact SQL sequence:7connections,134top-level driver commands,.064792642active
  DB seconds,9379returned data-value bytes,40storage/10teardown commands,0open.
  These are disposable fixture measurements; production identity SELECT adds a
  command counted at runtime. Returned data-value bytes are not network traffic.
- Exact3blocked+control,duplicate seed no-op,8real-role42501denials,0attempts/grants,
  original stop and protected application fixtures1504–1508 preserved.

Initial draft failed cgroup attachment because the test process lacked a common
ancestor delegation; corrected harness uses a private systemd scope and drops to
runner UID before Python. Broad pytest harness exceeded256MiB, so unrelated SQL
validation stays outside the focused production-controller scope. No production
ceiling increase, no hidden omission, and no claim that harness cost is runtime.

Artifact12108129841 ingestion-provisioning-disposable-023e352... originalZIP65249bytes,
SHA256a070a4bcd36a39170c80a033fab71eb1560b6b724342b35aaea66866e1c8fdd6.
Verified downloaded bytes archived here. provisioning.xml50411bytes SHA256
b4b83b2a22b1404c4411c2fcc0d35394c0f5e68bdc3957e08b59570edd937a0f;
kernel-memory.xml3572bytes SHA25670ef9414444f76ffc9a9052d2240c80157dda222e7d735db88a23d4402c04a0b.
Nested controller journal hashes/sizes are JUnit-recorded; individual original
journal bytes were not in hosted artifact patterns and are not independently
archived as originals. Do not conflate that with archived original XML/ZIP.

## Successor / owner gate

registration.json SHA256cfc38625cca22de33d973f42851d3ea908d0b35f2a9e2ccc7e7000e52b42b082,
13file hashes, integrated revisiondc8d266..., original expiry2026-10-18T08:54:58.469465Z
(18October09:54:58BST). UNUSED at publication. No expiry extension or budget reset.
Existing authority retained for exactlytwo reviewed logins and fixed storage test.
Original owner audit hash is mandatory before input. New fixed successor latch
storage-acceptance-memory-successor-20261017; never delete either latch to retry.

Owner must run the reviewed command in existing secure WSL TTY/keyring session.
Actual user-manager/memory delegation remains a fail-closed local prerequisite;
no sudo/root fallback. Existing virtual environment/dependencies reused unchanged.
Migration URL only through hidden input. No password/token/URL in command or chat.
Success requires STORAGE_ACCEPTED_ACCESS_DISABLED and CLOSED after exact readbacks,
revocation,password clearing,protected-test-secret removal and session reconciliation.
Any failure/ambiguous result stops. Do not dispatch/retry another operation.

No production storage outcome claimed. IDs1504–1508,Salford stop,historical evidence,
consumed authorities and all held scopes preserved. TicketSU-511198 remains open.
Storage acceptance is not operational pipeline acceptance or database catch-up.
