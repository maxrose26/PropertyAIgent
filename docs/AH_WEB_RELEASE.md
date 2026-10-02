# AH web-only batch — release candidate

Base: remote master/live web6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a,
rechecked GitHub30September2026. Branch release/ah-web-truthful. Isolated worktree;
not a merge of the P0-A/AH/revisit development branch.

## Product outcome

Existing counts remain visible as reported; source and scope unverified. Qualified
headline/CSV count stays empty for unqualified legacy extraction. Unknown remains
unknown and cannot satisfy numeric minimum/maximum, including zero maximum.
Explore offers an explicit unknown investigation route. No universal AH minimum.
Pure count contract retains exact/no tolerance and qualified approximate10% band.
Component-count and current-tenure caveats remain; no production count is promoted
just because the supplied Focus statement is known to the Product Owner.

Percentages are retained as AH Reported Percentage and withheld from the qualified
CSV percentage. Dashboard cards label legacy percentage scope unverified and never
assert '100% affordable'. Detail removes generic high-confidence/all-units labels.
Unknown tenure is unresolved, never 'no affordable homes'. Dated delivery/operator
role labels use existing ControlRelationship evidence; no contacts/ownership/sale
inference. No source-linked claims are imported, even in the legacy-schema harness.

The existing-policy buyer-fit renderer is explicitly qualified. Buyer matching,
policy version4, persistence and all stored results remain unchanged. This is not
activation of locally developed policy6. Packet assembly and paid agents are not
changed or claimed repaired. Stored results/history are preserved; refresh remains
deferred. Browser HTTP CSV delivery and actual live feed inclusion await release
acceptance. Missing feed membership is never proof of exclusion.

## Scope boundary and tests

No changes to app/db, app/pipeline, app/revisit, scripts, render.yaml, buyer_matching,
buyer_profiles, production requirements or migration scripts. No new source-claim
schema/selector/store dependency. Original production Base metadata is used for
all fixtures. Git diff against base checks protected paths unchanged.

Focused suite: classification/tenure/threshold, existing AH scope, residential mix,
site profile and ownership rendering.173 tests+10 subtests passed before review,
zero failures/errors/skips. Initial failures: three newly qualified tenure-caption
assertions and the already resolved legacy30 assertion. Added qualification
expectation, kept unknown-tenure assertions, carried accepted legacy visibility
AND non-qualification checks (30 retained,490 kept separate).

Actual Streamlit AppTest walkthrough: Focus legacy72+82, Southlink legacy147,
WallHill26total/AHunknown, currentHydeunknown and cross-council negative control67.
The four emitted selected-record CSV rows were parsed. No source-confirmed numeric
match is claimed: all legacy counts are unqualified; minimum50 and maximum0 do not
match them. Selecting unknown keeps investigation accessible. Actual detail and
scheme/feed card functions render source/scope caveats. Focus dated party roles
are rendered from baseline evidence tables. No browser HTTP delivery assertion.

New ah-web.yml runs this suite and walkthrough on push/PR, with pinned isolated
venv and no production secrets. Tests deny external network, use disposable SQLite,
and upload only logs/JSON/CSV/XML, never the fixture database. No deploy step,
cron job or paid evaluation. Standard GitHub runner only. Workflow still local;
first hosted run not yet observed. Existing broad P0-A CI is not part of this branch.

## One release decision

Approve publication of this exact reviewed branch, automatic hosted checks, and
conditional deployment of this exact SHA to web srv-d9qbl7qjnfac73d8nieg ONLY after
those checks pass. Use Render Dashboard Deploy a specific commit, which disables
web auto-deploy (documented consequence included in approval). Do not push master,
merge, sync Blueprint or build/update other cron services. Intelligence cron also
tracks master with On Commit, so a master push would not be web-only.

Verify deployed+app-reportedSHA, four-record wording, min/max investigation route,
actual selected CSV HTTP download and no errors. Rollback is web-only specific
previousSHA6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a, keeping auto-deployOff.
No database rollback needed: no schema/data mutation authorised. Discovery remains
suspended at/bin/true; no production imports, profile activation, paid calls or
stored matching refresh. Final Focus tenure/real-source-zero, source-linked imports,
measured stored impact and bounded P0-A/revisit trial remain separate work.

## Independent review

Reviewer inspected exact candidate 42aaa55, its diff, JUnit and emitted CSV.
No blocking defect found. One observed caption inconsistency was corrected: empty
organisation sections now explicitly refer to application-summary fields, while
dated document-backed roles remain separately visible. The walkthrough asserts
Westshield/Housing 21 visibility and absence of the misleading empty captions.
Protected pipeline, database, matching and Render paths remain unchanged.

## 30 September 2026 — repair after failed live acceptance

The cloud equivalent c64def4371ec569210a496470d3aaa2e888b5b02 passed hosted
run 36739383520 but failed the Focus School live detail check. The web service
was rolled back to 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a; Auto-Deploy Off.
Discovery remains suspended at /bin/true. Earlier release approval is spent;
this repair requires its own exact-SHA deployment decision.

Observed trace: existing SchemeIntelligence.affordable_housing_status held
`legally_secured`; legacy_assessment copied it into AHClaim.stage;
AHAssessment.label placed the raw stage in Explore's AH Assessment and detail
headline/summary, and columns exported it as AH Stage. The detail planning and
AH sections also called st.write(assessment.columns()), exposing internal JSON.
The earlier fixture used `proposed` and did not assert the absence of JSON.

Repair: a shared presentation-only stage label says "Reported stage: legally
secured; operative terms unverified". Count qualification alone cannot establish
legal-stage provenance. Stored stage, assessment payload, count thresholds,
matching policy and fingerprints are unchanged. Both detail JSON dumps are
replaced by application/scope, source/date, review and operative-term notes.
CSV uses the same qualified stage label. No schema, production data, pipeline,
cron, matching or dependency change.

Focus expected presentation: 72 affordable homes, reported; source and scope
unverified under DC/085997. Reported stage: legally secured; operative terms
unverified. Final approved conditions and tenure terms require checking;
acquisition availability is not established. Whole-scheme classification requires
source and scope review. No whole-scheme 100% or all-social-rent confirmation.
The known October statement is not silently imported into production evidence.
Source-qualified 72-apartment reasoning remains separate from legacy storage.

Regression fixture now includes the observed 82 total / 72 AH / 100% / high /
all_units_affordable / legally_secured shape. It is a bounded reproduction, not a
production database export. The production-compatible ORM/reconciliation/page
path is exercised offline. The new actual-shape regression fails against the
rolled-back candidate's identical local tree (823356b), detecting its dictionary
leak. Repair verification:175 tests and10 subtests pass; actual Dashboard,
Explore and four detail pages render; four selected CSV rows are emitted and
parsed. Focus exports72 in AH Reported Count and blank Affordable Units. Unknown
Wall Hill and current Hyde stay blank; Southlink147 stays reported. Dashboard
checks the same fixture rather than relying only on an isolated card renderer.
No live-feed membership or browser HTTP download proof is claimed.

Independent review found no material code defect and inspected the actual local
render/CSV evidence. The new hosted run must pass on the published exact SHA;
its result and tree identity accompany the release decision, not this historical
prepublication record. No broad/native PostgreSQL rerun is needed for this
presentation-only delta.

Live acceptance order after a NEW approval:
1. Web-only exact-commit deployment to srv-d9qbl7qjnfac73d8nieg, Auto-Deploy Off;
   verify Render deployed SHA. Never push master or deploy a cron.
2. Focus site78 first: Overview, Planning Position and Residential Mix. Confirm
   reported72, qualified legal caveat, no raw AH JSON, no whole-scheme100%, no
   confirmed all-social-rent or acquisition availability claim.
3. Explore and Dashboard same-record wording; unknown and legacy controls.
   Dated organisation roles do not imply ownership or sale authority. Missing
   limited-feed membership is not an exclusion result.
4. Select records in Explore, download CSV through the browser, inspect actual
   bytes: legacy counts in AH Reported Count; Affordable Units blank; qualified
   AH Stage wording; unknown counts blank and application identities preserved.
5. Any material acceptance failure: stop, web-only rollback to6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a,
   verify Live SHA and keep Auto-Deploy Off. Rollback restores the previous
   version, whose existing wording limitations are not thereby accepted.
