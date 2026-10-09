# Specification 031 L0: retained dependency attribution

Additive offline verification only. No verifier, orchestrator, application change,
external request, production connection, model call or invalidation is authorised.

## Contract

`dependencies.py` defines one type per field/consumer relationship: direct factual,
context, or discovery. Multiple relationships to one application are allowed. Only
an exact qualified direct edge establishes its stated fact. `status_verified_at`
certifies only that application's planning-status/decision verification as of its
recorded time, not count, AH, control, document currency or a related application's
freshness. Missing verification is UNKNOWN, not stale or current.

`reconstruct.py` reuses the actual buyer-family, operative reconciliation and
opportunity-universe functions against the hash-pinned privacy-minimised retained
8 October snapshot. It preserves the original replay's omitted applicant/company/
title inputs as unresolved. Linux seccomp denies network creation and sending
before application imports. SQLite is seeded offline, then reads are guarded;
flush, commit and DML are rejected. No production DATABASE_URL is used.

Run with the three retained private inputs using --snapshot, --metadata,
--accepted-replay, --evaluation-date (2026-10-08 or 2026-10-09), and --output.
Detailed buyer-linked output is a private review artifact, not a repository export.
Input hashes fail closed; this is a reproducible dated evaluation, not a general
production exporter. The selection clock is frozen; freshness-adapter process UTC
is recorded separately and does not change facts or dependency selection.

## Manifest

Subject ledger: existing feed key, canonical existing universe identities when
joinable, site/allocation and scope, per-buyer considered/visible/representative
membership, non-application factual inputs and unresolved attribution.
Edges: exact application ID/reference/council, dependency type, fields, consumers,
source URL/document IDs where captured, source-selection reason, operative role,
truth label, status verification time/scope, candidate material consumer impact,
generated-record qualification and uncertainty.

Consumer lists are conservative impact candidates, not proof that every field
changes every consumer. Context selection readscope is not proof of causal input.
Risk cohorts propose review priority; they never authorise refresh, acquisition
ranking, invalidation or AI processing. Context/discovery-only records have a
separate review-only scope. No numeric freshness score or universal expiry exists.

## Measured retained coverage

8 October: 439 subjects per buyer; 213 with application edges and 226 strategic
subjects without application edges. 1,509 edges: 756 direct, 740 context, 13 discovery;
648 distinct applications; 210 exact direct status-source applications.
9 October selection-date projection: 440 subjects per buyer; 214 with application
edges and 226 without. 1,514 edges: 760 direct, 741 context, 13 discovery; 649 apps;
211 direct status-source apps. One added subject is a clock effect, not new evidence.

All 249 recorded allocation narratives remain withheld because prompt v6–v8 is
ineligible under v9. Their individual summary IDs/context fingerprints were not
retained. None is automatically an AI regeneration candidate. Eligible retained
strategic-subject population is 226, not all 287 production allocations.

## Remaining input gate (no queries executed)

A complete *current* census requires a separately authorised consistent read-only
snapshot of: current minimum structured active buyer/mandate facts; eligible site/
application/phase and allocation links; structured applicant/company/title facts
actually consumed by selection; per-summary allocation ID, prompt version and
context/dependency fingerprint; and exact supporting-application status/decision/
source dates/status_verified_at. No contacts, buyer narratives or document bodies.

Smallest missing allocation projection: summary ID, allocation FK, prompt version,
planning-context fingerprint and generation timestamp, joined only to the selected
allocation IDs. Exact table/column names must be checked against the accepted model
before any future query. Applicant/company/title omission cannot be filled using
AI or broad text exports. Reuse the previously accepted minimised structured
representation, after an explicit consumer/field permission gate.

Do not claim a first-bootstrap traffic reduction from 1,270 applications: the
retained map narrows review to 234 direct-source candidates plus 415 review-only
context/discovery records, but unresolved inputs and unrepresented applications
prevent an operational coverage guarantee. L1 may implement an offline bounded
verifier contract only after separate authority; no L1 work is included here.
