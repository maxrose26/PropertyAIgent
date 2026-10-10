# Buyer-facing dependency observation — OFFLINE PROTOTYPE, NOT ACCEPTED

Base: `183570e0c940d28b51b9f05a5dbf47f56dff37b2`. No product source changed.
Dedicated action: `launch:observe_buyer_facing_dependencies`.
Proposed machine: `legacy-freshness-dependency-observer`.
No production policy grant is supplied or installed. Do not execute against production.

The command uses the actual input loader, stored mandate resolution, buyer family
assessment and family/member objects. It accepts exact references already emitted
by the existing planning-freshness adapter; ambiguous ID resolution/conflict is UNKNOWN.
Allocation policy is not converted into an application fact. Context/discovery edges
are not inferred from same-site membership: absent authoritative attribution remains
UNKNOWN. Counters include zero context/discovery counts explicitly.

## Blocking resource finding

**NO-GO for live authority.** The canonical loader uses full ORM populations and
lazy document/control context, before output/population checks. Query limits and
statement timeout constrain statements, not input byte/memory consumption. A
120-second SIGALRM is not an independent process deadline around native calls.
The existing 512 MB Render service shares capacity with the live web process.
No safe complete-production resource profile is established by small SQLite fixtures.

Do not treat proposed limits (20 buyers, 12,000 families, 20,000 subjects per buyer,
40,000 output rows, 2 MB JSON, 12,000 SQL statements, 120-second timer) as accepted
production ceilings. They are prototype fail-closed checks; input bytes/memory,
independent process termination and cancellation cleanup need a separately reviewed
bounded offline solution. No new service or production architecture change is proposed.

## Tested scope and deferred acceptance

Synthetic tests cover actual family traversal (a synthetic fit table is explicitly
patched in that fixture), excluded/related members, unknown allocation attribution,
output minimisation, write/commit rejection, replacement transaction rejection,
Python-level networking/subprocess/model denial and budget/output aborts.
They do not prove production cardinality, PostgreSQL snapshot/READ ONLY enforcement,
actual all-buyer mandate behavioural isolation, retained Failsworth/Southlink/Hazelhurst
acceptance, native cancellation or a complete context/discovery export.

READ ONLY / REPEATABLE READ controls are implemented for PostgreSQL but not rehearsed
natively in this checkpoint. No schema migration. No production evidence or private
structural artifact is committed. Correlation accepts the reviewed assembler's `data`
shape and retains missing IDs as UNRESOLVED rather than inventing expected changes.

Model/HTTP guards cover the reviewed Python path, not arbitrary native networking.
Importing the canonical evaluator transitively imports OpenAI; constructors and
request paths are blocked, rather than falsely claiming it is never imported.

Runtime code must match exact SHA and have clean tracked/untracked source paths.
The existing Render web shell can retrieve small stdout artifacts; this prototype
has not established reliable transfer of an eventual 2 MB artifact.

Future policy delta, not installed: enabled exact machine identity; exact dedicated
launch action only; correct workspace; explicitly approved buyer IDs. Expected buyer
IDs must reconcile with admitted active rows. No historical Gate B action substitutes.
No live authority is requested until the blockers and remaining acceptance gates pass.
