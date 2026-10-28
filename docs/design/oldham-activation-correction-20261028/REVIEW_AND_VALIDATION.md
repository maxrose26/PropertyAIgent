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
