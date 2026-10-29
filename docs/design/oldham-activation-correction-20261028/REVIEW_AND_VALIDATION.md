# Review and validation record

Draft correction only. No production connection or mutation occurred.

Independent review found and corrected exact C-symbol/signature binding,
NULL-safe recovery exclusions, recovery column-SELECT checks and missing execution
coverage for the corrected volatility predicate. Second review found no additional
material security widening under the schema-denial precondition.

Local focused units/ordering:39 passed. Corrected historical diagnostic copy:
50 tests passed; one initial test lacked registration.INACTIVE.json, then passed
individually after copying that unchanged fixture. Original source/archive remain
unchanged; the checked-in patch is an inactive successor correction, not a change
to historical output or installed SQL.

First hosted candidate e6191a1677e032ef9db1f070437d93581caf2372:
run40787839382, e2e job123165400697,278 passed/6 failed/3 skipped.
The production defect was planner reordering: has_sequence_privilege evaluated
on a non-sequence in the newly added recovery check. Corrected by guarded CASE,
matching the existing historical sequence predicate. No assertion was weakened.
Fixture defects: dropping the recovery role needed grantor-aware removal of its
fixture database ACL; pg_get_functiondef dollar-quotes its C symbol, so mutation
fixture now changes that exact symbol representation. Both are disposable only.

Full failed logs retained locally. Failed artifact12860292224 downloaded and
verified SHA256 babcdf4ec18dac69b6fe14e0a6a69aa504d762fde6a088ec08248630702b1d88.
Failed commits/runs are preserved. Hosted validation for corrected final head is
reported in the PR and final handoff; this record does not imply it passed.

Native boundary tests use actual PG17 extension catalogues and actual derived
production gate. Source/council contact is absent. Restricted-login view access
checks test schema refusal without reading query text. Existing wrapper fixtures
exercise command subprocesses, disposable PostgreSQL and synthetic source/API
stand-ins. Any existing native cgroup runs prove kernel containment of fixtures,
not provider state or live operational readiness.

Historical three-login/default gate bytes remain equal to the original SQL.
No SQL installation, policy/stop mutation, PUBLIC revoke, role creation in
production, limit increase or new dependency is part of this candidate.

Second hosted head6a4a9e03610341f148a4576a50156160708550bf, run40788642196,
e2e job123168038242:283 passed/1 failed/3 skipped. The sole failure was disposable
absent-role setup: PostgreSQL17 requires GRANTED BY's grantor to be current_user,
even for the bootstrap account. Fixture now removes each database ACL through its
actual known fixture grantor connection. No production permission semantics or
assertions changed. The preceding production sequence fix and all other cases
passed. Full failed log is retained. Third head also adds a real recovery-session
held across NOLOGIN test; a dormant role must not hide a surviving session.

The added recovery-session predicate exposed an alias collision with the original
DO's declared record `a` (run40789118289, job123169623515). PostgreSQL interpreted
`a.usesysid` as an unassigned PL/pgSQL record. Renamed only the SQL alias to
`recovery_session`; no condition or assertion removed. The full failed log and
failed heads remain preserved. This is a correction defect, not the historical
production failure's root cause.

## Installed-policy reuse delta

Reuses the same owner command, grants, writer-free capture/screening, accounting,
publication and containment. Explicit cleanup derives the entire immutable old
registration, compares the exact full unused grant/allowance and preserves history.
Review corrected partial historical validation and same-window source substitution
risks before the first hosted candidate for this delta.

Local pure/ordering/input checks pass. Attempting existing supervised-child wrapper
units locally reported LAUNCH_OR_ACCOUNTING_UNCERTAIN, no source output and
uncertain supervisor accounting (73 passed,2 failed,9 fixture errors). No source or
production operation occurred; no containment assertion was relaxed. Hosted PG17/
real-cgroup command checks are required. Final results are in the PR/handoff,
not inferred from these local fixtures.

First reuse-delta hosted run40833115550/job123311609938 failed in fixture setup
before an operational Owner existed; failed fixture teardown then caused cascading
role collisions. Direct setup coverage established the cause on run40834106682:
the test backend replaced the immutable acceptance registry with only a synthetic
key, so historical registration reconstruction correctly refused the real reviewed
key. The reuse fixture now preserves immutable reviewed entries alongside the
separate synthetic work key. A pure regression proves separation. Fixture teardown
also handles partially prepared state; no production guard was weakened.

Review tightened preparation size/symlink checks before reads/copies, full policy
attributes (not just source body), original queued-work preservation and exact
historical counters/package bindings. Prior failed logs/artifacts remain preserved.
