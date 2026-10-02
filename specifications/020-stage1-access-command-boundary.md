# Stage 1 access and command boundary

TO REVIEW — design and implementation approval request, 1 October 2026.

**Recommendation:** approve the bounded local implementation described here, after accepting the proposed pilot permission policy. This document is a specification, not an implemented security control or a production release approval. No application code, dependency, schema, infrastructure or production configuration was changed to prepare it.

## 1. Authority, baseline and evidence

The accepted LOCAL implementation base is `ff4436937b4268d62f129bc7e2f4ba9e68f0d36e`, tree `05ca152b253882d9becf1c15f5ddeb2c8b68e526`. Its parent is the preserved integration commit `9e515af911a8d387973e48131d6037d8d96ae4e5`, tree `d2a33c11d8a3ecf696b545fc549790352b4cfec8`. The design branch descends directly from the accepted correction. The final handoff records the documentation commit separately; the accepted application baseline does not change.

The complete local report `PropertyAIgent_UI_Session_Lifecycle_REVIEW.txt` and archive `PropertyAIgent_UI_Session_Lifecycle_Evidence.zip` were located and inspected. The archive passed ZIP integrity checking; all 40 SHA256SUMS entries matched; the standalone report equals the archived report. JUnit records support 257 tests plus 10 subtests (267 XML cases), 8 lifecycle tests and 5 workflow tests, all with zero failures/errors/skips. The 49 AppTest checkpoints have zero outstanding connections/transactions and end at 95 checkouts/95 checkins. The parent regression records one outstanding connection/transaction after its first dashboard execution. `walkthrough.log` contains PASS and `DONE /tmp/ah-buyer-walkthrough-lcmlbcx0`; `result.json` names the accepted commit and four CSV rows. All 71 dependency pins matched in the archived inventory. No discrepancy was found. These are verified archived results, not newly rerun tests. They establish local lifecycle/functional acceptance, not authentication, browser HTTP, production, or full-suite acceptance. Initial new-test fixture/routing failures are retained and explained in that report.

Instructions reviewed: `CLAUDE.md`, `specifications/019-ui-session-lifecycle.md`, Product Vision, Platform Architecture, Product Roadmap, and Stage 1 plus security findings of the supplied critical review. The supplied July 2026 platform report is historical: its local/single-user description, counts, scheduling claims and build-status assumptions are not current authority. The current product outcome is buyer-specific acquisition intelligence over shared evidence. This design protects that distinction without introducing a general tenancy platform. Stale NEXT/FUTURE wording in architecture/roadmap is not permission to resume unrelated work. The present explicit Stage 1 design decision governs this work; the lifecycle contract remains binding.

## 2. Observed hosting and access boundary

| Layer | Evidence and consequence |
|---|---|
| Public web address | The 1 October critical review identifies `https://propertyaigent.onrender.com`, Streamlit router `app/ui/streamlit_app.py`, previously reviewed live SHA `7ba940eb90a7d79a22e123a9260e0dba3ebd8262`. This turn does not claim a new live SHA check. |
| Web service | Prior release records identify `srv-d9qbl7qjnfac73d8nieg`; repository `render.yaml` explicitly excludes the existing web service. Its current command, access gateway, replica count and deployment settings cannot be established from YAML. |
| Application | The accepted router registers pages without identity checks; `bootstrap()` can initialise SQLite schema; `get_settings()` creates/commits a missing row. Buyer selection lists all active buyers or falls back to pilot templates. These are not permission controls. |
| Download/media | Inspected installed Streamlit 1.64.0 `web/server/starlette/starlette_routes.py:create_media_routes`: file ID resolves directly in media storage. No application principal/buyer check is made there. It serves `st.download_button` and local `st.image` bytes. An unguessable media URL is not authorisation. This is local source evidence, not a production exploit test. |
| Database | Server-held credentials can act independently of browser identity. No current production role/grant/RLS audit was performed. App checks do not constrain administrators or a compromised server credential. No RLS migration is proposed. |
| Live metadata limit | Render `list_services` refused because no workspace is selected and requires user-confirmed workspace selection. No workspace was guessed, no browser fallback or production access attempted. Current host/gateway and scheduler settings remain release verification items. |

**Trust model:** treat the public origin, deep links, widget events, query parameters, selected IDs, source text and returned document URLs as untrusted inputs. The controlled application process, deployment administrators and protected server configuration are trusted. No upstream gateway is credited with protection until both its policy and bypass resistance are evidenced. Public static framework assets and a content-free health response may remain accessible; application data may not.

## 3. Recommended identity and admission design

Use Streamlit's supported native OIDC (`st.login`, `st.user`, `st.logout`) with **one Google Identity OIDC client**, subject to confirmation that the owner can use this provider. An existing organisation-managed Microsoft Entra tenant is a proportionate substitute if that is the owner's established identity system; use its exact tenant issuer, never a generic multi-tenant default. Do not implement passwords or treat GitHub OAuth login to hosting tools as application OIDC.

Use Authlib through the supported Streamlit integration for signature/JWKS, issuer/audience, expiry, nonce and state validation. The application accepts only the configured provider/issuer and a nonempty subject from the framework-validated identity; it additionally checks required claims and current admission. Do not decode an unverified JWT, accept browser headers, email text, query parameters or a client-supplied role as authority. Binding is `(issuer, subject)`, not mutable display name or email domain. For Google, require `email_verified=true`; email is a confirmation/display aid, not the grant key. Canonicalise only the documented Google issuer variants into the configured canonical issuer; reject other issuers. Reject inconsistent audience/azp, missing/expired exp or malformed/future iat where exposed; validate the real provider claim shape during the integration tests.

Admission is a small versioned server-side configuration mapping exact principals to `enabled`, `role` (`reader` or `operator`), one existing `workspace_id`, explicit `buyer_ids`, and optional `not_before`. No domain-wide admission, wildcard buyer grant, first-user-becomes-owner, self-service signup or client-editable role. OIDC success without a grant shows a generic access-denied page and logout, with no DB access. Never list admitted people to a denied user.

The owner is an explicitly nominated operator with explicit buyer grants, not a hardcoded email. Operators can maintain shared evidence but do not automatically gain every buyer's confidential data. A second recovery operator is recommended only if the Product Owner nominates one. No real person, subject, workspace or buyer grant is invented by this specification.

### Configuration failure, expiry and logout

Validate local configuration before any application DB connection, cached data return, page registration that loads data, or provider client construction. Missing/unreadable/invalid grants, unknown role, duplicate principal, missing owner declaration, invalid callback URL, missing cookie/client secret, unexpected environment or disabled access mode must produce a generic closed/unavailable screen. There is no permissive development fallback. Loopback tests use explicitly supplied synthetic identities and disposable configuration through test-only adapters, never an HTTP header or deployed auth-bypass environment switch.

OIDC provider URLs/callback are fixed configuration, not user input. Production requires HTTPS; localhost HTTP is only for the isolated test identity provider. Keep Streamlit CORS/XSRF protections enabled. Expose no access/ID tokens to application UI or logs. Do not claim the documented 30-day identity cookie is an acceptable application lifetime: check provider `exp` on every protected execution and command, additionally cap grant lifetime at eight hours from validated `iat`, and expire idle UI access after 30 minutes. Expiry requires a new supported login flow; no silent extension from browser activity beyond absolute expiry.

Use a small process-owned authentication lease registry (not SQLAlchemy sessions) to invalidate stale tabs on explicit logout. A lease binds validated principal, OIDC issuance, permission revision, server boot epoch and browser-session nonce. No identity/role values supplied by the client create a lease. Logout revokes active leases for that principal/issuance, clears UI state and calls `st.logout()`. Every service/read/export checks the lease; a lightweight UI auth heartbeat may clear idle displays, but never renew idle time. Reject old issuance after logout; a fresh OIDC token is required. On process restart, require fresh authentication for tokens predating the new boot epoch rather than silently losing revocation. Test same-second issuance and clock skew without permitting replay. This bounded registry is for one web process/replica; multi-replica deployment is a NO GO without an agreed shared revocation mechanism. Do not add Redis or auth tables in this stage. Already-delivered screenshots/downloads cannot be revoked; do not claim otherwise.

Check permission configuration on every protected entry/service action. A server-loaded revision digest (plus deployment epoch) invalidates grants/state; it is never browser-controlled. Replacing config requires the separately approved deployment/admin channel. Missing configuration after a previously good load fails closed rather than retaining stale grants. If permission reload, process topology or provider claims cannot satisfy these rules, stop with that concrete blocker.

### Proportionate alternatives

| Alternative | Assessment |
|---|---|
| Native OIDC plus explicit admission/grants | Recommended: supported login, one small policy layer, no account/tenant schema, fits existing Streamlit pilot. Requires deliberate download handling and lease tests. |
| Proven upstream OIDC gateway | Potential later substitute for login if already operated and proven to cover HTTP, WebSocket, media, direct Render hostname and callbacks. Still needs command/buyer checks; no gateway is currently established by evidence. Do not add a proxy/service now. |
| Shared password / hidden URL / UI-only role | Reject: no reliable individual admission, revocation or service/data boundary. |
| Full account, organisation, billing and RLS rebuild | Defer. More product and operational scope than this internal pilot needs. |

## 4. Data classification and actor matrix

Shared means reusable between admitted pilot users, not publicly downloadable. Site, Application, allocation, source document, policy facts, qualified AH facts and source attribution remain shared evidence. Buyer/BuyerMandate criteria, buyer-fit interpretation, AgentEvaluationHistory, CurrentBuyerOpportunityState, claims and future decisions are buyer-private. Internal credits, job diagnostics and enriched personal contacts are operator-restricted. Existing `Contact.outreach_status` is global operational metadata, not a buyer-private decision store; do not expose it as one. Do not add decision persistence in Stage 1.

| Action/data | Anonymous or authenticated but unadmitted | Admitted non-operator | Approved operator |
|---|---|---|---|
| Login, generic denied/unavailable page | Allowed; no data | Allowed | Allowed |
| Shared evidence, ordinary Dashboard/Explore/Profile/policy reads | Deny | Allow | Allow |
| Buyer names/options/mandates/fit/evaluation/history | Deny | Only explicitly granted buyer IDs in assigned workspace | Same explicit grants; role alone is insufficient |
| Select a buyer / generic mode | Deny | Among authorised options only; generic reads shared evidence only | Same |
| Temporary shortlist/filters/selections | Deny | Own current identity/buyer scope | Own current identity/buyer scope |
| Deterministic CSV/PDF/export | Deny | Authorised rows, approved non-contact fields only | Authorised rows; contact data remains an explicit operator-only projection |
| Matching/relinking, global exclusions, policy/AH/visual evidence review | Deny | Deny at service boundary | Allow existing commands with fresh checks, current object validation and provenance |
| Credits top-up, enrichment/unlock, contact edits | Deny | Deny, including contact lookup/export | Operator only; paid/network gate is additional |
| NL AI search, AI PDF narrative, plan summary, web research, agent evaluation | Deny | Deny; deterministic filtering remains usable | Only enabled named action within explicit server budget/limits and buyer grant if buyer-specific |
| Buyer mandate writes/onboarding/baselines | Deny | Deny | Existing operator CLI only, explicit buyer grant and command scope; no new UI |
| Admission/role changes, DB migration, deployment/scheduler/secret control | Deny | Deny | UI operator role grants none of these; separate infrastructure/release authority |

Recommended pilot policy deliberately makes non-operators read-only and keeps paid operations disabled by default. Approving Stage 1 code does not enable production spend. The shared evidence/contact distinction must apply to underlying loads and export projections, not just hiding columns.

## 5. Enforcement contract

Proposed narrow modules: `app/security/access.py` (validated actor, admission, lease, require checks), `app/services/ui_commands.py` (existing UI mutations/paid orchestration), `app/services/authorised_reads.py` (buyer/private read and export projection boundaries), `app/security/outbound.py` (document destination/transport policy), `app/reporting/csv_safety.py`, and `app/ui/protected_download.py` (scoped client delivery). Names are design targets, not existing implementations.

`require_admitted(actor)`, `require_operator(actor, action)`, `require_buyer(actor, workspace_id, buyer_id, mandate_id=None)` and `require_command(actor, action, targets)` deny by default with a typed exception. Resolve actor in a trusted UI/CLI adapter and pass/bind it explicitly; do not derive it from selected buyer or a mutable `session.info['role']`. Underlying effectful public services must check a trusted request context before their first query/mutation/provider call, even if the UI command already checked. No `actor=None` => system/owner shortcut. An OS/deployment administrator able to execute arbitrary Python with database credentials is outside the browser-user boundary, not made safe by this API.

Each command accepts IDs and validated scalar changes, re-reads authorised targets, validates relationships/current state, then uses the existing commit boundary. Denied calls make zero queries when role/admission alone suffices, zero writes always, and zero provider construction/requests. For cross-buyer IDs, a constrained membership/ownership read may be required; do not load the confidential object then filter it. Avoid ORM autoflush before authorisation. Do not hold or reuse ORM objects across requests. Permission revision is rechecked before side effects and before returning private results from a long operation; revocation cannot undo an already dispatched request/committed action.

The accepted `with get_db()` try/finally session ownership stays intact. Guards occur before acquisition where possible and inside the scope for resource checks. Any exception, `st.stop` or `st.rerun` still closes acquired sessions. No new auto-commit-on-exit, shared/cached SQLAlchemy sessions or pool changes.

### Exact enforcement inventory at the accepted baseline

| Existing entrypoint / function | Required boundary/change |
|---|---|
| `app/ui/streamlit_app.py`, all ten pages converted in specification 019 | Authenticate/admit before `pg.run`, bootstrap or data loads. Page-local guard prevents direct/alternate entry bypass. Administration registration is operator-only for usability, plus service enforcement. Hidden detail routes remain guarded. |
| `common.bootstrap`, `app/db/session.py:init_db`, `get_settings`; `common.get_db` | UI uses read-only schema/settings lookup after admission; missing schema/settings closes with operator setup instruction, never a page-load insert/DDL. Existing CLI setup behaviour is only available through an explicitly scoped operator setup path. Keep fresh session/finally close. This is the intentional startup-write correction, not a migration. |
| `common.credits_sidebar` | Move top-up mutation/commit to `ui_commands.add_credits`; operator check before Settings lookup/change. Credits are not permission or an unlimited paid budget. |
| `common.render_scheme_detail` (restore/exclude/relink) | `set_site_exclusion`, `relink_site_applications`; operator, IDs/current links/council validation before mutation; unchanged commit boundaries and reason/provenance. |
| `2_Review_Site_Links.py`; `app.pipeline.site_linking.confirm_suggested_link`, `reject_suggested_link` | Guard service and UI command, reload Application and current suggestion; preserve existing linking semantics. |
| `2b_Review_Allocation_Site_Matches.py`; `allocation_site_dry_run_matching.confirm_review_candidate`, `reject_review_candidate`, `run_controlled_write`; `policy.site_match_review.confirm_site_match`, `reject_site_match` | Operator/machine scope before loads/effects; preserve candidate revalidation and note requirements; server-derived actor replaces literal `streamlit_review` attribution. |
| `common.render_companies_and_contacts`; `contact_pipeline.enrich_company`, `upsert_company_from_enrichment` | Check operator before loading contacts, constructing clients or calling Companies House/Apollo/Hunter/OpenAI. Validate application/site/company association; deduct credits only within existing success semantics. Editable contact IDs must belong to that authorised company/site; constrain fields. |
| `policy.review.approve_change`, `reject_change`; `visuals.review.confirm_image`, `reject_image`, `relink_image`, `mark_primary` | Require shared-evidence operator action. Record actor server-side. Protect AH/policy changes through these existing review services. No new AH production truth tables/importer or pending migration package. |
| `4_Council_Dashboard.py`, `6_Council_Intelligence_Detail.py`; `reporting.local_plan_summary.generate_local_plan_summary` | Plan regeneration is operator plus paid action before client/query; preserve source-grounding and existing explicit commit. Reader detail page cannot reach the action by submitting a hidden event. |
| `reporting.allocation_intelligence_summary.generate_allocation_intelligence_summary` | Protect paid generation/persistence and `scripts.generate_allocation_intelligence_summaries`; passive summary reads remain admitted shared evidence. |
| `0_Explore.py`; `search.query_parser.parse_query`; `reporting.pdf_report.generate_narrative` | Explicit operator paid request before OpenAI client/call; no auto-paid repeat from stale query cache. Pure parser/result/display helpers stay pure. PDF data scoped before generation. |
| `3b_Shortlist.py`; `reporting.allocation_web_research.build_allocation_web_research_context`, `cross_site_intelligence.generate_cross_site_intelligence` | Operator + paid scope before web research/synthesis; bind result to identity/buyer/permissions/shortlist/evidence version. No non-operator paid callback. |
| `ui.buyer_selector.buyer_selector`, `active_buyer_key`; `policy.buyer_profile_store.list_active_buyer_options`, `get_buyer_profile_dataclass` | Filter before names/mandates are returned. Resolve workspace/buyer IDs from authoritative grants and existing rows. No template/default-workspace fallback for a missing/unauthorised buyer in secured mode. Templates remain pure test data. |
| `reporting.opportunity_feed.build_opportunity_feed`, `reporting.site_profile`, `ui.site_profile_view`, `policy.buyer_matching_b2_context.evaluate_buyer_fit`; buyer fit/packet consumers | Authorised read boundary before buyer mandate lookup or interpretation; a valid shared Site ID confers no access to another buyer's fit or history. Generic mode never includes private overlays. Pure interpretation functions need no artificial auth parameter once input was legitimately obtained. |
| `policy.agent_evaluation_persistence.get_or_create_subject_anchor`, `try_claim_evaluation`, `record_evaluation_outcome`, `run_persisted_evaluation` | Explicit scoped actor before anchor/claim writes, mandate/history/current-state read, commit or paid evaluation. Validate mandate -> buyer -> workspace relation; no agent/claim-state UI is added. |
| `policy.buyer_profile_store.resolve_default_workspace`, `seed_default_buyer_profiles`, `run_buyer_onboarding_baseline`, `bootstrap_acquisition_monitoring`, backfill/migrate functions | Operator-only command paths; never invoked as a reader convenience/fallback. Setup is deliberate, not page loading. |
| Explore selected/all-filtered CSV and PDF; Shortlist CSV/PDF/AI PDF; dataframe/editor toolbars; `common.render_visual_evidence` | Scoped generation and client delivery as sections 6–7; no protected bytes registered in global `/media`. |

Implementation must complete a call-site audit for these public effectful services and attach a checked manifest to its handoff. Keep pure reconciliation/evaluation semantics unchanged; do not introduce a second business-logic implementation inside command wrappers.

### Command paths and machine identities

CLI access is authenticated by the approved execution environment/OS administrator, not by `--operator`, an email string, a buyer selector or possession of a DB URL alone. A reviewed server configuration binds a machine principal to exact entrypoints, actions and buyer scope. The web adapter cannot construct this principal or launch these CLIs. No machine capability defaults on when configuration is missing. CLI flags may further narrow authority, never create it. Keep existing `--dry-run`, approval and cost guards; require both existing guards and new command scope.

| Command family | Exact relevant paths | Proposed authority / local check |
|---|---|---|
| Discovery / processing / monitoring | `scripts/run_daily_councils.py`, `scripts/run_intelligence_processing.py`, `scripts/run_historical_rebuild_to_completion.py`, `scripts/sync_opportunity_monitoring.py`, `app/pipeline/run_weekly.py`, `app/policy/monitor.py` | Distinct least-action machine identities at launcher; no implicit UI operator. Local launch-contract tests only. No activation or settings change. Historic rebuild remains separately blocked. |
| Human matching / policy review | `scripts/apply_pr2_allocation_match_review.py`, `dry_run_gm_allocation_site_matching.py`, `dry_run_gm_allocation_site_relationships.py`, `cleanup_allocation_site_relationships.py`, `register_policy_sources.py`, `populate_control_relationships.py` | Read-only dry runs still require trusted operator environment; apply/write additionally requires named command scope and existing opt-in flags. |
| Buyer setup / migration | `scripts/bootstrap_acquisition_monitoring.py`, `backfill_buyer_mandate_b1_defaults.py`, `migrate_buyer_profiles_to_mandates.py` | Explicit scoped operator, authorised buyer IDs; never page-triggered. No execution against production. |
| AI / benchmark / rebuild | `scripts/generate_allocation_intelligence_summaries.py`, `run_agent_evaluation_benchmark.py`, `refresh_intelligence_application.py`, `rebuild_intelligence.py`, `reextract_failed_documents.py` | Operator/machine action, existing approvals and budget caps; benchmark dry run stays no-paid. No new paid entitlement is created. |
| Import/backfill/schema tooling | `scripts/migrate_schema.py`, `migrate_to_postgres.py`, `migrate_policy_intelligence.py`, `migrate_joint_plan_support.py`, `add_allocation_match_review_columns.py`, remaining `scripts/import_*`, `backfill_*`, ingestion/onboarding tools | Host-admin boundary only, not callable from UI. Inventory and denied web-dispatch tests; no migration/import work is authorised. Existing database privilege separation is a later release review prerequisite. |
| Operator export | `scripts/dry_run_gm_allocation_document_evidence.py` CSV output; `benchmark/extraction.py` / benchmark case JSON | Trusted operator scope; CSV sanitisation where applicable; treat mandate-bearing JSON/cases as private artefacts, not public static assets. |

Do not retrofit every pure historical analysis function or redesign scheduler orchestration. Guard relevant launch adapters and effectful services; if this requires P0-A runtime changes, stop and request a separately bounded decision.

## 6. State, cache and download isolation

An authorised view scope consists of principal, workspace, buyer (or explicit generic), permission revision, auth lease, result identity/generation and relevant data/mandate fingerprint. Compare it before reading any prior UI state and before each export/action. On logout, expiry, principal, role, grant revision or buyer change, clear/recreate application and widget state: `active_buyer_key`, `buyer-selector-*`, `_shortlist`, `_last_nl_query`, `_last_nl_filters`, `_pdf_report_bytes`, AI intelligence result/web evidence, selected IDs/table generation keys, detail query parameters and pending review/contact edits/messages. Revalidate all deep-link IDs after clearing. Do not silently use the previous buyer as fallback.

Preserve the accepted selected-record contract: stable actual IDs, result identity generation, changed-result reset, reordering and A-B-A invalidation. Extend its scope with identity/permissions/buyer rather than substituting row positions. Never store sessions, lazy ORM instances, permission-bearing clients or callbacks in session state/cache. A generation result may be retained only as values under its complete scope; changed permissions invalidate it even if underlying data is unchanged.

Only immutable public council/config data can be shared globally without a user key. No global buyer-private result/export cache for this pilot. Shared-evidence caches require admission BEFORE cache access and must exclude contacts, mandates and private annotations; they may never perform writes on a cache miss. Do not use underscore cache parameters to omit actor/scope from a private cache key. Auth lease state may be process-shared solely for revocation, never to share database sessions or user payloads.

### Delivery decision

Do not serve any protected generated report, CSV, contact file or local evidence image via native `st.download_button`, `st.image` file registration, static directories or bare file-ID routes. Keep framework static assets public; no user data goes there.

Use one small supported Streamlit v2 component for protected delivery: an explicit download request triggers a normal authorised rerun/command; the server revalidates current IDs/scope and serialises the final bytes as a safely encoded string in that user's WebSocket component payload. Component code creates a browser-local Blob/download, with no server file URL. Use structured component data, not interpolated executable HTML; allowlisted MIME and safe filename, revoke object URLs on scope change/unmount, no localStorage/service-worker persistence. For local evidence thumbnails use the same admitted payload approach. External source links remain normal source links, not a proxy to private server files.

Do not send export bytes speculatively to an unrequested stale button. The browser download is scoped to the bytes already authorised for delivery; a copied Blob URL cannot authorise a new server request in a different clean browser. Test this rather than assuming it. A file that was legitimately downloaded cannot be recalled. Avoid building a custom authenticated HTTP server/gateway in this stage; if the component cannot pass isolation/accessibility/size gates, stop rather than falling back to unguarded media URLs.

Built-in dataframe CSV download is a second export route. Where supported, remove it via the pinned component's documented configuration and confirm in Chromium. Independently supply only an authorised, CSV-safe display projection to every dataframe/editor; hidden columns still count as transmitted data. Preserve raw typed values/IDs separately for actions and filtering. If disabling the toolbar is unsupported, its output must pass the same text safety tests. Never rely on CSS hiding to enforce access.

## 7. Document and CSV trust boundaries

### Fetch inventory

- `app/extraction/pdf_text.py:download_document` streams files, uses `app.scrapers.idox_portal.get_with_retry`, retains a 200 MB download ceiling and separate extraction limit. Preserve streaming, temporary-file cleanup, retry accounting and current limits.
- `app/scrapers/documents.py:get_idox_documents`, `_find_anite_search_url`, `get_anite_documents`, `get_arcus_documents`, `discover_documents`: request/listing and Playwright-assisted paths, including Anite binary response/download handling.
- `app/policy/document_discovery.py:discover_policy_pages_for_council`, `download_policy_document`; `app/policy/report_discovery.py:discover_reports_for_source`, `check_report_for_changes`; `app/policy/monitor.py:check_source`: direct requests and discovered URL ingestion.
- `app/scrapers/ssl_fix.py:get_verify_bundle_for_host`, `_fetch_leaf_cert`: preliminary HTTPS HEAD, raw TLS socket and certificate AIA issuer URL fetch; all are outbound destinations requiring validation, not just the final PDF.
- Callers include `app/pipeline/run_weekly.py`, `evidence_refresh.py`, `status_verification.py`, policy ingestion and operator extraction scripts. `reporting/allocation_web_research.py` delegates searches to the model provider and does not make those results trusted download URLs.
- Companies House/Apollo/Hunter/OpenAI/EPC/postcode calls are fixed-provider enrichment paths, requiring command permission and no dynamic endpoint injection; a general enrichment rewrite is outside scope. Any discovered document URL passed into them remains untrusted.

### Contained destination policy

Introduce one document transport policy and route the above HTTP document/discovery/AIA requests through it. Allow only HTTPS 443 by default, exact configured council/CDN hostnames and approved path scope where a shared host/bucket requires it. HTTP 80 is an explicitly documented exception for an existing legitimate source or CA issuer, never a blanket fallback from failed TLS. Reject other schemes, embedded credentials, fragments where inappropriate, malformed/ambiguous host encodings, invalid ports, IP literals and local hostnames; canonicalise IDNA/trailing dot before matching. No `*.amazonaws.com`, `*.blob.core.windows.net` or blanket council-controlled subdomain wildcard.

Resolve A and AAAA; reject the destination if any candidate address is non-global, loopback, private, link-local, unspecified, multicast, reserved, IPv4-mapped private IPv6, or a metadata endpoint. Connect only to a validated resolved IP while retaining the original hostname for SNI, certificate hostname validation and Host. A DNS pre-check followed by an ordinary second hostname resolution is insufficient. Use a tested Requests/urllib3 transport adapter with explicit destination binding, no environment proxy/netrc inheritance, scoped cookies and no global resolver monkeypatch. Revalidate on each new connection/retry and redirect; fail closed if this cannot be guaranteed.

Disable automatic redirects. Follow at most five explicitly validated hops; reject HTTPS downgrade except a preapproved source-specific policy, loops, malformed Location and unlisted/private destinations before dispatch. Strip credentials/cookies/authorisation/referrer secrets across origin changes; use only approved destination-scoped portal cookies. Do not log full signed URL queries or tokens. Validate source/path before opening a destination file; restrict caller-selected paths to the evidence directory.

Browser-assisted document downloads may not bypass this transport. Intercept document requests before browser dispatch and fetch/fulfil through the safe transport with explicitly scoped portal cookies, or fail closed when unsupported. Do not merely inspect a response URL after Chromium has fetched it. Any Playwright path that still follows untrusted document/navigation redirects without equivalent pre-request destination enforcement is a NO GO for this portion; return a bounded blocker rather than claiming whole-browser SSRF protection. Do not change P0-A browser lifecycle, pool/budget architecture or live scraper configuration.

Keep TLS verification true against trusted CA roots (existing approved intermediate bundles may be used). For the current certificate-repair helper, the certificate-only unverified handshake is not permission to fetch document content without verification: bind/validate its network destination first, tightly bound certificate/AIA sizes, restrict AIA host/path, validate the resulting chain and require the final document TLS handshake to verify. Never trust the unauthenticated leaf/AIA content as a new root, and never introduce `verify=False` or `ignore_https_errors` for content fetches.

Local legitimate fixtures come from existing configured origins: `planning.stockport.gov.uk/PlanningData-live`, `planning.bury.gov.uk/online-applications`, `pad-planning.bury.gov.uk`, `live-iag-static-assets.s3.eu-west-1.amazonaws.com` (Stockport policy assets), and `tcintunestorage01.blob.core.windows.net` (Trafford policy assets). Retain required paths from `config/councils.yaml` and `config/policy_sources.yaml`. Build fixtures from URLs/configuration, with local synthetic responses and controlled DNS—not live council requests or a newly invented generic CDN allowlist. Distinguish policy-approved origins from proof they currently serve valid documents.

### CSV policy

Apply one central cell encoder at Explore selected/all-filtered CSV, `allocation_report.to_csv_bytes`, operator document-evidence CSV, and every dataframe/editor download projection. Work from a typed export schema: genuine numeric values remain numeric (including negative numbers); IDs retain their canonical identity; arbitrary text resembling a number is still text. For external text, neutralise leading formula markers `= + - @`, their relevant full-width variants, and leading tab/CR/LF or whitespace/control prefixes that expose a marker. Use a leading apostrophe text marker plus correct CSV quoting/doubled embedded quotes; preserve the original DB/source value, never rewrite evidence. Normalise only in the export projection and document the transformation. Test separators, quotes, newlines, UK phone strings, negative numeric values and legitimate source URLs.

Validate representative files in local LibreOffice/available spreadsheet software, not only string assertions. Do not promise permanent safety if recipients remove text markers or save/reopen in software that strips them; this known limitation is stated in operator documentation. No macros, formula evaluation or paid external spreadsheet service is needed. Preserve selected record counts, source attribution, AH qualification, scoped meaning and all existing CSV identity assertions.

## 8. Implementation sequence and impact

1. Build config/identity/admission/lease boundary and local fake OIDC fixture; prove denial occurs before bootstrap/DB/provider creation. Keep provider-specific real accounts unconfigured.
2. Wire router and ten page guards, read-only UI startup/settings, buyer-scoped reads and operator commands. Add effectful service guards and narrowly scoped CLI adapters; preserve commit/lifecycle semantics and existing safeguards.
3. Isolate state, restrict contacts, implement authorised client download delivery and CSV safety. Preserve existing report/data contracts and per-record identity.
4. Apply contained document/AIA transport protection with council/CDN fixtures; no scraper runtime redesign.
5. Run access/command/service/browser negatives and operator positives, then original functional/lifecycle/workflow regression gates. Return exact patch/configuration manifest for separate release approval.

**Expected code footprint:** router/common/ten pages, buyer selector, targeted private read consumers and effectful services listed above; new small security/command/export modules; document transport adapters and relevant launchers. No opportunity semantics, matching scores, AH evidence meaning, prompt/model policy, agent orchestration, persistent decision workflow or schema change. Extract only current UI side effects needed to enforce checks. Broad movement of `common.py` or pipeline rewrites is not approved by this proposal.

**Dependencies:** retain the proven Python 3.12 / Streamlit 1.64.0 / SQLAlchemy 2.1.1 environment and other 71 pins. Native login needs Authlib, absent from the current lock. Add and lock a compatible supported Authlib release and only its required missing dependencies after local compatibility/security review; record the exact final resolver diff. Do not silently upgrade Streamlit/SQLAlchemy. The v2 delivery component uses the existing Streamlit/browser facility and local static JS, not a CDN package/new server. Selecting the precise Authlib patch is an engineering verification task, not a new product decision. No dependencies were installed now.

**Database:** no auth/user/role tables, no new buyer/workspace model, no grants/RLS/owner changes, no migration. Existing shared versus buyer relationships are enforced in queries/services. Settings initialisation is moved out of page reads into the existing deliberate setup boundary. Existing commit semantics otherwise remain. A no-migration assertion must be evidenced against the exact patch; if a new schema is genuinely necessary, stop for separate approval.

**Audit:** structured allow/deny/action/outcome records with server-derived pseudonymous principal, action, object IDs, permission revision and correlation ID. Existing provenance fields use verified actor identity; no tokens, credentials, contact payloads, mandate contents or full signed URLs in logs. Use existing logging infrastructure; retention/access configuration is a release review item, not a new telemetry service. An audit log does not replace permission enforcement.

## 9. Acceptance specification and gates

These are required future tests, not results claimed in this documentation task.

| Test group | Positive and negative proof |
|---|---|
| Identity | Valid admitted reader/operator; valid unadmitted identity denied; forged signature, wrong issuer/audience/nonce/state, expired/missing claims, unverified email, malformed callback, missing dependency/config, unknown role and missing admission owner all fail closed. Count DB/session/provider calls before denial: zero. |
| Permission matrix | Parameterise every listed command for anonymous, unadmitted, reader and operator. A forged widget/callback or direct service invocation cannot mutate; authorised operator action persists correct changes once, with actor attribution. Denial precedes DB autoflush/client construction; snapshot every table and network/cost spies. |
| Buyer ownership | Buyer A principal cannot enumerate Buyer B names, mandates, fit, history, current state, claims or decisions through IDs, query params, stale widget state, generic mode, fallback templates, exports or indirect relationships. Operator without Buyer B grant also denied. Allowed A reads work. Unknown versus forbidden responses do not disclose object existence. |
| Sessions and concurrency | Repeated reruns/navigation/independent AppTests; settings error, command denial, page exception, stop/rerun; zero connection accumulation before GC/teardown. Existing commits persist and uncommitted work is rolled back. Never close sessions manually in tests to fabricate a pass. |
| Browser authentication | Launch real local Streamlit in isolated process plus loopback-only fake OIDC provider with test keys; use separate fresh Chromium profiles for anonymous/A/B/operator. Test login callback, direct hidden detail links, logout, back/refresh, session expiry, second tab, revoked grant, identity switch and restart. Do not substitute `st.user` monkeypatch/AppTest for browser login proof. |
| Downloads/cache | Generate A export/image, attempt URL/payload reuse in signed-out/B contexts; no protected `/media` artefact, no pre-auth bytes or stale cache. Logout/expiry/permission/buyer change removes pending downloads and edit state. Test both selected/all-filtered, shortlist deterministic/AI PDFs and all dataframe/editor download routes. Previously delivered files are outside revocation guarantee. |
| Outbound | Initial private targets; redirects to private/unlisted/downgrade; mixed A/AAAA; DNS rebinding between validation/connect; IPv6 variants; URL credentials; proxy env; retry/AIA/browser fallback bypass; excessive hops/bytes/time. All fail before prohibited connection. Approved council/CDN and scoped portal-cookie cases succeed with verified TLS and unchanged streaming limits. |
| CSV | Hostile cells and headers, hidden fields, tabs/CR/LF/full-width markers, separators/quotes, legitimate URLs, phone text, real negative numbers; spreadsheet-open check and original ID/count/qualification assertions. |
| Scheduled/CLI | Launch-contract tests prove no implicit machine/operator grant, correct per-job scope, denied paid/write paths make no calls/writes, existing dry-run/cost/manual approval guards remain. No real hosted workflow/scheduler invocation. |
| Preservation | Original 257 + 10 subtests; lifecycle 8; workflow 5; 49-checkpoint accounting; existing AH/selection/export functional assertions and full walkthrough final DONE/result.json; no new failure/skip hidden behind totals. |

Local verification uses no production environment files, credentials, database or accounts. Reuse the existing seccomp denial wrapper for pure/service tests. Browser/OIDC/transport fixtures necessarily need loopback sockets; use a separate network-isolated harness allowing only assigned local fixture ports (and no external DNS/egress), with disposable SQLite and optionally disposable PostgreSQL for query/transaction checks. This is a clearly identified additional harness, not weakening the original offline suite. Paid providers are recording fakes; denied cases fail if any request/client is created. No live council downloads or model calls.

Authentication means the historical walkthrough cannot simply enter data pages anonymously after implementation. Preserve the accepted original script verbatim as an archive/reference. A new external test adapter may supply a validated synthetic operator context exclusively in the isolated acceptance process so the original script's AH/selection/CSV assertions still execute unchanged. Do not add a deployed auth bypass. If download transport assertions require adaptation, create a separate reviewed version comparing identical bytes/IDs with the original; do not delete/weaken assertions or silently label a changed script 'unchanged'. The real Chromium gate independently proves access and delivery over the running app.

Suggested exact verification commands for the future implementation (proposed filenames, not runnable tests created now):

```bash
# Run from the Stage 1 implementation checkout with its recorded test interpreter.
PY=/workspace/scratch/1b4c7bcd52fc/test-venv/bin/python
OUT=/workspace/scratch/fbbe3b115fa5/stage1-implementation-evidence

env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" verification/ah-offline-pytest.py -q -p no:cacheprovider verification/test_stage1_access.py verification/test_stage1_commands.py verification/test_stage1_buyer_scope.py verification/test_stage1_csv.py verification/test_ui_session_lifecycle.py

env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" verification/stage1_browser_check.py --output "$OUT"

env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$PY" verification/stage1_outbound_check.py --output "$OUT"

bash verification/stage1_preservation_check.sh "$PY" "$OUT"
```

The preservation runner must enumerate the same eleven original focused test files from `verification/web_ah/check.sh`, the five workflow-context tests, lifecycle suite/AppTest checks, and full authenticated functional walkthrough. Report pass/fail/skip counts separately. Do not assert proposed test counts in advance.

**GO for code acceptance:** all matrix and negative-path gates evidenced, denied actions have zero writes/paid calls, authorised operator paths work, buyer/data/download isolation proven in fresh browsers, URL/CSV protections tested with legitimate fixtures, lifecycle and original functional contracts preserved, exact dependency/config/command/diff manifests reviewed, no unapproved schema/runtime work.

**NO GO:** unknown upstream security credited, configuration fallback opens access, private bytes in global media/cache, buyer selector used as permission, default machine identity or UI-only checks, DNS pre-check with unchecked reconnection, weakened TLS, unexplained functional failure/skip, multi-replica revocation gap, or purported production readiness from local tests alone. Release additionally requires the operational checks below.

## 10. Rollout, scheduler blast radius and recovery

### Exact proposed configuration categories

- Native Streamlit secret file `[auth]`: approved absolute `redirect_uri` ending `/oauth2callback`, strong `cookie_secret`; named `[auth.google]`: `client_id`, `client_secret`, exact Google `server_metadata_url`, minimal `openid email profile` scope; token exposure off. Render secret-file path must be included in Streamlit's configured secrets-file search. No secret in Git, image, logs or screenshots.
- Separate server access-policy file/path: schema version, environment, enabled switch, required owner principal, principal grant entries, permission revision, not-before cutoffs, lease duration/idle limits, approved workspace/buyer IDs. No actual grants are included in the example/design.
- Named paid-action switches default false; explicit per-action input/call bounds use existing limits (including existing web-research and benchmark caps). Credits do not override these switches. Scope does not create a billing ledger or approve budgets/production spend.
- Source-origin/path/AIA allowlist, redirect policy and validated transport settings; no generic outbound override.
- Web one-process/one-replica assertion; CORS/XSRF enabled, static user-data serving disabled, safe error presentation. Existing production DATABASE_URL and credentials are neither read nor changed now.
- Separately reviewed per-service machine principal/command scopes when a scheduled service is eventually included. Web secrets must not be copied to cron services by default.

### Scheduled service evidence and release consequence

The dated 29 September read-only report `docs/P0A_BLUEPRINT_AUTO_SYNC_IMPACT.md` in the preserved P0-A review checkout records the following. It is evidence to account for, not a current settings attestation and not imported P0-A code:

| Service / ID | Recorded schedule/state | Deployment risk to recheck |
|---|---|---|
| Daily discovery `crn-d9sv93vavr4c73f98rb0` | 05:00 UTC daily; suspended | Later context reports parked `/bin/true`; current value unverified. Preserve suspension/parking. |
| Intelligence processing `crn-d9sv93vavr4c73f98rag` | 07:00 UTC daily; enabled | Master-linked auto-deploy can publish shared dependency/service changes and affect paid processing. |
| Weekly sync `crn-dag1lbv40ujc73de74mg` | Monday 06:00 UTC; enabled | Master-linked deployment affects deterministic writes even if web is deployed separately. |
| Historical rebuild `crn-d9uq0sijobas73bf7s2g` | 1 January 03:00 UTC; enabled in dated report | Annual schedule is not manual-only; do not trigger or reinterpret it as disabled. |

That report initially observed On Commit auto-deploy for all four and Blueprint Auto Sync Yes. Its execution addendum records the separately approved Auto Sync change to No / Sync paused, with all four service On Commit settings unchanged. Later parking context and elapsed time mean current values must still be reverified rather than copied forward. Pausing Blueprint sync alone does not disable service auto-deploy or scheduled execution. `render.yaml` does not prove live settings. No setting was changed in this design task.

Future release sequence, requiring separate approval:

1. Confirm actual Render workspace, web service/command/replicas, direct/custom origins, current live SHA, web auto-deploy, Blueprint sync and each of the four cron branch/auto-deploy/command/suspension states using read-only metadata. Verify no unexpected run. Inventory DB capability read-only under separate permission; never infer normal-role RLS protection.
2. Validate proposed secrets/access-policy configuration offline without printing values. Confirm exact owner subject via a controlled identity-provider login/identity-only admission screen that exposes no application data; no automatic grant. Owner approves admission and buyer map through the established release channel. Configure a separate local/staging provider client and exact callback allowlists; no wildcard redirect.
3. Before any merge/push, approve a release plan for all automatically affected services. A documentation-only or 'skip-render' commit message is not a deployment guard. Prefer an exact-SHA web-only rollout from an approved isolated ref if the platform supports it, keeping master untouched until cron compatibility/configuration is separately accepted. Do not switch branches, disable auto-deploy or sync Blueprint without explicit approval.
4. Prepare current authorised owner/recovery administrator access in a separate browser, secure config backup, and tested fail-closed recovery. Verify schema/settings prerequisites without page writes. Test real provider and fresh signed-out browser against every public origin, WebSocket and download path only after explicitly approved staging/live access work.
5. Deploy the reviewed exact application SHA/config pair only when separately approved. Smoke reader/operator/buyer isolation; keep all paid switches off. Verify live reported SHA, owner access, no anonymous data/startup writes, original lifecycle health and unchanged cron controls. Abort for unexplained auto-deploy, config drift or access exposure.

**Lockout recovery:** a nominated hosting administrator uses the existing protected Render/IdP account, MFA/recovery codes and reviewed config backup to repair only the OIDC/admission/callback configuration. It is not an in-app emergency password. While locked out, show a closed maintenance screen; do not unset auth, temporarily allow every email/domain, or revert to the unauthenticated Stage 0 app. A rollback may restore the last tested access-protected build/config; before such a build exists, maintain closed access and fix forward. Rotating secrets or changing owner grants remains separately authorised. Test provider outage, invalid secret, missing owner grant, restart and recovery locally before release.

## 11. Genuine decisions and approval request

Recommended defaults resolve the implementation choices; no generic architecture questionnaire is needed. The remaining Product Owner/identity decisions are:

1. Accept the pilot matrix: admitted readers see shared evidence plus only assigned buyer information; operators maintain shared evidence, contacts and paid commands but also need buyer grants. Paid actions stay disabled pending separate bounded approval.
2. Confirm Google Identity or nominate the existing organisation-managed OIDC provider, and securely identify the owner (and any recovery operator), admitted pilot subjects, workspace and buyer grants. These values are needed for rollout, not for synthetic local implementation tests. Do not send secrets in the review report.
3. Confirm which Render workspace owns the known service IDs so current read-only metadata can be inspected before a release plan is authorised. No infrastructure choice or settings mutation is implied.

**Precise approval requested:** approve local implementation, focused tests and disposable browser verification of sections 3–9 from the accepted application base plus this documentation commit: native OIDC/admission/leases; read-only UI startup; operator command and buyer read enforcement; state/contact/export isolation with supported client delivery; contained document/AIA URL transport and CSV safety; relevant scoped CLI adapters; Authlib dependency addition with a reviewed pin diff. Authorise no new schema or user/organisation platform, no live identities/grants, no paid execution, no production access/configuration/migration, no merge/push/deployment, no scheduler change or activation. Stop for a complete exact-SHA REVIEW handoff after local verification. Keep P0-A and AH migration packages independent.

## 12. Source and inspection record

Repository anchors above refer to accepted commit `ff4436937b4268d62f129bc7e2f4ba9e68f0d36e`. The supplied critical review Stage 1 and security section are the scope source. The older platform PDF supplies historical context only. The lifecycle report/archive and dated Blueprint report are evidence with the limits stated above.

Primary technical references checked 1 October 2026:

- https://docs.streamlit.io/develop/api-reference/user/st.login — native OIDC configuration, Authlib, state/nonce and framework protections.
- https://docs.streamlit.io/develop/concepts/connections/authentication — identity versus authorisation and session/cookie behaviour; native logout alone is not an application-wide revocation policy.
- https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component — supported local component surface; proposed delivery security still requires browser proof.
- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html — destination/redirect/DNS threat model; local exact transport requirements above are design decisions.
- https://community.owasp.org/attacks/CSV_Injection — formula-leading text and spreadsheet save/reopen limitations.

Design preparation performed read-only source/document/archive inspection, local docs branch creation and documentation checks. No application acceptance suite was rerun merely to create this specification. No claim is made that Stage 1 security tests pass before implementation.

## Implementation clarification under the 1 October local authority

The independent feasibility review found that navigating native `/auth/logout`
would otherwise bypass application lease revocation. Use the pinned public
`st.App(..., middleware=[...])` API in a thin `app/ui/server.py` launch module,
run by `streamlit run app/ui/server.py`. Middleware revokes cookie-bound leases
before delegating to native logout; it does not replace OIDC routes or implement
a second authentication server. Raw cookie fingerprints are binding data, never
identity. Directly launching the router without this middleware fails closed.
This is a local launch clarification, not approval to change Render's command.
Test direct logout, stale tabs and copied-cookie replay as well as the UI button.

## 10. Approved bounded corrections after candidate da6c9fe (1 October 2026)

The Product Owner adopted the REVIEW instruction for local correction and verification.
Preserve candidate `da6c9fef62fe146d70f1460f01474f1ef7cf5284`; work on a separate
local descendant. No production/publication, P0-A or AH migration authority is added.

Document retrieval may create one dedicated DOCUMENT BrowserContext within the
existing browser, blocking service workers at birth and installing transport controls
before pages exist. This narrow exception to section 7 does not change browser launch,
pool, recycle, concurrency or existing budgets. All requests, redirects, frames,
subresources, workers, popups, WebSockets and downloads must either traverse validated
transport or be denied before dispatch. Cookies cross the boundary only for explicit
allowed destinations and matching paths; updates use the same restriction. Contexts,
pages and temporary files close on every exit. Security/transport failure is a typed
failure, never successful empty discovery. Preserve Anite/Arcus document identity and
functionality, and demonstrate memory/streaming and resource bounds with local fixtures.

LeaseRegistry must reclaim expired capacity in every collection without increasing
limits, removing required replay tombstones or reviving idle/logged-out issuance.
Check reusable active leases before new-entry capacity. Retain issuance rejection until
its eight-hour absolute validity horizon; expired admission must never create a lease.
Reclamation and admission are atomic under the registry lock. Cover fresh admission,
capacity, concurrency, logout/idle replay, revision changes, restart and machine scopes.

The final acceptance pack includes existing functional/security/browser/lifecycle/TLS/
spreadsheet gates and new regressions, including an unchanged-parent capacity failure.
Independent review inspects actual final source and evidence. Application acceptance,
Git-history readiness and production readiness are separate statuses. History recovery
uses only available original objects/bundles; never synthesize missing ancestry or edit
shallow boundaries to conceal missing objects.

### Findings while executing the bounded correction

The replay contract includes native logout between OIDC callback and first app lease.
Verified native issuance is tombstoned even without an existing lease. At full issuance
capacity no required tombstone is evicted; a bounded new-issuance cutoff rejects the
unrecordable logged-out issuance while preserving already-active leases.

Positive command coverage also found two implementation mismatches: the provider
wrapper must support the existing timeout-only `with_options` call with a SHARED call
counter, and extraction must permit its established THREE calls (entities, site
intelligence, affordable classification). This corrects the Stage 1 wrapper's two-call
limit; it does not add a workflow, enable expenditure or change the original extraction.

Native Chromium `offline` plus CDP Fetch controls cover the tested HTTP paths but do
NOT provide complete renderer egress denial: a local positive-control TURN/TCP probe
connects from the actual dedicated document context. Native packet-emulation rules
also failed that negative test. No JavaScript API replacement is accepted as proof.
Thus this implementation remains BLOCKED, regardless of completed mechanism tests.
A separate network-denied document renderer PROCESS is a proposed next scope, not
approved here; it must preserve scraper-browser launch/pooling/recycling and account
for total process resources. Production and Stage 2 remain unauthorised.

### 11. Adopted local native document-process correction

The Product Owner authorises a local descendant of d9d04b4e243bd57f5be9dc040ce0c7e4d1811aa5 to replace the document-only context boundary with a separate document Chromium process. Discovery/status launch, pooling, recycle and P0-A/AH packages remain unchanged. No publication or production change is authorised.

The document process must start behind an unprivileged Linux native syscall filter, inherited by every child/thread. Deny direct network socket creation, alternate ABI bypasses, external descriptor import, io_uring network bypass and process-group escape. Only connected AF_UNIX STREAM/SEQPACKET pairs for Chromium internal IPC and audited private CDP pipes are permitted; no Unix datagram/external-endpoint path. A kernel notification supervisor denies attempted network syscalls and fails the entire document job, rather than treating a denied resource as an empty successful result. Unsupported kernel/architecture/bootstrap configuration fails closed before rendering. Ordinary unavailable Unix service sockets may return EPERM at startup; these must never permit external IPC.

The existing parent verified HTTP transport remains authoritative. The private CDP relay bounds each frame and retained queue, validates framing/JSON and request/response correlation, and fails closed on malformed, stale or mismatched messages. No network debugging port, generic proxy, shared browser profile or ambient credentials is allowed. The accepted document identity, cookie scope/deletion, TLS, streaming and response limits remain required.

Before implementation, local probes demonstrate unprivileged seccomp notification and Chromium rendering with socket denial and only connected internal socket pairs. These are feasibility results, not acceptance. The separate guardian must supervise the entire child process group, record typed failures, reap children and handle parent loss; parent-side supervision must handle guardian loss. A missing or unverifiable supervisor/descriptor boundary is fatal.

Resource controls must cover parent retained buffers, renderer descendants, CDP queues, temporary files, requests, concurrency and lifetime. Existing 20 MiB renderable-resource and 200 MiB attachment caps and operation deadlines are not increased. New combined limits must be fixed before final verification and measured against legitimate fixtures. Aggregate RSS monitoring is explicitly a sampled fail-closed limit with possible sampling overshoot, not a kernel memory ceiling; the local cgroup mount is read-only. Resource-accounting uncertainty must fail closed, not silently omit descendants.

Acceptance includes unrestricted positive controls and protected negative controls for native TCP/UDP, IPv4/IPv6 where available, TURN/STUN, WebRTC data channels, WebSocket and WebTransport where supported; unsupported worker/popup/service-worker/native attempts must not return document success. Preserve legitimate Anite/Arcus/council/CDN, redirects/origin/cookies/download identity, bounded streaming and cleanup assertions. Test timeout/cancellation/crash/parent and guardian loss, malformed/stale IPC, process recycle and cleanup. Run the complete exact-candidate Stage 1 pack and independent read-only review. A nonzero final complete pack or need for broader privileges/runtime changes triggers the user's stop condition.

Git-history readiness remains separately blocked on the previously recorded original missing commits/trees and their closure. No fabricated commits, amended checkpoints, shallow-boundary changes, production release, Stage 2, P0-A or AH migration work is authorised.

#### Document process implementation contract and local evidence boundaries

The dedicated process uses private `--remote-debugging-pipe` transport, a fresh private
profile, sanitized environment and scoped `TMPDIR`. Linux x86-64 unprivileged seccomp
notification is mandatory; unsupported platforms/kernels fail closed. The native filter
precedes Chromium exec, rejects alternate ABIs, socket creation, external Unix sockets,
network descriptor import, namespace/group/CLONE_PARENT escape and io_uring. Internal
connected Unix STREAM/SEQPACKET pairs remain usable. Native attempts terminate the job.
Guardian and parent process incarnations are pinned; stale PID/group values cannot
justify signalling another process. Normal shutdown requires a clean root exit and
reaped descendants, with accounting active during shutdown.

Fixed new document-only bounds: 32 MiB per CDP frame, 64 MiB retained relay queues,
128 outstanding CDP requests, 16,384 request IDs per process, 512 MiB aggregate renderer
RSS, 256 MiB parent/driver RSS growth, 768 MiB combined growth/guardian/renderer RSS,
512 MiB temporary storage, 32 supervised processes including the guardian, and
300 seconds process lifetime. Sampling is 100 ms; memory and aggregate disk bounds can
overshoot between samples. Child-written individual files additionally have a 512 MiB
kernel file-size limit. Shutdown/reaping is bounded to five seconds. Existing document
operation deadlines, 20 MiB render and 200 MiB attachment limits remain unchanged.

The new process uses `--no-zygote` to avoid retained fork-template processes, preserving
separate renderer/GPU/network processes, graphics and site isolation. This is limited
to document launch: actual Anite fixtures demonstrated the original draft launch
exceeded the fixed RSS cap, while no-zygote preserved the fixtures within that cap.
No graphics-disabling diagnostic flags are adopted. Discovery/status launch, pooling
and recycling are unchanged. Admission is at most one document process per Python
process, matching the inspected sequential document/council pipeline; this is not a
cross-service/global limit. Overlap fails closed without extending operation budgets.

Parent-crash cleanup uses a bounded trusted-parent output journal and an explicitly
owned private directory marker. Pending output replacements/partial files are restored
or removed and the owned job directory is removed after parent loss. The guardian must
never recursively delete an arbitrary caller directory. Native process/context entry
and exit remain within the document rollback scope; cookies sync only after successful
process completion. Request IDs and CDP session IDs must both correlate. Document bytes
remain bound to their verified download URL, not a filename or most recent attachment.

Native-layer fixture checks deliberately test the process boundary without relying on
the additional application HTTP interceptor/offline controls; fixed synthetic HTML is
supplied over private CDP. These are distinguished from full `document_page` integration
checks and never change production guards. Direct RTC fixtures use a local synthetic
STUN binding responder solely to discover the peers' local addresses; actual message
delivery is peer-to-peer, with no TURN relay or external service. Fixture ICE, local
network permissions and resolver rules are synthetic-test-only. Failed intermediate
controls remain separate evidence. The complete local gate is
`verification/stage1-renderer-check.sh`; earlier mechanism-pack completion is insufficient.


#### Completion and cleanup ownership

A document-only file custodian survives the guardian's planned browser shutdown. It
shares the original job deadline (no reset), is included in combined RSS/process
accounting, and reserves the existing final five seconds for cancellation cleanup.
An exact-job private-pipe acknowledgement distinguishes committed output from pending
output. Backups survive until this acknowledgement; pending outputs roll back on parent
loss. An abort marker plus a bounded output lock excludes parent writes during rollback.
The custodian stops and verifies the pinned guardian and renderer group before deletion.

The custodian's own receipt asserts only file removal, never its own process exit.
The parent reaps it, closes its pipes and verifies no owned directory, recorded partials,
guardian or renderer group before emitting `closed: true`. A failed postcondition
quarantines capacity. Hung/malformed/oversized custodian output fails closed with bounded
kill/reaping; no release is allowed while cleanup remains unverified.

Cleanup fixtures use the application's actual temporary-directory location (/tmp),
with evidence exported only after assertions; synchronized evidence directories are
not runtime job directories. Workspace recreation diagnostics remain separate failed
evidence and require writer attribution, not an assumption of environmental causality.
