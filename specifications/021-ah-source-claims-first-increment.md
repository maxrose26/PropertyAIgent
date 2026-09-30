# 021 — AH source claims: exact first-increment specification

Status: bounded local implementation approved, including the three preflight amendments below, 30 September 2026. Production migration/import and release remain unauthorised.
Accepted executable: 739895df1c613e912560943a443d7a182311e26f. Its accepted 188 candidate / 188 baseline / 20 AH / 38 spec020 / 1 filter passes remain unchanged. This document is not a migration, importer or release.

## 1. First-increment boundary

Two new AH-specific tables; immutable source assertions plus append-only review/relationship events. A controlled operator import/review command and read-only preview, not a general dashboard. First-class metrics in this increment are affordable_count and tenure_count, including explicitly named components. Existing percentage/classification fields remain labelled legacy context and retain their independent uncertainty checks; do not build a new percentage extraction or editing subsystem. Future percentage claims can use a separately approved schema revision, not arbitrary new metric strings.

Reuse Application, Site and Document, current operative-planning selection, AHAssessment and the spec020 threshold kernel. Add a bounded claim selector BEFORE the current percentage-led whole-record winner. No change to specialist exclusions, recommendation taxonomy, discovery scheduling or contact-data collection. No backfill, re-extraction or model call.

## 2. Exact proposed schema

Database names below are NEW and proposed only. Types are portable logical SQL types: INTEGER primary keys use each supported database's normal generated-integer mechanism; timestamps are UTC (timezone-aware in PostgreSQL, normalised UTC at the SQLite boundary). String enum domains are CHECK constraints, not PostgreSQL-specific enums. No JSON data can bypass the typed quantity, scope or review columns. All fields are NOT NULL unless marked nullable. Foreign keys use ON DELETE RESTRICT; no cascade deletes.

### ah_source_claims

| Column | Type / nullability | Meaning |
|---|---|---|
| id | INTEGER PK | Immutable assertion identity |
| schema_version | INTEGER, default 1, CHECK = 1 | Reader contract, not matching policy version |
| application_id | INTEGER FK applications.id | Application to which the claim applies |
| site_id | INTEGER FK sites.id, nullable | Resolved physical site; null permitted only for pending/unresolved imports |
| scheme_application_id | INTEGER FK applications.id | Explicit root application identifying the scheme interpretation; initially the source application itself if no linkage is reviewed |
| scope_kind | VARCHAR(20) | whole_scheme / component / phase / unclear |
| scope_key | VARCHAR(200) | WHOLE_SCHEME, named stable component/phase key, or UNRESOLVED |
| scope_label | VARCHAR(300) | Human-readable scope name |
| scope_basis | TEXT | Evidence/reference explaining application-to-scheme/component assignment; empty prohibited |
| metric | VARCHAR(30) | affordable_count / tenure_count |
| tenure_name | VARCHAR(100), nullable | Required for tenure_count; null for affordable_count; preserve source term, no inferred classification |
| qualifier | VARCHAR(20) | exact / approximate / range / at_least / up_to / unknown |
| value | NUMERIC(18,6), nullable | Point quantity only |
| lower_bound | NUMERIC(18,6), nullable | Source-defined lower bound only |
| upper_bound | NUMERIC(18,6), nullable | Source-defined upper bound only |
| unknown_reason | TEXT, nullable | Required for unknown; null otherwise |
| document_id | INTEGER FK documents.id | Primary supporting Document; required even for an explicit unknown statement |
| document_url_snapshot | TEXT, nullable | Source URL as captured; never silently updated from a later Document edit |
| document_title_snapshot | TEXT, nullable | Captured source title |
| document_content_hash | VARCHAR(64), nullable | Actual existing/captured byte SHA-256; not fabricated for legacy documents |
| document_date | DATE, nullable | Date on source document, not download/review time |
| document_date_missing_reason | TEXT, nullable | Required iff document_date is null |
| passage_text | TEXT | Verbatim supporting passage, nonempty |
| passage_locator | TEXT | Page/section/table/paragraph descriptor, nonempty |
| page_start | INTEGER, nullable | 1-based PDF page, if available |
| page_end | INTEGER, nullable | Inclusive; requires page_start and >= page_start |
| extracted_text_hash | VARCHAR(64), nullable | SHA-256 of captured full extracted text, when used |
| passage_start | INTEGER, nullable | Zero-based Unicode code-point offset in that exact text snapshot |
| passage_end | INTEGER, nullable | Exclusive offset, requires start and > start |
| passage_hash | VARCHAR(64) | SHA-256 of UTF-8 passage_text, checked by writer |
| planning_stage | VARCHAR(20) | proposed / approved / legally_secured / unresolved: SOURCE-REPORTED stage pending review |
| stage_document_id | INTEGER FK documents.id, nullable | Source establishing stage if stage is to be checked; may equal document_id |
| stage_passage_text | TEXT, nullable | Stage-supporting passage, not merely a status label |
| stage_passage_locator | TEXT, nullable | Source locator for stage support |
| origin_kind | VARCHAR(20) | reviewed_import / extraction |
| origin_reference | VARCHAR(200) | Batch/record or extraction-run/record identity |
| extractor_version | VARCHAR(200), nullable | Parser/model/config version if known; provenance only |
| created_by | VARCHAR(200) | Operator or extraction process identity, NOT an assertion of human review |
| recorded_at | TIMESTAMP | Capture/insert time; never substituted for source date |
| import_key | VARCHAR(200), UNIQUE | Stable namespace + caller idempotency key |
| payload_hash | VARCHAR(64) | Hash of canonical assertion payload, excluding id/import_key/recorded_at/created_by |

No source claim is created for the mere absence of evidence: zero claim rows naturally resolves to unknown. An explicit unknown source claim requires a real source passage. The controlled first importer accepts references to existing Document records only. External documents not yet present remain outside this increment; do not create placeholder document rows, scrape, or bypass source linkage. This deliberately narrows the earlier URL-only alternative.

Database CHECK constraints:

- Quantity shape: exact/approximate => value only; range => lower+upper only and lower<=upper; at_least => lower only; up_to => upper only; unknown => all three null plus nonempty unknown_reason. Enforce mutual exclusivity, not COALESCE-based guessing.
- Non-null quantities >=0. Reject NaN/infinity and values outside NUMERIC precision in the writer; PostgreSQL checks also reject special numeric values. Preserve source numeric precision up to six decimals; higher precision is rejected for review, never silently rounded. The normal case is integer home counts, but no invented integer rounding.
- Metric/tenure consistency, all enum domains, positive page numbers, paired valid offsets and paired stage passage/document fields. scope_kind=whole_scheme => scope_key=WHOLE_SCHEME; unclear => UNRESOLVED; component/phase => neither reserved key and nonempty label. Non-null hash strings must be 64 lowercase hex characters (writer plus supported dialect constraint).
- document_date and missing-reason exclusivity; primary source URL may be absent where document identity and reviewable captured evidence remain available.
- No UNIQUE constraint on application/metric/scope: multiple source claims are intentional. Index (application_id,metric), (site_id,scheme_application_id,scope_kind,scope_key,metric), document_id, payload_hash.

Cross-row writer/acceptance checks (FK alone cannot establish these): document ownership belongs to application or an explicitly reviewed cross-application source link; site/root/application relationship is consistent; component membership has support. The acceptance reason must identify any cross-application relationship and its evidence. If an existing relationship changes after acceptance, fail safe to needs-review at read time rather than silently transplant the claim into a different scheme. Never treat every application sharing site_id as the same scheme.

ACCEPT requires a resolved non-null site_id and non-unclear scope. Resolving a pending claim's null site or unclear scope creates a new assertion and a reviewed correction link; it never edits the original. Claim validation permits genuinely ambiguous evidence to remain pending, but rejects malformed or missing required evidence. Stage-check acceptance requires all three stage-source fields; it does not promote the quantity qualifier.

### ah_claim_events

| Column | Type / nullability | Meaning |
|---|---|---|
| id | INTEGER PK | Immutable event identity |
| claim_id | INTEGER FK ah_source_claims.id | Subject assertion |
| sequence | INTEGER, CHECK >0 | Contiguous sequence per claim |
| previous_event_id | INTEGER FK ah_claim_events.id, nullable | Previous event on this claim; null only for sequence1 |
| action | VARCHAR(20) | ACCEPT / REJECT / NEEDS_REVIEW / WITHDRAW / CORRECT / SUPERSEDE / CONFLICT / REVERSE_LINK |
| related_claim_id | INTEGER FK ah_source_claims.id, nullable | Replacement or competing assertion for link actions |
| reversed_event_id | INTEGER FK ah_claim_events.id, nullable | Existing link event being reversed |
| source_checked | BOOLEAN | True only on ACCEPT after passage/identity check; false on all other actions |
| scope_checked | BOOLEAN | True only on ACCEPT after scope linkage check; false otherwise |
| stage_checked | BOOLEAN | On ACCEPT only: whether supplied stage evidence was checked; false otherwise |
| actor_id | VARCHAR(200) | Reliably attributable authenticated/operator reviewer; no extractor acceptance |
| reason | TEXT | Nonempty human-readable decision and evidence rationale |
| recorded_at | TIMESTAMP | Decision time |
| request_key | VARCHAR(200), UNIQUE | Idempotent review operation identity |
| request_hash | VARCHAR(64) | Canonical requested event hash for exact-replay detection |

Constraints: UNIQUE(claim_id,sequence); indexes (claim_id,sequence), related_claim_id and reversed_event_id. CORRECT/SUPERSEDE/CONFLICT require related_claim_id != claim_id and no reversed_event_id. REVERSE_LINK requires reversed_event_id and no related_claim_id. All other actions require both null. ACCEPT requires source_checked and scope_checked true; other actions require all check flags false. Previous-event linkage must refer to the same claim and sequence-1 (validated within the serialised writer transaction; unique sequence prevents races). Event request_key is unique across all claims.

Application-level UPDATE/DELETE of either table is forbidden. Future production migration must include reviewed DB enforcement rejecting UPDATE/DELETE (and PostgreSQL TRUNCATE) on these two tables, or a dedicated restricted writer role plus equivalent guarantees; do not claim Python conventions alone make records immutable. Preferred mechanism is table-scoped deny triggers, not changing shared service-role permissions. SQLite test equivalents reject UPDATE/DELETE. Administrative repair/removal is outside this application workflow and requires separate authority. No such triggers or roles are created now.

## 3. Passage identity and reviewer checks

Passage identity is (Document ID, captured content/extracted-text version if available, locator, passage_hash), not URL alone. Offsets are optional but, when present, must select the exact passage_text from the referenced captured extracted-text snapshot. For OCR/manual transcription without stable offsets, preserve page/section locator and exact captured wording; reviewer checks it against the document. Missing byte hash is explicitly visible, not evidence of immutability. Do not recalculate a historical hash from changed content and claim it was the original capture.

For first import, missing passage, missing Document or ambiguous document/application linkage rejects the import or leaves a valid captured claim pending; never qualified. Numeric narrative cannot be parsed into a newly verified quantity by this command. Human review checks the proposed typed quantity against the passage, scope and qualifiers. A differing interpretation requires a new immutable claim.

Five distinct concepts:

1. Source checked: reviewer inspected passage/document identity. ACCEPT also checks scope; not legal finality.
2. Quantity estimated: approximate/range/one-sided remains estimated even after source checking. Accepted exact maps to verified exact; accepted bounded/approximate maps to estimated. “Verified source” does not change quantity shape.
3. Planning approved: checked planning-stage evidence, not assumed from the count or generic application status.
4. Legally secured: checked operative obligation with relevant scope. If this cannot be checked, accepted quantity can still support discovery but stage projects as unresolved/reported-unverified. A signed agreement for a different phase does not qualify.
5. Current and available: current means selected within the specified planning context as of the available evidence, not exhaustive legal freshness. Availability for purchase is NOT a field or conclusion of this increment. No claim implies seller intent, ownership/control or market availability.

Document dates may legitimately be missing. That alone does not force rejection of otherwise checkable evidence; display date unknown and avoid date-based currency claims. No reviewer timestamp substitution.

## 4. Import, review, concurrency and history

Controlled command: dry-run by default; explicit apply against a local disposable target only in this increment. Validate complete manifest before transaction. Import returns original IDs on exact replay of import_key+payload_hash; same key/different payload is an error, not an update. A different key with an identical canonical assertion is REJECTED as duplicate_payload_use_original_key, returning the original ID/key. Never acknowledge an unrecorded alias as a successful import. Every successful key is durably stored on its assertion. Serialise duplicate checking in the same application lock as imports. Identity includes document/version, passage/locator, application, scheme/scope, metric/tenure, quantity and qualifier; origin metadata alone does not make identical evidence a new assertion. Independent documents remain distinct even when numbers match. No import-receipt table is added.

Reviews require expected sequence heads for every touched claim and a request_key. PostgreSQL: lock involved Application rows in ascending ID order, then involved claim rows in ascending ID order with SELECT FOR UPDATE; compare expected heads; append events in one transaction. Imports use the same Application locking order, including source/root applications, so review preview cannot silently race a new imported competitor. SQLite local tests use BEGIN IMMEDIATE before validation. No mutable head column needed: maximum sequence plus unique constraint is authoritative. Deadlock/uniqueness/stale-head failure rolls back and requires reloading; never automatic approval retry against different evidence. When an exact request_key+request_hash already exists, return that outcome without appending. A mismatch is an error. Preview token includes the set of claim IDs/heads for the selected application context; recheck under locks before applying.

Every operation for a scheme locks its scheme_application_id row, even when the source belongs to a different linked application. The preview token also covers eligible application membership and source/scope linkage values; a changed context requires a new preview. A review request appends one event atomically; compound review operations are separate previews/requests in this increment. request_hash covers claim/action/related or reversed IDs, flags, actor, reason and expected context/heads, excluding generated IDs and recorded_at. Empty/non-attributable actors, extractor ACCEPT requests and stale context are rejected.

State fold (ordered by sequence, never wall-clock date):

- No status event => PENDING. Latest ACCEPT/REJECT/NEEDS_REVIEW/WITHDRAW yields that review status; later re-review retains earlier events. ACCEPT never edits the claim. Reaccepting an unchanged claim requires a reason and current evidence check.
- CORRECT on old claim points to a separately accepted new claim correcting capture/interpretation of the same source assertion. It may correct wrong/unclear scope or site assignment, with the same document and original locator, explicit evidence rationale and both old/new contexts previewed and locked. A corrected passage at that locator must be identified in the reason. Metric/tenure remain compatible. It cannot suppress a different document or unrelated assertion. SUPERSEDE requires compatible metric/tenure/scheme/scope and a separately accepted replacement supported by checked stage evidence and a reviewer reason establishing applicability. Both retain earlier evidence; neither operates merely because a document is newer.
- SUPERSEDE requires both assertions accepted and replacement stage/authority sufficient for the stated context. CORRECT may link an erroneous pending/rejected old assertion to an accepted replacement. Cross-application linkage needs reviewed scheme continuity. Neither may form a directed cycle.
- A live replacement edge makes the old claim historical/nonselected. Rejection/withdrawal of its replacement does NOT silently resurrect the old claim: context becomes needs-review until the link is reversed or a new valid replacement is accepted. Two incompatible live successors remain conflicting; don't select the latest.
- CONFLICT records a reviewed relationship; independently detected same-context inconsistencies also produce conflict. REVERSE_LINK references a prior CORRECT/SUPERSEDE/CONFLICT event on the same owning claim, with a reason. Reversal is terminal for that link event; re-establishing it requires a new link event, not reversal-of-reversal. Lock/check both endpoints for relationship events.
- “Conflicting” is an assessment of several claims, not a destructive status replacement. Two ACCEPTED source transcriptions can remain in conflict. Reversing a CONFLICT annotation does not suppress a numerically detected contradiction.

First increment has no automatic acceptance. Future extractors may emit pending claims with real document/run provenance through the validated boundary; they cannot create ACCEPT events, pick a winner or upgrade legacy counts. A general review UI and automated estimated-claim acceptance are deferred.

## 5. Deterministic selection for search and buyer matching

Return a shared SelectedAHClaims projection: context identity and planning stage; outcome per metric/tenure/scope; selected claim IDs; qualified alternatives; pending/unverified alternatives; excluded/historical IDs with reasons; scope/source/date labels; reason code and explanation. Feed the same projection to both fact builders, filters, detail, feed, packet and CSV. Missing source linkage cannot be repaired by the projection.

Algorithm:

1. Resolve the existing operative application/scheme/phase context. A consented scheme and a separate active amendment/proposal remain separate context groups. Do not collapse everything on a Site. If context membership cannot be established, return unknown/investigate with the ambiguity.
2. Load all claims/events for eligible linked applications in one consistent read. Source ownership/scope links are revalidated; pending and rejected/history remain explainable, not eligible numeric evidence.
3. Fold events and reviewed replacement edges. No ranking by newest document, capture time, highest count or generic source confidence. Different-authority documents require a reviewed supersession basis to resolve relevant disagreement; date alone cannot do it.
4. Group by metric, tenure where applicable, supported application/scheme context and scope key. Unchecked planning_stage labels NEVER partition contradictions away. Supported distinct application contexts may remain separate; ambiguous membership remains investigation. Even a checked stage alone cannot choose the count: a supported explicit review/supersession relationship is required to resolve conflicting applicable evidence. Never compare retirement-component count72 with whole-scheme total82 as competing AH counts; never use retirement to infer OPSO tenure. Tenure counts do not add to a scheme total; summation is deferred in v1.
5. One accepted claim: use its original qualifier and scope. Several equivalent accepted quantities/qualifiers: show one equivalent value with all corroborating source IDs (stable ID ordering is presentation only). Different exact values, different non-equivalent bounds, or material contradictions remain alternatives/investigate. Overlapping ranges are not intersected or averaged. A pending relevant contradictory claim blocks a definitive current answer; unknown/unreviewed scope cannot be used as proof of exclusion.
6. Apply existing spec020 numeric rules to each qualified alternative jointly for the requested minimum/maximum. Do not meet minimum with one source and maximum with another. Conflicts are investigate unless all relevant supported alternatives individually establish nonqualification and no unresolved relevant alternative remains. Unknown never passes maximum as0. Generic low/medium/high bands remain deferred.
7. Component minimum leads are allowed with explicit component label. Component counts cannot establish a whole-scheme maximum, or disprove a whole-scheme minimum merely by being small. A component's supported count above a whole-scheme maximum can establish failure only where membership in the same scheme is checked. Never merge/count components twice.
8. If no accepted eligible quantitative claims exist, use the unchanged legacy assessment as reported/unverified, explicit unknown numeric route and investigation relevance where appropriate. A raw stored0 is not accepted zero. Legacy percentages/classification cannot override the new independently checked count; surface contradictions and preserve the independent percentage guard. Any percentage-based buyer rule must have a valid same-context basis and remain independently qualified.
9. Apply buyer exclusions separately. A count lead cannot override a retirement exclusion. Keep overall buyer-fit classification distinct from count outcome; estimates don't automatically create STRONG_FIT or availability claims.

Mandatory reason examples: `accepted_source_claim` (which source and scope); `equivalent_sources` (all IDs); `conflicting_counts` (each quantity/source); `pending_competitor`; `scope_unresolved`; `historical_replaced` (replacement and reason); `legacy_unverified`; `no_count_evidence`. Show readable wording, not only these codes. Include source checks versus unverified stage explicitly. For multiple planning contexts, show separately named leads; if existing UI cannot do so truthfully, return investigation rather than arbitrarily collapse them.

Fingerprint projection includes effective selected quantities, qualifiers, scopes, stage qualification, active material alternatives and decision-relevant provenance, not audit-only review comments or recorded timestamps. The currently tested full AHAssessment payload needs a bounded projection review when this new reader is implemented; do not blindly hash the entire event log. Readers never persist histories, refresh mandates or invoke evaluation.

## 6. Acceptance examples (not production source verification)

| Example | Import/review and selection | Search/buyer result |
|---|---|---|
| Focus School DC/085997, reported72 affordable retirement apartments within82 homes, disputed whole-scheme100/all_units | Until actual passage and scope are checked, retain legacy unverified. After review, accepted approximate72 claim scoped to named retirement component can be used independently of disputed percentage. Count82 is total scheme context, not another AH assertion. Reported10 market homes is not inferred subtraction. DC/094889/condition40 does not establish legal resolution until inspected. | Qualified approximate72 lies above55, so likely minimum50 lead with component/source label. Current legal position unverified unless stage evidence checked. Retirement-excluding buyer remains NOT_SUITABLE. No blanket high-AH grouping or availability assertion. |
| Unknown scheme | No claim rows or accepted explicit unknown claim. Do not turn absent source text into exact0. | Unknown for minimum50 and maximum50; explicit unknown route. Keep reported legacy narrative visible. |
| Authoritative whole-scheme exact0 — synthetic source-backed fixture, NOT a production site claimed found | Existing test Document contains explicit zero passage with whole-scheme scope and stage support. ACCEPT event checks source/scope; stage only checked if its supporting evidence is checked. No unresolved current positive competitor. | Minimum50 fails; maximum50 meets quantity criterion. Affordable-package exclusion can use checked whole-scheme zero. Component-only0 and raw legacy0 cannot do so. No private-count/0% derivation. |

For approximate44/45/50/55/56 at threshold50, retain spec020 outcomes: minimum fail/investigate/investigate/investigate/likely; maximum likely/investigate/investigate/investigate/fail. Exact48 fails minimum50 with no tolerance. Source60–80 likely minimum50, crossing45–60 investigate, up_to72 possible only. All same-record displays/export retain the same original quantities and qualifications.

## 7. Migration, rollout and rollback — plan only

Future migration must create ONLY these tables, constraints, indexes and table-scoped append-only protections, in an explicit transaction on PostgreSQL with bounded lock/statement timeouts. No existing columns/rows altered, no seeded claims, no automatic history backfill. Validate actual target schema and database identity; fail on incompatible pre-existing objects, not CREATE IF NOT EXISTS then assume compatible. Test on disposable PostgreSQL and SQLite. Do not run the broad platform migrate_schema command as a substitute: it can apply unrelated pending model changes. No startup/page-load DDL and no migration executed here.

Future rollout: migration approval separate from code approval and claim-import approval. Reader/writer default disabled; enable only after schema preflight and source cohort acceptance. If explicitly enabled but schema is absent/incompatible, report failure rather than silently erase claims. Disabled state continues the accepted legacy/unverified behaviour. Import writer requires explicit target and reviewer identity, no inferred credentials or UI side effects.

Rollback: disable reader/writer and restore prior approved executable. Retain claim/event tables and append-only history read-only; no DROP/delete/truncate, no revert of raw fields because they were never changed. Prior current evaluation pointers/history remain intact but freshness must not be asserted by rewriting hashes. Read-only audit export remains possible. Any destructive cleanup is a separate approval.

## 8. Focused verification plan

Do not repeat accepted candidate tests for documentation alone. After separately approved implementation:

- Schema constraints and FK rejection, mismatched existing schema, append-only enforcement, idempotent migration and retained-history rollback on disposable SQLite/PostgreSQL.
- Quantity combinations, null/unknown/zero, negative/nonfinite/precision, tenure/product distinction, document/date/hash and passage offset validation.
- Duplicate same key/same payload => same ID; same key/different payload => error; independent conflicting extraction => separate row; no implicit review.
- Two real concurrent transactions with stale preview tokens, sorted multi-claim locking, rollback on event uniqueness, exact review retries, import arriving during review. No mocked concurrency-only acceptance.
- Status fold, re-review, correction, supersession, rejected replacement, link reversal, cycles, competing successors, independent detected conflicts; no resurrected outdated claim without explicit review.
- Source-checked approximate remains estimated; unchecked legal stage stays unresolved; new date alone never wins; rejected/technical/component evidence cannot replace a whole-scheme claim.
- Original spec020 boundaries plus multi-document/multi-application disagreements, separate consent/proposal contexts and common search/matching selection. Preserve independent retirement exclusions.
- Full same-record qualified and legacy/unknown/source0 paths across Explore, detail, actual CSV assembly, feed, packet and fingerprint projection. Real rendered/export acceptance remains separate from payload-unit tests.
- No writes on read, no model calls, no automatic migration/import/backfill; effective changes alter fingerprint, audit-only notes do not. Execute bounded affected regressions and exact-commit isolated comparison after code changes.

Real-source cohort gate: actual reviewed Focus School passage/scope, true unknown and genuinely evidenced whole-scheme zero must be obtained independently. Synthetic source fixtures establish code behaviour only. Release remains blocked until that acceptance and measured stored-result impact are reviewed.

## 9. Measured Render findings, 30 September 2026

Workspace verified by list_workspaces as My Workspace, tea-d9qbf8jm8hqs7385cu0g, exactly matching user confirmation. Every following request used that explicit workspaceId; no global workspace state or service settings were changed. list_services confirmed ownerId, repository maxrose26/PropertyAIgent and service IDs before deployment inspection. Two latest deployment records per service were inspected.

| Service | Verified service ID | Current live deployment ID |
|---|---|---|
| PropertyAIgent web | srv-d9qbl7qjnfac73d8nieg | dep-damobmjlp5dc73bsi96g |
| Weekly opportunity sync | crn-dag1lbv40ujc73de74mg | dep-damobmk4419c7381o2a0 |
| Intelligence processing | crn-d9sv93vavr4c73f98rag | dep-damobmhd1p3s73f0vqug |
| Historical rebuild | crn-d9uq0sijobas73bf7s2g | dep-damobmo0639c73ar81dg |
| Daily discovery (suspended) | crn-d9sv93vavr4c73f98rb0 | dep-damobmifbmqs73d0ji80 |

All five live deployment records identify commit 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a, deployed18September2026. GitHub fetch_file at that exact commit, app/policy/buyer_matching.py, returned `BUYER_MATCHING_POLICY_VERSION = 4` (blob5949a26d180611cd0269626b3d93c9bf47c65e0d). Local git-object inspection independently agrees. Thus current deploy-artifact evidence establishes matching4, not5, for these five identified services. This is not an inspection of in-memory process state or proof that5 was never run historically, manually or elsewhere.

Daily discovery remains suspended, autoDeploy off, start command /bin/true. No change made. Other service settings were observed only, not altered. No inference that weekly sync is a paid evaluation runner: its deployed script invokes sync_opportunity_monitoring_state, not an evaluation call.

Supabase SQL-editor attachment was retried once and failed with Emulation.setFocusEmulationEnabled timeout before editor access; no SQL was entered/executed. Actual stored mandate/current-state/history combination counts remain UNKNOWN, not0. Render's PostgreSQL query tool is not a substitute for this Supabase database; no credentials were extracted.

Version implications: retain local5 pending release review. A release from identified matching4 artifacts to5 changes otherwise-identical mandate fingerprints broadly; agents also hash the mandate fingerprint and matching version. This does not imply every historical stored result currently matches4, or that all stored tuples need paid evaluation. History's evaluation_policy_version string omits buyer-matching version, so cannot establish it by string search.

Outstanding bounded DB measurement: read-only schema inventory, mandate totals/active/archived/baseline-present, actual distinct (buyer_mandate_id,subject_anchor_id,acquisition_type) in current state versus history, successful versus failed-only and subject type. Read-only offline recomputation classifies exact changed hashes, already stale/unknown and missing inputs; no bootstrap/claim/evaluate functions. Where historical inputs cannot be reconstructed, report actual tuple inventory as an exposure ceiling, not confirmed invalidation. Do not multiply sites by buyers. Reader stale labelling, deterministic baseline recomputation and future model-capable invocations stay separate, with no automatic refresh authorised.

## 10. Review decision requested

The Product Owner approved local implementation and the three preflight amendments. This is not deployment approval. No production write, import, evaluation refresh, paid call, push, merge, deployment, discovery resumption or P0-A change is authorised. P0-A Gate A remains open.

## 11. Local implementation boundary

The two tables live in separate SQLAlchemy metadata (`app/db/ah_claim_schema.py`), deliberately outside Base.metadata and automatic startup creation. Only the explicit local migration creates them and their guards. The controlled one-claim/one-event operator command is `python -m scripts.ah_claims_local`, with mandatory explicit `--database`; no DATABASE_URL lookup or application bootstrap. Import/review default to dry-run. `--apply` is required for a local write. The command rejects remote write targets. This is a trusted local operator tool, not a public authentication/review service; extraction code is not wired to it. Reviewer identity is operator-supplied and recorded, not an independent external identity-provider attestation.

`PROPERTYAIGENT_AH_SOURCE_CLAIMS=1` explicitly enables the shared source reader; default is disabled. Missing/incompatible enabled schema fails visibly. Rollback disables it and retains both tables. Scope corrections preserve the original source quantity/qualifier/passage when changing scope, so an unrelated assertion cannot be relabelled a correction. Quantity/passage interpretation corrections within the same scope retain the same document/locator and require a human rationale. Source text hashes use actual UTF-8 captured extracted text; the existing whitespace-normalised Document.content_hash is never passed off as a byte hash.

SQLite guards also reject conflicting INSERT OR REPLACE, avoiding its special delete-trigger semantics. SQLite quantities that cannot round-trip losslessly at six decimals are rejected, not rounded. Readers preserve caller SQLite transactions without autoflush; PostgreSQL reader snapshots use a separate repeatable-read, read-only transaction. Relationship explanations are displayed but audit-only prose is excluded from the agent fingerprint projection.

Local runtime validation is performed only on disposable SQLite memory/file databases. PostgreSQL DDL compilation does not count as runtime migration/concurrency validation: no PostgreSQL server/container runtime is installed in this workspace. PostgreSQL AH schema/migration execution therefore fails closed pending runtime validation and exact server-side schema verification. That implementation/test gate remains open. No local execution here substitutes for actual-source cohort acceptance, measured stored combinations, or release approval.

## 12. Approved disposable PostgreSQL verification boundary — 30 September 2026

Authority: local verification only. Ordinary PostgreSQL migrate_local, import,
review and enabled selection remain denied unless their SQLAlchemy Engine was
created by the disposable-verification factory in the current process. There
is no enabling environment flag, CLI switch or monkeypatch. SQLite is unchanged.

The trusted operator runner creates a private network/PID/mount namespace with
loopback only, an empty HOME and a fresh initdb data directory. Before database,
role or schema writes it checks the connected PostgreSQL system identifier
against pg_controldata for that directory, the server PID/data directory against
postmaster.pid, process UID/network namespace, server port and start timestamp.
The namespace must differ from the launcher namespace. An unguessable run ID,
private owner-only marker and per-case manifest bind all subsequent connections
to that cluster. Reject inherited production database/model/config inputs and
repository/ancestor dotenv files. No arbitrary URL or external credentials.

The runner provisions a per-run LOGIN role with NOSUPERUSER NOCREATEDB
NOCREATEROLE NOREPLICATION NOBYPASSRLS and no role memberships. It owns only its
objects inside runner-created case databases, not the database or cluster.
PUBLIC database/schema rights are revoked; only CONNECT and public-schema
USAGE/CREATE are granted for this test. Reading pg_control_system is granted
solely to attest the cluster. Cluster administration is confined to the runner;
application tests use the restricted role. Each case uses the normal public
schema and the actual existing Base tables plus the unchanged AH tables.

Factory admission checks filesystem/namespace proof and then the actual server
system identifier, database OID/name, restricted role, search_path and start time
before registering the Engine. Every AH transaction/schema verification repeats
connection identity checks; unregistered Engines fail before a connection/write.
Authority is scoped to that engine/process and ends when it is disposed/revoked.
A host named localhost is never authority. This protects against configuration
mistakes, not a malicious operator/root who can rewrite Python or PostgreSQL.

migrate_local uses the SAME TABLES, constraints, indexes and protections and the
same transactional creation body for the disposable PostgreSQL path. No raw-DDL
substitute for AH schema, reference table, alternate test schema or skipped
validation. On first creation it refuses pre-existing AH objects, verifies their
structural catalog inventory and trigger/function semantics, then records the
server-normalized catalog signature from that exact creation transaction.
Subsequent verification compares the full columns/defaults/constraints/indexes/
triggers/function catalog, including CHECK expressions and enabled/validated
flags, to that trusted in-process signature. Data are excluded. Creation rolls
back atomically; failed attempts clear the signature. A new process cannot bless
pre-existing AH tables. Production verification/adoption of existing PostgreSQL
schemas is deliberately NOT implemented by this disposable proof.

Native tests must exercise restricted-role first/repeat migration, failed-DDL
rollback, catalog/protection tampering, UPDATE/DELETE/TRUNCATE, real concurrent
imports/reviews, corrections/supersession/conflicts, unknown/component/source-zero,
shared consumers, reader-disable rollback retaining history and connection reuse
after database failure. Source fixtures remain synthetic. Bad manifests, wrong
server/database/role/namespace, unregistered engines and ordinary entrypoints
must fail closed. No network/model access; no production inputs.

Dependency correction: the repository requires psycopg[binary] version 3, not
psycopg2. Use SQLAlchemy postgresql+psycopg explicitly. The previous handoff's
psycopg2 requirement was erroneous. Ship a complete pinned dependency manifest,
a separate isolated setup operation, and preflight both imports and test
collection before initdb. Record Python, distributions, psycopg/libpq, PostgreSQL
binaries and runner hashes even on failure; absence never implies zero failures.

A native pass proves these code paths against the recorded disposable PostgreSQL
version/role, with real SQL transactions and database enforcement. It does not
approve production migrations, Supabase/pooler/permission compatibility,
existing-schema adoption, real-source claims, rendered live UI, evaluation
refreshes or release. Keep those gates separate from P0-A.
