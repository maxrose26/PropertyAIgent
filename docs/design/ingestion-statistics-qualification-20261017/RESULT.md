# Exact statistics boundary and finite credential-risk implementation

Stage4 OPEN. Exception QUALIFIED within tested scope; implementation integrated. Production storage acceptance NOT RUN. Provider ticket SU-511198 stays open; possible verifier retention is explicitly accepted only for the two fixed logins, not represented as confirmed redaction.

## Exact identities
PR122 https://github.com/maxrose26/PropertyAIgent/pull/122 merged.
Predecessor runtime44135bb406ea4cab1b053cef90ee34020ac1d35f/tree20a48f9e864f1eaab34686bc23957fa7db85f4ab.
Reviewed candidatea700cd7ff2e07b3df026f040fb1180ff01deab22.
Integrated revision1088bc35def340f4b8ce9b5ec904e55bfb0fd605.
Exact shared candidate/integrated tree8aa093fc53ad34d0f24b0eea2a3cb9bdfbcb8b6a.
All9 candidate checks and all7 post-merge checks PASS (CHECKS.json). Independent source review PASS after required echoed-input fallback correction. Merge used expected master44135... lease, exact tree and [skip render]; no deployment invocation, production workflow dispatch or source operation. PR121 test evidence remains preserved/unmerged; its test-only changes were not silently included here.
Existing evidence predecessor8085178858e951beb62b821340065c5eb9bd85f7 and accepted7d626d6e9cf463147c52b3c917d0de29cd8fbfbf remain preserved. Local counterpart47d9f5f has the identical integrated tree; original worktrees/uncommitted reassessment preserved.

## Production catalogue evidence, not effective-login proof
At2026-10-17T06:40:20.172214Z, existing signed-in dashboard, SQL principalpostgres, server17.6, READ ONLY:
- extensionpg_stat_statements1.11 inextensions.
- Both exact views have PUBLIC SELECT only, no PUBLIC grant options.
- extensions schema ACL: {postgres=UC/postgres,anon=U/postgres,authenticated=U/postgres,service_role=U/postgres,dashboard_user=UC/postgres}; PUBLIC has no USAGE/CREATE.
- Reader functions pg_stat_statements(boolean), pg_stat_statements_info() are C SECURITY INVOKER with PUBLIC execute; reset(oid,oid,bigint,boolean) has no PUBLIC execute.
- View definitions were inspected, never stored query text. Under search_pathpg_catalog,public, structural definition MD5s: statementsad1495ce5b4c54e4501e907a1f6aae8c; info1807985dc152d2828720e1272d549775. Complete source/package bindings use SHA256.
Two read-only scripts were submitted, respectively4 and5 statements, each endingROLLBACK and5-second statement timeout. No stored statistics/query rows, passwords, verifiers or application data retrieved. Dashboard-internal connection counts/resources/socket closure are not independently measured; do not label this managed observation CLOSED or count it as supervised production storage acceptance. Existing native TLS preflight was not repeated.

## Effective qualification and enforced gate
Original object-ACL-only gate rejected even unusable grants. The corrected gate accepts only the exact pair's latent ACLs while REQUIRING schema USAGE/CREATE remain denied. It grants no SELECT, schema access, memberships or application capability.
Checks pin extension1.11, exact view definitions/options and extension dependency; reject non-SELECT/grant-option privileges, reset execute, pg_monitor/read_all_stats membership, altered functions and unrelated ambient objects. An entire schema/statistics family is never exempted. Existing broad ambient, definer, membership and owner protections remain.
Disposable PostgreSQL17.11, actualextension1.11, same two real login identities, no superuser/SET ROLE substitute:
- Effective object SELECT=true but schemaUSAGE=false, statistics-role membership=false and resetEXECUTE=false.
- Eight actual SQL attempts across two logins fail42501 at schema lookup: both views, reader function and reset function. No stored query text was selected and no reset executed.
- Negative mutations prove rejection of schemaUSAGE, monitoring membership, viewUPDATE, changed view options, resetEXECUTE and unrelated third view.
Thus protected text is inaccessible through these exact paths in the matched disposable boundary. This is stronger schema denial, not a claim that production restricted-logins have been created/tested.

## Focused validation, artifact and cleanup
Final candidate run39011460849, number155, attempt1; restricted job117334692287 PASS.
Five PostgreSQL tests,0 failures/errors/skips,28.112 seconds (suite elapsed, not production budget usage).
Retained original artifact12093067728,63679 bytes:
SHA256 f91b8c4fe71df06fe552998ae1bff8ad4170e7f9d2673f7e873492d20eb06a13, verified after download.
Extracted JUnit47781 bytes:
SHA256 54ac50d1488e7a8142c0eacc671ed656c21a7dc50c665ccc3b803375e59a3880.
Both retained here before hosted expiry; recovery does not depend on expiring artifacts.
The affected existing provisioning rehearsal also reports30 restricted-login denials, fixed3+control readbacks, duplicate seed no-op,0 attempts,4595 serialized bytes and49152 physical bytes, with disposable protected fixtures preserved. These are synthetic/disposable outcomes, NOT production readbacks.
18 focused helper tests PASS locally, final affected suite0.18seconds; final hosted offline and restricted jobs PASS too. No unaffected suite was manually requested; required hosted checks ran automatically on changed heads and merge.
Test connection contexts close; disposable fixture teardown and hosted Stop containers/Complete job PASS. No production CLOSED receipt, native production accounting or resource proof is inferred from CI. RSS/wire-traffic usage was not newly measured by this permission test.

## Helper correction
Original blocked helper remains available at predecessor44135... and SHA2568c5b66c838a0c26a69ef245bacea2697549e7288554b9cdd68d3da2cd45713c5.
New entrypoint requires explicit exact-scope verifier-retention risk, reviewed revision/controller/project/endpoint/method/roles/limits, content hashes, expiry, clean checkout and an exclusive credential-free consumption record. Old provider-attestation CLI does not admit production; historical attested=True only admits disposable fixture.
Independent48-byte randomness, initialNOLOGIN, verified CA/verify-full and selected approved address, direct protected-secret stdin mapping, suppressed raw errors/output and no blind retry preserved. Hidden-input warning fallback aborts before reading; credential files/core dumps forbidden. The approved connection recipe is unchanged; timeouts are applied before catalogue/identity checks. Exact activation gates are checked READ ONLY before password generation.
Only the mapping phase is controlled by this helper (one DB connection,90-second outer deadline,10s statements/3s locks/20s secret calls). It does not claim to orchestrate or reset the overall240-second/13-connection provisioning/storage/revocation allocation. Separate phase receipts, activation/storage readbacks, protected access and cumulative supervision remain mandatory.
Registration mapping-registration.json SHA256e685c79086758f5b52bf5ceff5a8ad34fb2d9e2598e8670485b3ce3a07d7252d binds integrated1088... and expires2026-10-18T06:55:49.492537Z (07:55:49BST). It was validated offline, not invoked/consumed. No new executable ledger grant or operational authority was issued. Do not invoke it before committed installation/remaining prerequisites and the manual controller's finite phase allocation are verified.

## Production dispositions and exact remaining access step
- Provisioning/install/ownership transfer: NOT RUN in production.
- Credentials, secret mapping, activation: NOT RUN.
- Three fixed items/control, production duplicate seed, denied operations and committed readbacks: NOT RUN; no production storagePASS.
- Teardown: NOT RUN/NOT NEEDED for this attempt; no roles/passwords/protected secrets/ledger data created by this work. No blind revocation or deletion.
- Production setup run/number/attempt/artifact: NONE; finite storage authority unused.
- Operational consumers/source/council calls/application/factual writes/scheduling/deployment: NONE.

The reviewed package requires an owner-local Linux/WSL secure terminal, existing authenticated gh owner access for stage4-production-canary environment secrets and the existing migration credential through hidden local input. This workspace has neither gh nor that credential/owner-terminal channel. No secret was extracted from GitHub, requested in chat, substituted through browser SQL or replaced by stronger access. Establish that concrete existing channel before installation, rather than leave partially provisioned accounts waiting. This is an access prerequisite, not renewed generic approval.
Owner action now: make the existing trusted Linux/WSL owner terminal available with gh authenticated to the authorised account and the migration credential accessible in its trusted store; report readiness only, never passwords/tokens/URLs. Do not run the mapping command before the committed-install and finite-controller handoff. Existing protected-environment approval remains applicable to any hosted phase.

Preserve all existing ceilings, IDs1504–1508, Salford stop, historical authorities/evidence and unit/factual UNKNOWN dispositions. No blanket barrier release, source authority, new runtime account or Stage4 advancement. Storage acceptance, operational readiness and backlog completion remain separate.
