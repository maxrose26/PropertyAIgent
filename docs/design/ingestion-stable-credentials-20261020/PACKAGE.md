# Stable restricted credentials — release package (owner provisioning and revocation; restricted-runtime qualification; prepared, not released)

Aim: separate the provisioning of the two restricted logins from individual work executions. Credentials are provisioned **once** by an owner ceremony, stored in the protected `stage4-production-canary` environment, qualified by a finite restricted-runtime job, and revoked through a reviewed privileged path. A valid login does not authorise ingestion. Nothing is authorised by this package until the Product Owner releases it; no standing-access risk is accepted by it.

## Three separate things (kept apart)
1. **Provisioning (owner terminal, administrative credential at the hidden prompt)** — mode `STABLE_CREDENTIAL_PROVISIONING`. Restores and keeps the two capability memberships and the three role-level timeouts; sets a fresh password on each login with `VALID UNTIL` = now + **90 days**; stores two protected environment secrets; enables `LOGIN`. It does **not** tear down. Any failure after the credentials exist falls into the ordinary disabling path (NOLOGIN, NULL password, memberships revoked, settings restored, secrets removed).
2. **Qualification (GitHub Actions, protected environment, restricted credentials only)** — `stage4-stable-credential-qualification-once.yml` runs `stable_qualification`. No administrative credential, no write-capable token. At most **3 attempts per login, 6 in total**, worker first, effect only after the worker qualified; the same credential for every attempt; a further attempt only after the exact `AUTHENTICATION_REJECTED` **and** verified client closure, after a fixed wait of 20 s then 60 s; stops at once on TLS failure, unexpected identity/profile, uncertain closure (success included), circuit-breaker indication, any other class, or exhausted limits. Single-use by run number; no automatic extension.
3. **Revocation (owner terminal, administrative credential)** — mode `STABLE_CREDENTIAL_REVOCATION`: the ordinary teardown (NOLOGIN, NULL password, memberships revoked, bounded session policy, secrets deleted). Role-level timeouts are left in place.

## Validity and renewal
Initial validity 90 days. **Extending expiry** (`ALTER ROLE … VALID UNTIL`, no password change, no secret change, no pooler credential change) is a separate small owner action to be prepared before the first renewal is due (reminder at 14 days). **Rotating the password** (new secret, new qualification) only on suspected compromise, a change of the secret store or an annual review; it is not a monthly ritual. Expiry does **not** terminate existing sessions; revocation handles sessions.

## Ceilings
Administration (totals): ≤ 60 commands / 6 connections before teardown, ≤ 92 / 8 through teardown, ≤ 104 including failure diagnostics (measured on the disposable server: provisioning 50 commands / 4 connections; revocation 21 / 2; the failure path 75 / 7). Hidden input 120 s, active 270 s, outer 420 s, backstop 450 s. Qualification: ≤ 6 connection attempts, ≤ 330 s overall.

## Not authorised
Any grant, exception, source request, queue row or application write; scheduling or activation; live provisioning; acceptance of the standing-access risk (a separate decision).
