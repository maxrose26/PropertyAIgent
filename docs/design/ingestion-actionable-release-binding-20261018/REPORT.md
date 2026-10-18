# PR129 integration complete; exact diagnostic release binding blocked

Stage4 OPEN. Storage accepted; capture/screening held.

## Completed authorised integration
Approved candidate4f4ef89edc83a549fc16e0c43986b9ca30539ecd integrated via PR129.
Integrated revision6bb68733441d487f556179ee3845c3b28aaff2f3.
Exact approved tree724adb7104fb9ce4a77f6118b35c75b32ca08525.
Merge title includes [skip render]; no deployment requested.
All nine candidate checks and all seven required post-merge checks passed. Exact metadata preserved alongside this report.
No production database or secret-store operation occurred.

## Concrete release blocker
The reviewed operational_runner.validate_registration accepts only the old consumed diagnostic authority AUTHORISE_INGESTION_RESTRICTED_ROUTE_DIAGNOSTIC_ONCE_20261018.
main also hardcodes operational-route-diagnostic-once-20261018, whose original full audit is already preserved from that consumed execution.
A new authority fails validation. Reusing the old authority and namespace would violate the new instruction and collide with historical state.
Changing a JSON registration's execution.state_directory alone cannot fix this: main does not use that field.
No renaming/deleting historical audit directories, monkeypatching, validation bypass or old-authority reuse is acceptable.
Therefore no diagnostic registration or owner execution command has been released.

## Minimal correction prepared, not integrated
Draft PR130: https://github.com/maxrose26/PropertyAIgent/pull/130
Candidate8fd3c0d91caa09f50a00eb8d6bec5027743288c4
Tree0c51773453e9c88aca2ad25b7cf2c194e0acdade
Parent6bb68733441d487f556179ee3845c3b28aaff2f3

Only three files change:
- operational_runner.py declares one new fixed DIAGNOSTIC_AUTHORITY and DIAGNOSTIC_STATE and uses them in the exact existing validator/startup.
- Five focused tests reject consumed/unrelated authorities before subprocess/access, accept the exact fresh binding under a synthetic clean checkout, and prove independent one-use journal creation without modifying the old audit.
- Existing offline CI step includes those five tests.

New exact authority: AUTHORISE_INGESTION_ACTIONABLE_CONNECTION_DIAGNOSTIC_ONCE_20261018
New exact state directory: operational-actionable-diagnostic-once-20261018
Routing, roles, SQL, memberships, TLS, credential method, source restrictions and budgets are unchanged.
Five local tests passed with zero failures/errors/skips in0.29s. Independent exact-candidate review PASS; all three reviewed files match the remote tree. All nine exact-head hosted checks also passed; status metadata is preserved in PR130-checks.json. The five local test JUnit file SHA256 is34b7e14d9a177c028dc558591d1543e7773bf77d30083f5a6c1f47bfd61b1878.

## Remaining decision
The current instruction approves integration of the exact PR129 tree. Integrating the different PR130 tree requires its specific exact-content review decision; no generic execution-authority renewal is needed.
After that integration/check gate, the already-approved one diagnostic can receive a genuinely fresh registration binding the final revision/tree, dependency hashes, controller, manifest and accepted generation-1 control hash.
Only then publish its exact blob/SHA256 and explicit <=24-hour expiry, recheck unused owner-local state, and supply one supervised WSL/keyring command.
No release clock has started and no allowance has been consumed by this preparation.
Do not run either old diagnostic command.

## Existing finite scope carried forward
Only exact existing ingestion_worker_login and ingestion_effect_login, reviewed memberships, independently generated in-memory48-byte passwords, direct protected mapping and accepted finite provider verifier-retention risk.
Existing endpoint, selected IPv4 policy, provider CA and verify-full. At most one restricted handshake per role; abort after the first failure.
No installation replay, execution grant, exception, generation-policy patch, queue seeding, source calls, screening or application/factual writes.
Administration240 commands/13 connections/1MiB returned values/240 supervised seconds; runtime1040 commands/40 connections/4MiB returned values/300 seconds. Ceilings, not additive entitlements.
256MiB native controller/owned-subprocess memory,1.5GiB aggregate,zero swap,2MiB combined output.
Separate300-second hidden input with no effects,450-second work,25-second diagnostic reserve,5-second reporting,480-second active and790-second finite outer ceiling.
Known effects permit reviewed NOLOGIN/PASSWORD NULL/membership revocation, exact readbacks and two exact temporary secret deletions/absence check, preserving DATABASE_URL.
Uncertain effects stop mutations with no retry or compensation. Failure status and access/connection/process closure are separate. Post-exit systemd scope removal must be read independently.
Original credential-free audits, disabled-access evidence, consumed authorities, IDs1504–1508 and both original stops remain unchanged.
The prior production failure's cause is still UNDETERMINED. No new fixed reason code or production cleanup outcome exists yet.
SU-511198 follow-up remains prepared and unsent. UNKNOWN/provider-dependent results will end this diagnostic path with that specific provider question, not another automatic diagnostic cycle.
