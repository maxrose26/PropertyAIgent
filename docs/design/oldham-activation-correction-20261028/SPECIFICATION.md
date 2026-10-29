# Narrow activation correction (offline, inactive)

Baseline: fa0064aa111c55bf4f8be1e4d4216aa2fe2b529e / 03751b14fa23d260baad2d39de2ad7bf604e563a.

The owner reports two reconciliation findings: latent SELECT access to the two
provider statistics views, and no recovery login. Original failed receipts and
reconciliation classifications remain historical evidence, not rewritten results.

Only the explicitly selected capture/screening-only activation gate changes.
Absent recovery login is permitted because no recovery capability is invoked.
An existing recovery login must be NOLOGIN, unprivileged, and have only the
reviewed non-admin, inherit-only recovery membership. Existing recovery sessions
and orphaned session identities also refuse: NOLOGIN or a dropped role does not
terminate an already-authenticated session. Existing administrative session
visibility is required by Lifecycle.observed before this gate. Historical/admission gates
remain unchanged and still require recovery existence.

Reuse the storage ceremony's exact PG17 pg_stat_statements 1.11 latent-SELECT
boundary: two extension-owned views with reviewed definitions and no altered
options, no schema USAGE/CREATE, no monitor/all-statistics membership, no mutation
or grant options and no reset execution. ACL provenance is not assumed PUBLIC:
has_*_privilege and pg_has_role assess effective inherited access. This exception
accepts latent ACLs, not usable access to query text. Any actual schema access,
other version, lookalike or object change refuses before password generation.
No ACL is revoked or granted. Provider metadata is a mandatory future pre-effect
check, not established by the two reported view names.

Exact fixed PostgreSQL gate codes are translated locally only at the gate call;
unrecognised messages and codes remain unexported. Credential generation and
secret mapping remain strictly after successful gate execution.

The reconciliation control function was defined LANGUAGE sql SECURITY DEFINER,
with no volatility clause, hence authoritative volatility is VOLATILE ('v').
Correct the diagnostic expectation; never ALTER the production function to fit it.

No activation, authority cleanup, policy install or fresh timed registration is
part of this change. Cleanup and execution remain separate reviewed proposals.

## Explicit installed-policy successor (29 October delta)

`OLDHAM_CAPTURE_SCREENING_INSTALLED_V1` is a separate sealed package shape, never
automatically selected. It uses only the exact installed Oldham inventory and
post-retirement state. It binds original failed-result/audit and reconciliation
files, exact consumed authority/registration and reviewed role settings. It neither
calls Transition.retire nor Transition.install. The original mode is unchanged.

One cumulative owner clock/allocation includes explicit historical cleanup,
committed readback, fresh CAPTURE/SCREENING issuance, runtime and teardown.
Historical cleanup expires only the exact grant, sets only its allowance revoked,
removes only the two exact residual memberships and preserves history. Stored
expiry is observed; expiry alone never substitutes for revocation. Unknown state,
changed policy/stops/barriers, active sessions/secrets or uncertain effects refuse.
No compensation or replay. Original files are hashed and mode-observed, not edited.

Before any new work issuance, the gate validates the production-equivalent
statistics objects, effective rights and recovery state with the expected runtime
memberships. On cleanup readback those memberships are restored only in a rollback
transaction for gate validation. Later activation restores and validates them in
a single transaction before COMMIT, then mints credentials. No admission access.
