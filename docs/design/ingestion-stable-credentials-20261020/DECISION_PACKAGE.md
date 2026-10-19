# Stable restricted credentials — reviewed candidate and single production proposal (preparation only; nothing here is authorised or run)

Stage 4 remains OPEN. Storage remains accepted. This is the offline implementation and disposable validation of **provisioning plus qualification only**. No live provisioning has been done and **no standing-access risk is accepted by this document**. PR #150 (direct route) is preserved unchanged; the Pro upgrade, IPv4 purchase and Render changes are not part of this. All consumed authorities (audits PRs #142, #145, #148), stops and IDs 1504–1508 are preserved. Scheduling and operational activation remain held.

## 1. Candidate
| Item | Value |
|---|---|
| PR | #151 (draft), branch `stage4/stable-credentials-20261020`, **stacked on PR #150** (`stage4/direct-route-20261020`, which stays preserved; its direct-route code is dormant — no registration selects it) |
| Tested code state | `85014b4490e0eb3dfc23abdea82573a48a5eb64c`, tree `1f0113821572d7e8b9b68af35792ea9e85f8419a` (later commits on the branch are documentation only; the grouped provisioning → qualification → revocation handoff is `HANDOFF.md` in this folder) |
| Hosted checks at exactly that head | all pass: offline (three jobs), native, postgres-admission, restricted-provisioning (disposable PG17 rehearsals), web |
| Review | full independent review (D1–D7, F1–F2), re-reviews of the receipt/cancellation corrections, and a focused review of the final cancellation fixes; exact-head hosted validation as above |

## 2. What was built
1. **Owner provisioning** (`STABLE_CREDENTIAL_PROVISIONING`, administrative credential at the hidden prompt): restores and **keeps** the two capability memberships and the three role-level timeouts; sets a fresh password on each restricted login with `VALID UNTIL` = now + **90 days**; stores two protected environment secrets; enables `LOGIN`; reads the standing state back; **does not tear down**. Any failure after the credentials exist runs the ordinary disabling path (rehearsed).
2. **Restricted-runtime qualification** (`stage4-stable-credential-qualification-once.yml` → `stable_qualification.py`, protected environment `stage4-production-canary`, restricted credentials only, no administrative credential, `contents: read`, single use by run number, pinned reviewed SHA): at most **3 attempts per login, 6 in total**; worker first, effect only after the worker qualified; the same credential for every attempt; a further attempt only after the **exact** `AUTHENTICATION_REJECTED` **and** verified client closure, after a fixed wait of **20 s then 60 s**; stops at once on TLS failure, unexpected identity/profile, uncertain closure (a successful attempt included), circuit-breaker indication (outranks any SQLSTATE), any other failure class, exhausted limits, the overall 330 s window (no attempt starts unless it can finish) or cancellation. No automatic extension; a second sequence is a new reviewed workflow.
3. **Privileged revocation** (`STABLE_CREDENTIAL_REVOCATION`): the ordinary teardown (NOLOGIN, NULL password, memberships revoked, bounded session policy, secrets deleted), tolerant of a partially disabled state and of secrets already removed; role-level timeouts are left in place.
4. A standing-state preflight and an owner package (renderer, owner script, manifest) for both ceremonies; the workflow is pinned by hash in the existing environment-exclusivity guards (no blanket exemption).

## 3. Access: what a valid login can do, with and without a grant
Established from the reviewed SQL and **exercised on the disposable server** (no grant / active grant / expired grant). "Visible binding hashes are not secret authentication factors": the worker can read the control row, which shows stops, expiries and bindings, and nothing in the design treats those values as secrets; the authorising factors are the database credential **plus** an owner-issued, unexpired, exactly bound grant and Bolton exception.
| | Worker login (`ingestion_worker_login`) | Effect login (`ingestion_effect_login`) |
|---|---|---|
| **Without a grant** | connect; **read** both ledger tables (incl. the control row); **raise a stop** (fail-safe pause, owner-cleared); every ledger operation is refused (nothing to act on, or the stop gate, `42501`); cannot INSERT/UPDATE/DELETE/TRUNCATE; cannot register grants/exceptions or read the owner-only control view | connect; **nothing readable** (no table privilege); every operation refused; cannot raise a stop |
| **During an active grant** (owner-issued, ≤ 24 h, one Bolton scope) | additionally: **claim** and progress the **granted keys** with the exact binding, login and owner name (tested: an authorised claim succeeds, a repeat is refused; wrong authority or wrong binding is refused `42501`); anything outside the grant, any direct table write, any grant creation remains refused | additionally: the broker operations (fence/resolve effect, enqueue child, batch row/reseal) **on granted keys within the exact batch plan**; wrong authority or binding refused; cannot use worker operations (`42501`) |
| **After the grant expires** | back to the no-grant column (tested on the same existing item: every operation refused at the stop gate, `42501`) | same |
| **Compromised credential could** | read the ledger/control row at any time; pause operations by raising a stop; **during an active grant** act as a worker inside that finite grant (e.g. mis-progress that scope's items until the grant expires or the owner raises a stop) | nothing at any time without a grant; **during an active grant** broker-type changes within the granted batch plan |
| **Cannot, ever** | write application/B2 data, create or widen a grant, register an exception, read passwords or owner views, act on an ungranted key, use broker operations | read the ledger, claim work, raise a stop, create grants, write tables |
Not re-proved here: the full positive semantics of every operation inside a grant (accepted storage acceptance covers them).

## 4. What the restricted runtime can and cannot verify
It reads only what a login may read about itself: its role row, memberships, privilege-inquiry results, remaining validity (≥ 7 days required), and — for the worker only, informationally — the control row. **Owner verifications** (listed in every result): no other sessions of the two logins; the password state and exact `VALID UNTIL` on the server; no unexpired grant for the effect view; server-side closure of the qualification sessions. No monitoring privilege is added to obtain these.

## 5. Failed qualification, retained access, emergency revocation
A failed qualification **blocks use** (result `use_blocked`, non-zero exit) and states `BOTH_LOGINS_REMAIN_ENABLED_UNTIL_THE_OWNER_RUNS_THE_PRIVILEGED_REVOCATION`; the runtime cannot disable anything (and, when authentication itself is what failed, could not even raise a stop). Revocation, session termination and recovery are the privileged owner path above; uncertain outcomes follow the existing rule (they block continuation and need reconciliation).
| Event | Response |
|---|---|
| Qualification stopped (any reason) | owner reviews the artifact; revocation ceremony if the credentials are not to stay enabled; no automatic retry |
| Suspected leak | revocation ceremony (disable first; sessions resolved or reported; secrets deleted); new provisioning is a new decision |
| Expiry reached | new logins fail; **existing sessions continue** (expiry is not termination); revocation ends them |
| Uncertain provisioning/revocation | `STOP_RECONCILE_NO_RETRY`; read-only diagnostics; owner reconciles before anything else |

## 6. Validity and renewal policy (proposed)
- **Initial validity 90 days.** Qualification refuses credentials with < 7 days left, so any later execution decision would be blocked in the last week.
- **Renewal = extend `VALID UNTIL` only** (no password change, no secret change, no pooler credential change, so no repeat of the rotation cache problem): a small owner ceremony, **to be prepared as a separate step before the first renewal is due (reminder at 14 days)** — it is not part of this candidate.
- **Rotation (new password, new secret, new qualification)** only on suspected compromise, a change of secret store, or an annual review — not monthly.

## 7. Secret locations and permissions
`INGESTION_WORKER_DATABASE_URL`, `INGESTION_EFFECT_DATABASE_URL`: protected environment `stage4-production-canary` (write-only; values readable only inside a pinned workflow job; never printed, never in the audit, artifact or result; tested). The administrative migration credential is never stored by this design (hidden prompt in the owner's terminal only). **Disclosed residual:** the same environment also holds the existing administrative `DATABASE_URL` used by other hash-pinned workflows. The qualification job references only the two restricted secrets (tested statically), but separating the restricted secrets into their own environment is a recommended later hardening (it needs a code change to the secret writer and an owner step).

## 8. Single production proposal (one grouped decision; nothing is released)
1. **Integration:** PR #150 then PR #151 as guarded `[skip render]` commits with the same reconciliation as before (combined-tree and executable-hash reconciliation, required checks). #150 is dormant code (no registration selects the direct route); the alternative is to re-cut #151 on `master` without it at the cost of repeating the verification.
2. **Provisioning registration:** one fresh registration (≤ 110 minutes) for `STABLE_CREDENTIAL_PROVISIONING`, bound to the integrated revision and the three consumed predecessors; owner ceremony in the owner's visible terminal (administrative credential at the hidden prompt). Finite administrative budget ≤ 60 commands / 6 connections before teardown, ≤ 92 / 8 including the failure path, ≤ 104 with diagnostics (measured: success 50 commands / 4 connections; failure path 75 / 7; revocation 21 / 2). Hidden input 120 s, active 270 s, outer 420 s, backstop 450 s.
3. **Qualification:** one dispatch of the single-use workflow (environment approval, authority input, reviewed SHA), ≤ 6 attempts, ≤ 330 s (job limit 8 minutes), spacing 20 s then 60 s. **Pass:** both logins connect once over verified TLS, identity/flags/timeouts and the self-visible profile match, validity ≥ 7 days, closure verified. **Fail:** any stop reason above; revocation ceremony on the owner's decision.
4. **Not released by a pass:** no grant, exception, source request, queue row, application write, scheduling or activation; an execution mode and its authorisation ceremony are separate decisions.
5. **Decisions needed:** (a) accept the standing-access risk of section 3 for these two logins for up to 90 days, and re-bind the reviewed possible-SCRAM-verifier-retention acceptance to this standing credential pair; (b) accept the shared-environment residual (section 7) for the initial qualification or require separation first; (c) choose the #150/#151 integration option; (d) confirm the 90-day validity.
6. **Costs and owner involvement:** no subscription change or purchase; one provisioning ceremony, one workflow dispatch with environment approval, a renewal about every 75–90 days (prepared separately), rotation at most annually.

## 9. Remaining uncertainties
Whether initial authentication through the shared pooler works at all (stable credentials do not prove it; the qualification exists to find out, within its limits); the pooler's cache semantics; the environment-sharing residual; and that the full operational semantics inside a grant are covered by the accepted storage tests rather than by this candidate.
