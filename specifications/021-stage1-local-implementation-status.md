# Stage 1 local implementation checkpoint — BLOCKED

This is an implementation checkpoint under the autonomous local authority, not
Stage 1 local acceptance or release approval. Specification 020 remains the
contract. Base: `1ba23801f5660d01070b3eff99387f1c213d5a32`, accepted application
`ff4436937b4268d62f129bc7e2f4ba9e68f0d36e`. Exact candidate identity, results and
review are recorded in the external REVIEW/evidence archive.

## Ownership and boundaries

Native Streamlit/Authlib validates OIDC. Server policy admits exact issuer/subject
pairs and supplies role, workspace and explicit buyer IDs. Buyer selection grants
nothing. Readers see shared evidence and granted buyer overlays; operators also
perform shared commands and require the same buyer grants. Paid switches default
off. No signup, role database, schema change or new infrastructure exists.

`app/ui/server.py` is the middleware-backed local launch adapter. Every page enters
`page_scope` before bootstrap, then the accepted `get_db` scope. Settings/schema
reads do not initialise or seed the database. Fresh page sessions remain open for
lazy rendering and close deterministically; no automatic commit was introduced.
Service command guards run before inputs, protect flush/commit, and revalidate
before return. Private queries constrain ownership before loading, then revalidate.
Dirty-object reparenting cannot replace persisted ownership checks. Explicit
commits remain at their existing business boundaries.

`verification/stage1_service_manifest.json` and `stage1_cli_manifest.json` enumerate
the guarded functions and launchers. Historical schema/import/onboarding tools
remain trusted-host-admin-only, never web-dispatchable; this is not database RLS.
Buyer setup requires the whole affected workspace's existing buyers and enough
explicit unused buyer IDs for new templates/legacy mappings. There is no automatic
buyer grant. No migration was executed, including the separate AH rehearsal.

## Configuration manifest (no secrets or actual grants)

| Configuration | Required rule |
|---|---|
| `PROPERTYAIGENT_ACCESS_POLICY` | Protected JSON file, version 1, enabled, environment local/production, exact issuer/client_id, one web process and replica, enabled operator owner_subject, explicit principal entries |
| Principal entry | issuer, subject, enabled, reader/operator, positive workspace_id, explicit buyer_ids, optional not_before; no email/domain auto-admission |
| `paid_actions` | Known action names in `app/security/commands.py:PAID_LIMITS`, boolean, absent means denied; grants/credits alone do not enable payment |
| `machines` | Named trusted-OS identities with enabled, workspace_id, buyer_ids, explicit actions including `launch:<command>`; no wildcard |
| `PROPERTYAIGENT_COMMAND_IDENTITY` | CLI-only named machine; no default or web-provided identity |
| Native `auth` secrets | exact callback `/oauth2callback`, cookie_secret at least 32 characters, named `oidc` client_id/client_secret/server_metadata_url; tokens not exposed |
| Framework | CORS and XSRF enabled; static user serving and base path disabled; launch middleware required; one process/replica is a rollout attestation, not infrastructure discovery |
| Lease | max 8 hours, idle 30 minutes; 20-second UI checks do not extend idle time; restart forces new issuance; policy revision invalidates old leases |
| Document origins | exact entries in `config/document_origins.json`; HTTP exceptions empty; no approved production AIA origin yet |
| Existing DB/provider secrets | remain separately managed; never copied into fixtures; paid switches off for rollout until separately authorised |

Native chunked cookie reconstruction uses two pinned framework helpers solely to
verify and fingerprint consumed cookies for logout revocation. Unrelated cookie
names cannot change the fingerprint. This private helper compatibility requires a
regression check before any Streamlit upgrade; it is not an alternate OIDC verifier.

## Dependency and paid-call manifest

All original 71 pins are retained in `verification/stage1-requirements.lock`.
Only Authlib 1.8.0 and joserfc 1.7.5 are added. Requirements constrain installation
to that lock. Local `pip check`, 73 version comparisons and real native login are
required evidence; this does not claim a complete vulnerability audit.

`PAID_LIMITS` records per-command call/input ceilings; optional internally-created
acquisition clients also use the same provider guard. Existing pipeline/benchmark
limits remain. Visual classification retains one call per page and a 32 MiB
encoded request envelope, allowing image inputs larger than text-only limits;
existing 25 MiB input PDF, page and 200-classification default limits are unchanged.
Structured command logs contain action, pseudonymous principal, revision,
correlation, outcome and scalar target IDs, not payloads/tokens/signed URLs.
Production log level, retention and access remain rollout prerequisites.

## Evidence map and acceptance status

| Requirement | Code / local evidence | Gate status |
|---|---|---|
| Native identity, admission, expiry/revocation/restart | access.py, ui/access.py, middleware.py; synthetic native OIDC Chromium and lease tests | Local evidence present; production unverified |
| Operator and buyer boundary | commands.py, authorised_reads.py, manifests; parameterised denial, zero-write, positive commits, cross-buyer/reparent and query-revocation tests | Local evidence present |
| Read-only startup, lifecycle | common.py plus ten pages; original lifecycle8, AppTest49 checkpoints, exact accounting | Local evidence present |
| State and delivery | buyer_selector, scoped PDF/AI caches, protected_download, safe_table; real Blob CSV/image, cross-profile denial, no-native-media AST check | Populated Explore all/selected CSV, PDF, shortlist CSV/deterministic/AI PDF and toolbar flows verified with isolated provider; production unverified |
| Functional preservation | original257 plus10 subtests; unchanged full walkthrough via explicit authentication/byte-capture adapter | AppTest evidence, not HTTP/production evidence |
| Document HTTP | outbound.py, extraction/discovery/monitor/ssl_fix; destination unit tests and actual synthetic TLS/cookies/redirect fixture | HTTP/TLS and synthetic AIA trust-chain evidence present; browser integration blocked |
| Document browser | Anite/Arcus existing BrowserContext paths | **BLOCKED — see below** |
| CSV | central text projection, tests, actual LibreOffice open of17 cases, unchanged selected-record assertions | Local evidence present; recipients can remove text markers |
| CLI/workflows | guarded launch manifests, no-implicit-authority tests, five existing workflow-context tests; workflow files unchanged | Local-only; nothing dispatched |
| Complete Stage 1 acceptance | All specification020 gates, complete candidate review | **BLOCKED, not PASS** |

## Bounded blocker and requested decision

Anite/Arcus document retrieval uses a BrowserContext shared with earlier discovery
and status navigation. A late route hook cannot reliably constrain pre-existing
service workers, popups or WebSockets. An early global hook changes unrelated
scraping, contrary to specification020 section7. The attempted broad hook was
removed. No claim is made that the remaining browser document paths are protected.

The smallest proposed resolution is approval for **one dedicated protected document
context in the existing browser**, born with service workers blocked, explicit
pre-dispatch routing, scoped cookie transfer and deterministic cleanup. Retain
existing browser launch/pool/recycle/budget architecture and P0-A separation. Test
redirect-origin semantics, relative links, cookie updates, failed-route propagation,
streaming/memory limits and context closure/recycling, with legitimate council/CDN
and synthetic verified AIA fixtures. Do not route unrelated discovery/status traffic
through this policy. Rerun the whole local pack after this bounded correction. No production access
is needed. The rejected prototype remains outside the source checkout as evidence.

## Reproduction and failure disposition

Run `bash verification/stage1-check.sh <isolated-python> <external-output> <chromium>`.
Run `verification/stage1_spreadsheet_check.py <external-output> <soffice>` with the same
interpreter. The shell script records exact HEAD/tree and clean status; it explicitly
labels completion as a local pack, not complete Stage1 acceptance.

Historical assertion files and full walkthrough are unchanged. The opt-in pytest
plugin supplies synthetic grants/settings/buyers; AppTest thread adapters supply
synthetic actor context. Only AppTest maps protected delivery to its old byte
recorder so original byte assertions still execute. Real Chromium uses native OIDC
and the production component without that substitution. Populated AI report checks
replace only the SDK constructor with synthetic responses; real guards, schemas,
grounding checks and renderers still execute. Toolbar checks force the browser
without-File-System-Access fallback because headless OS save dialogs are unavailable;
actual Streamlit CSV serialization and Blob download bytes are tested. TLS fixtures map an already
validated public fixture IP to a local socket and accelerate only the 300-second
deadline test clock; these are instrumentation, not production transport settings.

Earlier failed/partial runs are retained. The HTTP/1.0 slow-drip test caught early
timer cancellation; cancellation now occurs on response release and the test passes.
Review also corrected buyer reparenting, query revocation, internal client limits,
omitted extraction commands, native image delivery and chunked-cookie isolation.
Populated browser checks also found and corrected a volatile shortlist cache timestamp
and a pre-existing accepted-baseline PDF mismatch: missing qualified private counts
now display unknown, without promoting legacy figures or changing AH calculations.
No assertion was disabled to obtain a pass. The unresolved document gate is not
reclassified as a skip or successful test.

## Rollout and recovery remain separate

No master merge, push, deploy, hosted workflow, scheduler change, real grant,
production-data operation, migration or paid request is authorised or performed.
Keep P0-A and AH migration work separate. Recheck the four master-linked scheduled
services and Blueprint/auto-deploy state before any publication; dated evidence in
spec020 is not a current attestation. Actual IdP, owner/recovery subjects, buyer grants,
Render workspace/topology and service commands remain rollout decisions.

Rollback of this local checkpoint is to its specification parent in an isolated
checkout. Never deploy the unauthenticated baseline as a recovery path. Production
recovery must retain closed access and restore a tested protected build/config or
repair admission through the existing hosting administrator boundary.

## Bounded correction follow-up (1 October 2026)

Continue from reviewed `da6c9fef62fe146d70f1460f01474f1ef7cf5284` on
`implement/stage1-bounded-corrections`, preserving that commit unchanged.
The adopted scope is specification 020 section 10. Registry reclamation, pre-lease
native logout, dedicated document HTTP rendering/streaming, scoped cookie updates,
and positive-command wrapper corrections are implemented locally. The complete
reproduction entrypoint is `verification/stage1-bounded-check.sh` (isolated Python,
external evidence directory, local Chromium and LibreOffice paths).

**Local application acceptance remains BLOCKED**: the required document egress test
has a real TURN/TCP connection from the dedicated offline context. The script runs
this as a failing final gate, not an xfail or a skipped requirement. HTTP/CDP fixture
passes establish only their named mechanisms. A separate browser process with native
network denial needs additional scope approval; no such process is implemented here.

**Git-history readiness remains BLOCKED** pending original missing objects from a
backup; current source testing does not imply ancestry connectivity. No shallow
boundary is changed to conceal missing history. **Production remains unauthorised.**

Command positives use explicitly admitted synthetic operator/machine identities,
explicit disposable Settings/buyer fixtures and existing provider mocks. A spawn-safe
entrypoint executes the unchanged syscall-denial wrapper so PDF worker processes do
not recursively run pytest. Historical HTTP mocks are forwarded to the new transport
seam only when an explicit Mock exists; separate actual TLS/CDP tests exercise transport.
Original 257 tests, ten subtests, lifecycle assertions and walkthrough remain unchanged.
The two exploratory historical matching tests expecting a caller-supplied literal
reviewer name remain incompatible with the approved server-derived attribution rule;
they are preserved unchanged. New matching positives assert the authenticated label
and rejection of the forged label, rather than treating those old assertions as passes.
