# HANDOFF — stable restricted credentials: grouped handoff: provisioning → qualification → failure revocation (prepared; nothing here is released)

Boundary: no registration is released, no credential has been changed, no workflow has been dispatched, nothing is scheduled and no source has been executed. **No ingestion grant, exception, source request or application write may be issued from this milestone.** Accepted storage, all historical authorities and stops, and IDs 1504–1508 are untouched. Stage 4 remains OPEN. Production provisioning and acceptance of the standing-access risk stay unreleased until this package is reviewed and approved.

Design decisions in force: the existing protected environment `stage4-production-canary` is used for the initial qualification; its shared-environment limitation (it also holds the administrative `DATABASE_URL` for other hash-pinned workflows) is accepted **for this test only** and the qualification job references only the two restricted secrets (tested statically and by the hash-pinned guards); the two capability memberships and the reviewed role-level timeouts are retained; initial validity is a **maximum of 90 days**; there is no automatic renewal and no automatic rotation; PR #150's dormant dependencies are integrated with PR #151 after final validation (this does not authorise the direct-route diagnostic, the Pro upgrade or the IPv4 purchase).

## What `use_blocked` means
`use_blocked: true` is a **qualification result** in the job's artifact and exit status. It is not a durable database barrier: both logins stay enabled (`LOGIN`, valid password) until the owner runs the privileged revocation, the control row is not changed, and the restricted runtime has no privilege to change either. Every result states this (`use_blocked_semantics`) together with `grant_may_be_issued_from_this_milestone: false`. The protection that remains in place regardless of the result is structural: with no owner-issued grant, neither login can mutate anything.

## Step 1 — Provisioning (owner terminal; administrative credential at the hidden prompt)
| Item | Value |
|---|---|
| Mode / authority / namespace | `STABLE_CREDENTIAL_PROVISIONING` / `AUTHORISE_INGESTION_STABLE_CREDENTIAL_PROVISIONING_ONCE_20261020` / `operational-stable-provisioning-once-20261020` |
| Registration | one fresh registration, rendered from the integrated revision and the current evidence-branch head, expiring within 110 minutes; binds the three consumed predecessors by hash |
| Secure owner input | the owner's own visible WSL terminal; private-keyring GitHub sign-in, then the owner script; the migration credential is typed only at the 120-second hidden prompt (never an argument, file, environment variable or chat); the generated passwords are never printed or written to a file |
| Effects | restore and keep the two capability memberships; set the three role-level timeouts (`10s`/`3s`/`20s`) and keep them; fresh password on each login with `VALID UNTIL` = provisioning time + **90 days (maximum)**; two protected environment secrets; `LOGIN` enabled |
| Limits | administrative ≤ 60 commands / 6 connections before teardown, ≤ 92 / 8 through teardown, ≤ 104 with failure diagnostics (measured: success 50 / 4; failure path 75 / 7); hidden input 120 s, active 270 s, work alarm 215 s, outer 420 s, backstop 450 s |
| In-run readbacks (privileged, performed by the run) | both logins: `LOGIN` true, password present (boolean only), connection limit 1, no privilege-bearing flag, `VALID UNTIL` set; memberships exactly one capability each; role settings present; the three secret names present in the environment; control row untouched (asserted in the rehearsal) |
| A failure | any failure after the credentials exist disables them (NOLOGIN, NULL password, memberships revoked, settings restored, secrets deleted) and reports `STOP_RECONCILE_NO_RETRY` |
| **Owner verifications still required afterwards** | (a) no sessions of the two logins; (b) no unexpired grant in the control row and the stops intact; (c) the exact `VALID UNTIL` date recorded in the audit. The run does not read sessions: that needs monitoring privileges the migration identity has not been shown to hold |

## Step 2 — Qualification (GitHub Actions, protected environment, restricted credentials only)
| Item | Value |
|---|---|
| Workflow | `stage4-stable-credential-qualification-once.yml`, `workflow_dispatch`, inputs: `reviewed_sha` (= the integrated `master` commit) and the authority `AUTHORISE_INGESTION_STABLE_CREDENTIAL_QUALIFICATION_ONCE_20261020`; single use (`GITHUB_RUN_NUMBER` = 1, attempt 1, `master`); environment approval |
| Credentials | `INGESTION_WORKER_DATABASE_URL`, `INGESTION_EFFECT_DATABASE_URL` only; `contents: read`; no administrative secret referenced; clean environment (`env -i`), administrative variables refused |
| Attempts | ≤ 3 per login, ≤ 6 total; worker first, effect only after the worker qualified; same credential every attempt; next attempt only after the exact `AUTHENTICATION_REJECTED` **and** verified client closure, after 20 s then 60 s; stop on TLS failure, unexpected identity/profile, uncertain closure (success included), circuit-breaker indication, any other class, exhausted limits, the 330 s window, or cancellation |
| Enforced limits | `timeout` 345 s (module hard window 330 s, no attempt starts unless it can finish); job timeout 8 minutes; `ulimit`: core files 0, open files 64, file size 4 MiB, address space 3 GiB (proved to import, build its engine and start a TLS client under exactly these limits in CI). **Not enforced:** a cgroup RSS cap or network egress control on the hosted runner. Output is bounded by code (one JSON line on stdout; audit journal ≤ 1 MiB; progress ≤ 256 KiB) |
| Evidence | artifact (30 days): `events.jsonl` with one event per attempt carrying its **complete credential-free budget receipt**, `progress.json` (cumulative accounting after every attempt, survives a kill), `final-result.json` |
| Cancellation and kills | SIGTERM/SIGINT (a workflow cancel) are handled cooperatively: the handler only records the request and raises inside the waiting, preparation and connection regions; closing the budget, recording the attempt and publishing `final-result.json` are never interrupted, so a catchable request after an attempt started still leaves its complete record and the final result. **An uncatchable kill (SIGKILL, the 345 s timeout kill, runner loss) cannot be handled**: then only the per-attempt events and `progress.json` written so far exist, `final-result.json` is absent, and that absence means the outcome is UNKNOWN and requires the revocation step. No final result is promised after such a kill |
| Accounting | per attempt and cumulative: connection attempts, driver commands, returned database-value bytes, connection active time, cancellation outcomes, hard-deadline events, client-closure evidence. Every value carries a basis: `MEASURED`, `NOT_STARTED`, or `LOWER_BOUND_ONLY_SOME_RECEIPT_UNKNOWN`; an attempt counts as started before anything can interrupt it; an unreadable receipt, a cancellation or a preparation failure is never a measured zero or a verified closure; **absence of `final-result.json` means UNKNOWN** (the per-attempt events and `progress.json` remain) |
| Closure vs server verification | closure is the **client-side** budget receipt only; `server_session_verification` is always `NOT_PERFORMED_BY_THE_RESTRICTED_RUNTIME_OWNER_VERIFICATION_REQUIRED` |
| Pass | both logins connect once over verified TLS; identity, flags, effective timeouts, one capability membership, no privileged membership, no direct DML privilege, the effect login cannot read the ledger, ≥ 7 days validity; closure verified for every attempt. **A pass authorises nothing further** |
| Owner verifications after the run | no sessions of the two logins remain (server-side closure); exact `VALID UNTIL`; control row unchanged |

## Step 3 — Failure → privileged revocation (owner terminal; administrative credential at the hidden prompt)
Run after any `QUALIFICATION_STOPPED` or `CANCELLED` result, after a suspected leak, or whenever the owner decides to end standing access.
| Item | Value |
|---|---|
| Mode / authority / namespace | `STABLE_CREDENTIAL_REVOCATION` / `AUTHORISE_INGESTION_STABLE_CREDENTIAL_REVOCATION_ONCE_20261020` / `operational-stable-revocation-once-20261020`; fresh registration ≤ 110 minutes |
| Effects | `NOLOGIN`, NULL password, memberships revoked; bounded session policy (up to 3 session reads, at most two exactly identified terminations, only with proven existing privileges; otherwise **reported as unresolved, never closed**); the two secrets deleted if still present; role-level timeouts left in place; tolerant of a partially disabled state |
| Limits | administrative ≤ 60 / 92 / 104 commands over ≤ 6 / 8 connections (measured: revocation 21 / 2; with an unresolved session 31 / 3) |
| Readbacks | roles `NOLOGIN` and NULL password, no memberships, secret names, session disposition (`NONE`, `CLEARED_BY_WAIT`, `TERMINATED_VERIFIED_ABSENT` or an explicit `UNRESOLVED_*` stop) |
| Owner verification | no sessions of the two logins if the disposition is unresolved; expiry never terminates a session |

## Expiry and what is not automatic
`VALID UNTIL` is at most provisioning time + 90 days. Expiry stops new logins only. There is **no automatic renewal and no automatic rotation**; extending expiry or rotating the password would each be a new reviewed ceremony. Qualification refuses credentials with fewer than 7 days remaining.

## Consolidated numbers
Administration ≤ 60 / 92 / 104 commands, ≤ 6 / 8 connections (per ceremony); qualification ≤ 6 connection attempts, ≤ 3 per login, spacing 20 s / 60 s, ≤ 330 s, ≤ 345 s process kill, ≤ 8 minute job; hidden input 120 s; backstop 450 s; GitHub requests per ceremony within the existing bound; cost: none.
