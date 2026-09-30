# AH application-scope repair: observed fixture mapping

30 September 2026; read-only application UI inspection. Production database rows
were not exported and direct SQL was unavailable. These are production-shaped
fixtures grounded in observed UI fields, not a claimed complete database snapshot.
No portal source was accessed, claim imported or production record corrected.

## Hyde: observed failure and exact relevant shape

Site 107, Stockport, detail route Scheme_Detail?site_id=107. The failed cloud
candidate a572d752285e442254d40b783c28d86b6e2f6904 displayed DC/098428 in the page
header but older DC/095922 zero in its main AH headline and Structured summary.
The older reference and unverified qualification were visible; qualified minimum
and maximum filters excluded it. That qualification did not cure application-scope
leakage into the current headline. Web was rolled back to 6fd4202.

Fresh inspection of the rollback version confirms:

| Observed field | Current application | Alternative application |
|---|---|---|
| Reference | DC/098428 | DC/095922 |
| UI application group | Submitted / pending | Submitted / pending |
| Type | None | None |
| Status | Unknown | Unknown |
| Decision text | Objection (Consult with Neighbour Auth) | Objection (Consult with Neighbour Auth) |
| Received | 24 February 2026 | 22 May 2025 |
| Residential intelligence | No extracted intelligence; current preferred version | 440 total homes; 0 affordable |

The current-preferred rationale is most recent qualifying application, intelligence
not fully reconciled. The alternative is explicitly listed as not combined with
current figures in the rollback version's Residential Mix. The earlier test's
Withdrawn status was wrong for this observed shape. Neither a Granted status nor
an operative consent should be invented to reproduce the leak. Preserve the
neighbour-authority objection text without changing global planning decisions.
Screenshots and rendered DOM are retained alongside this record.

## Other controls and provenance limits

Focus School site78/DC/085997's production count72 remains a legacy unlinked count,
not an imported claim from the October2024 Affordable Housing Statement. Its source
statement separately supports72 retirement apartments plus10 private houses;
final Condition40 wording and current tenure terms remain uninspected. Preserve
specialist-product exclusions and do not infer acquisition availability. Production
party data currently names Anwyl Partnerships as applicant; Westshield/Housing21
remain separately dated source evidence, not a production update.

Wall Hill site32/OUT/355454/25 was observed as26 total with AHunknown. Southlink
site25/FUL/355201/25 was observed as147 reported/unverified proposal. They are
controls for missing evidence and single-application legacy values, not proof of
current legally secured AH or transaction availability.

Qualified current nonzero with older contradiction, distinct components, and
same-application document revisions are constructed offline contrasts. They must
be labelled synthetic/source-qualified test evidence, not claimed live imports.
No council or application identity may be merged merely because addresses match.
A genuine revision means multiple claims explicitly sharing application/scope
with supported revision/selection semantics, not choosing the newest filename.

## Acceptance boundary

Application-context selection is separate from operative permission selection.
Do not solve by globally choosing the newest date for planning. Current AHunknown
must stay unknown; earlier evidence remains attributed history/alternative and
cannot satisfy either numeric boundary or fresh buyer-fit input without a reviewed
relationship/scope decision. Same-application conflicts/components remain visible.
Stored evaluations are not refreshed or relabelled current by this repair.
