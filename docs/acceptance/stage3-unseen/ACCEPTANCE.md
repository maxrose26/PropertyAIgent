# TO REVIEW — STAGE 3 UNSEEN AH VALIDATION

## A. Master stage / current gate / next gate

Master Stage 3 — AH evidence consistency. Current gate: real-source AH evidence and consumer-parity acceptance. Next gate: REVIEW decision on Stage 3 exit. Stage 2 remains accepted CLOSED_WITH_EXPLICIT_LIMITATION under PR57/head6ec6b65b66b59730ab27471529ffcad30010d448; no reopening or semantic change. PR58's evidence-gap ledger remains accepted. This candidate does not merge either PR.

**Recommendation: GO for bounded unseen validation, with explicit limitations; recommend Stage 3 closure only through the Product Owner's explicit decision on the nine blocked historical cases. Stage 3 is not administratively declared CLOSED by DEVELOPMENT.** No runtime semantic defect was demonstrated. This is six real-source cases, of which two contain substantive AH evidence and four are authoritative summary-only UNKNOWN controls. It is not six richly evidenced AH schemes, automated extraction acceptance, or broad generalisation proof.

## B. Candidate identity and changes

Base: `d253773a09690f27b150adb701c95f9aa3ee210f`, confirmed against remote master before work. Branch: `verification/stage3-unseen-ah`. Remote publication was established prospectively. Final head/tree/PR/hosted-run identities are supplied in the REVIEW handoff, avoiding a self-referential commit in this file.

Selection lock commit: `b8de19053713840daeecc18f821957807c13f9f5`. Expectation freeze commit: `beb26dd75aaa93daf7b3bdf26d73de385034ea71`. Frozen file SHA256: `48fbab1c8bce266de83f932ac4c2b485da837d003c7ed2eba6fcb317372945dc`. First software test publication: `b618dbdf9fd8765e4c7dc94396ef03606f1ea16c`, after both locks. No holdout assertion was changed after the first result. A later test edit adds denominator observations only.

Changed paths: this acceptance record; `SELECTION.md`, `FROZEN_EXPECTATIONS.json`, `SOURCE_REGISTER.json`, `FIRST_COMPARISON.json` in this directory; `tests/test_stage3_unseen_ah.py`; and `verification/web_ah/check.sh` adding the new test to the existing hosted selection. No application/runtime/schema code changed. Existing CI gates remain intact.

## C–D. Selection method and ordering proof

Before source interpretation, selected the lowest retained application ID in outline/reserved-matters categories in each of Bolton, Rochdale, Oldham, Tameside, Wigan and Bury. Selection used council, identity, address, category and exact URL only. Original ten and known AH design fixtures excluded. A schema inspection incidentally exposed Bury application1's proposal; it was explicitly excluded before selection. Existing AH answers were never read. Exact-reference searches found no primary candidate in tests/verification. A separate replacement scan found Wigan209 in allocation tests; it was not used.

Six primary candidates and one replacement per council were locked remotely before public review. Rochdale294/PL/2025/1221 returned only an application shell/CSS error; predetermined replacement621/24/00581/HYBR was used. No replacement was chosen because of its AH answer. Five other primaries were retained. No council-wide search/enumeration; only selected exact URLs and exact-identity searches for official committee alternatives. Maximum candidate allowance12; seven identities attempted; six achieved. Source URLs and complete-response hashes are in SOURCE_REGISTER.json; expectations were published before runtime comparison. Independent source-only review of both complex reports preceded comparison. The pre-frozen expectation hash is enforced by an acceptance test.

## E–I. Achieved cohort and authoritative sources

| Case | Council / exact identity | Authoritative reviewed evidence | Evidence shape / limits |
|---|---|---|---|
| H1 | Bolton21082/25; Land north of Arthur Lane; retained app71 | Official application summary, and26March2026 officer report, proposalparas1–2,p2;46;124–125,p19;137 | Up-to40 AH within up-to80; explicit50%; combined rent/intermediate tenure; futureS106; later13April2026 refusal |
| H2 | Rochdale24/00581/HYBR; land west of Hollingworth Road/off Rakewood Road; retained app621 | Official27November2025 committee item40 and linked report, paras2.6,7.29,7.248–250,13.1; conflict visually checked PDFp64 |47/309,15.2%; residential component of hybrid; internal25vs35 shared-ownership conflict; subject-toS106 |
| H3 | OldhamOUT/354782/25;1Skipton Street; app24 | Exact official application summary | Proposed2 dwellings; awaiting decision; AH absent from reviewed summary |
| H4 | Tameside25/00625/REM; Railway Inn,326Lumb Lane; app49 | Exact official application summary | Appearance/landscaping RM for1house, parent22/00846/OUT; approved19September2025; AH unknown; no parent borrowing |
| H5 | WiganA/25/099319/OUT; Middlecot Close,Orrell; app208 | Exact official application summary | Proposed3 dwellings; refused31October2025; AH unknown |
| H6 | Bury72367; former Wellington Pub,Stand Lane,Radcliffe; app16 | Exact official application summary | Proposed40flats; statusUnknown alongside decisionWithdrawn by Applicant20April2026; AH unknown |

One achieved case per council: six councils, not a GM source-coverage claim. Mix includes bounded quantity, explicit percentage, exact proposed total, residential denominator, tenure mix, real textual conflict, hybrid-component scope, RM scope, conditional legal stage, refused/withdrawn history and insufficient evidence. No wholly-affordable specialist or AH-offsite-contribution case was added merely to fill categories. Separate education/sports/car-park/open-space contributions are not treated as AH.

Exact council summary URLs are preserved per case in FROZEN_EXPECTATIONS.json. Complex document URLs:

- https://bolton.moderngov.co.uk/documents/s13300/Land%20north%20of%20Arthur%20Lane.pdf
- https://rochdale.moderngov.co.uk/documents/s119316/Application%202400581HYBR%20-%20Land%20to%20the%20West%20of%20Hollingworth%20Road.pdf
- https://rochdale.moderngov.co.uk/mgAi.aspx?ID=50212

Public HTML requests succeeded for five summaries; ordinary curl retrieved both reports and Rochdale agenda. Search/urllib failures are not evidence of absence. Exact linked PDFs for Oldham's form and Tameside/Wigan officer reports returned404; no access engineering followed. Bury's external document link was observed but not followed. Those four cases are therefore **summary-limited**, never source-confirmed zero. Full captures were hashed; durable Git retention contains pertinent excerpts/paraphrases, URLs, anchors, hashes and expectations, not complete source-document bytes or unrelated personal information. Retrieval date12October2026 is not a claim of exhaustive current-source verification.

## J–P. Frozen expectations and per-field comparison

States REPORTED/QUALIFIED/DERIVED/CONFLICTING/UNKNOWN in the frozen JSON refer to the independently reviewed source. Source-qualified proposed evidence is not proof of legally secured delivery, and is not automatically an installed product claim. Comparisons distinguish two levels: **L**, manual faithful transcription into existing legacy application/intelligence inputs through six consumer paths; **Q**, richer source-qualified claims through current claim/threshold/KPI/tenure/export helpers. There is no new importer/parser. No manual insertion into production. Current production answers UNKNOWN.

### H1 Bolton

| Field | Frozen source expectation | Actual existing software / classification |
|---|---|---|
| Reported/qualified count | Historical proposed upper bound40; no exact40 | Q retains upper40/valueNone, displays `Up to40`; minimum41 fails on that historical claim only. L has no representable bound field, preserves wording in reported tenure/evidence and returns current countUNKNOWN. **MATCH Q; SAFE_UNKNOWN current L**. Not a claim that qualified bound propagates through every live consumer. |
| Denominator | Up-to80, not fixed80 | Current refused scheme has no selected residential scalar or profile total. **SAFE_QUALIFIED_DIFFERENCE**: historical ceiling is not current operative quantum. |
| Reported percentage | Explicit historical50% | Application-specific report/export retains reported50 with refusal/history notes; current profile/buyer/packet percentage withheld. **MATCH reported; SAFE_QUALIFIED_DIFFERENCE current**. |
| Derived percentage | UNKNOWN; maxima division not a factual actual ratio | No actual percentage derived; consumer percentage remains unknown. **MATCH**. |
| Tenure/mix |75%social/affordable rent,25%intermediate;30/10 only maximum scenario | Faithful reported text preserved without splitting combined rent or naming intermediate as shared ownership. No qualified tenure point enters buyer gates. **MATCH reported; SAFE_UNKNOWN qualified counts**. |
| Scope | Whole historical outline proposal; no phase donation | L scope stays explicitly unconfirmed; Q historical whole-proposal label retained. **SAFE_QUALIFIED_DIFFERENCE L; MATCH Q**. |
| Status/legal |13April refusal supersedes favourable26March recommendation; S106 execution UNKNOWN | Historical/refused explanation; no active whole-site AH; no qualified buyer count; legal label says operative terms unverified. **MATCH**. |
| Funding/viability | UNKNOWN | No asserted terms. **MATCH**. |
| On/offsite | Proposed onsiteAH; other contributions separate | Source record preserves distinction; current numeric outputs do not claim an onsite/offsite quantity. **SAFE_UNKNOWN product**, not proof of automatic contribution extraction. |
| Conflict/chronology | No numerical conflict; recommendation/refusal dates must remain separate | Historical evidence retained separately from current position. **MATCH**. |

### H2 Rochdale

| Field | Frozen source expectation | Actual existing software / classification |
|---|---|---|
| Reported/qualified count | Repeated proposed total47; field-level source qualification permitted with tenure warning | L retains reported47 with source/scope-unverified qualification, not a numeric buyer/packet fact. Q represents source-qualified47 within residential component. **MATCH reported/Q; SAFE_QUALIFIED_DIFFERENCE L qualification**. |
| Denominator | Revised309residential dwellings; exclude school/carpark and old312 | Supplemental observation of unchanged builders: selected units309; profile total309. **MATCH** for transcribed residential basis; not an automated denominator-extraction test. |
| Reported percentage |15.2% | Retained in reported export columns; qualified percentage blank in Explore/report/profile/buyer/packet. Dashboard labels reported percentage, rounded15%. **MATCH reported with display rounding; SAFE_QUALIFIED_DIFFERENCE qualified**. |
| Derived percentage |47/309≈15.2104%, rounded15.2; proposed only | Current qualified-read contract does not publish a trusted derived percentage from legacy inputs. **SAFE_UNKNOWN**; source arithmetic remains in frozen evidence. It is not certified derived-percentage functionality. |
| Tenure/mix | Social rent12; shared ownershipCONFLICTING25vs35; bedroom breakdown inconsistent | L retains both alternatives and CONFLICTING wording in reported tenure/export/explanation. Q tenure helper preserves conflict, with no qualified shared-ownership count. **MATCH preservation**, not automatic detection. |
| Scope | Residential component of hybrid; no donation to school or phases | L explicitly scope-unconfirmed; Q component KPI=N/A and whole-scheme maximum47=investigate. **SAFE_QUALIFIED_DIFFERENCE L; MATCH Q**. |
| Status/legal | Committee resolution subject toS106/conditions; executed obligationUNKNOWN | Manually transcribed as pending/under-consideration, with exact committee qualification in notes; operative legal terms unverified. **SAFE_QUALIFIED_DIFFERENCE**: conservative pending representation does not assert issued permission. |
| Funding/viability | UNKNOWN | No invented terms. **MATCH**. |
| On/offsite/contributions | OnsiteAH; separate education/sports/highways/carpark payments | OnsiteAH retained in supplied reported notes; no other payment converted into AH units/percentage. **MATCH preservation**; no general legal/contribution parser claim. |
| Conflicts |25vs35 cannot be silently corrected | Both survive; no arithmetic repair or cherry-picking. **MATCH preservation**. |

### H3–H6, field-complete summary-limited controls

| Field | H3Oldham | H4Tameside | H5Wigan | H6Bury |
|---|---|---|---|---|
| ReportedAH / qualifiedAH | UNKNOWN / UNKNOWN: **MATCH** | UNKNOWN / UNKNOWN: **MATCH** | UNKNOWN / UNKNOWN: **MATCH** | UNKNOWN / UNKNOWN: **MATCH** |
| Denominator | Proposed2; selected/profile2: **MATCH** | RM1; selected/profile1: **MATCH** | Historical3; current withheld: **SAFE_QUALIFIED_DIFFERENCE** | Withdrawn40; current withheld: **SAFE_QUALIFIED_DIFFERENCE** |
| Reported% / derived% | UNKNOWN/UNKNOWN: **MATCH** | UNKNOWN/UNKNOWN: **MATCH** | UNKNOWN/UNKNOWN: **MATCH** | UNKNOWN/UNKNOWN: **MATCH** |
| Tenure/mix | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** |
| Scope | NoAHscope assertion: **SAFE_UNKNOWN** | NoAH/parent donation: **SAFE_UNKNOWN** | NoAHscope assertion: **SAFE_UNKNOWN** | NoAHscope assertion: **SAFE_UNKNOWN** |
| Proposed/agreed/secured | NoAHstage established: **MATCH UNKNOWN** | Permission is not AHsecured: **MATCH UNKNOWN** | NoAHstage asserted: **MATCH UNKNOWN** | NoAHstage asserted: **MATCH UNKNOWN** |
| S106/legal / funding/viability | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** |
| On/offsite/contribution | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** | UNKNOWN: **MATCH** |
| Conflicts | Not established: **MATCH UNKNOWN** | Not established: **MATCH UNKNOWN** | Not established: **MATCH UNKNOWN** | RawstatusUnknown/withdrawal retained; noAHfact inferred: **MATCH UNKNOWN** |

No UNSUPPORTED_ASSERTION, SCOPE_ERROR, NUMERIC_ERROR, TENURE_ERROR, LEGAL_QUALIFICATION_ERROR or CONSUMER_PARITY_ERROR was demonstrated by these comparisons. This is bounded evidence, not proof no such defect exists anywhere.

## Q. Consumer parity

| Consumer | Direct holdout evidence | Result and qualification |
|---|---|---|
| Explore/search | Scope resolver + AHAssessment.search/columns + inspected `app/ui/pages/0_Explore.py` row wiring | Unqualified counts cannot pass minimum1 or maximum0; qualified percentage withheld; reported columns retain available facts. Six case checks; full browser not run for each case. |
| Site profile / Residential Mix | `build_residential_mix`, KPI and tenure helpers; inspected evidence renderer wiring | Legacy counts remain reported/unverified; qualified point withheld; unknown never zero. Rochdale conflict remains in reported evidence/tenure, not forced into compact headline. |
| Dashboard | `_scheme_card` six cases; inspected `app/ui/shell.py` reported/unverified badge labels | Rochdale47 only reported/unverified; other current countsNone. Reported percentage uses integer display rounding. Does not independently render each holdout card. |
| Feed / buyer evaluation | Actual `_attach_planning_delivery_matching_facts` and operative buyer facts | All unqualified point countsNone; no promotion from known source text without accepted claim provenance. Existing direct qualified/phase/sibling regressions supply complementary protection. |
| Agent packet | Actual packet builder six cases | Count/percentageUNKNOWN for unqualified data. No assertion of qualified-source propagation or current production contents. |
| Exports/reports | Same `.columns()` as actual Explore and report-row code; source-code wiring inspected | Reported fields retain context; qualified count/percentage blank. Q explicit tenure claims serialize conflict. Hosted existing walkthrough separately tests renderedCSV; it is not a six-case holdout browser run. |
| Explanations | `format_affordable_housing_lines` + inspected `scheme_summary` guard instructions | Bolton historical/refused; Rochdale explicit conflict and legal qualification. No model-generated explanation executed; Specification028 output not independently exercised case-by-case beyond common packet/facts dependencies. |
| Allocation profiles | Legitimate linked residential-mix path only | No allocation-specific new case; shared helper/regression support only. No requirement to invent AH where allocation consumer lacks it. |

SAFE_UNKNOWN here is deliberate contract containment. The product's qualified-read surface cannot accept numbers from an unlinked legacy row as if it possessed source/qualifier/scope provenance. This work must not be represented as proving automated source reading, conflict discovery, import, or population. Those are not silently supplied by these tests.

## R. Original ten

Unchanged PR58 dispositions: Cross Lane, Woodford Garden Village Extension, ViaduxPhase2, StretfordMall, Hazelhurst, Lacy, Brixham, WorldPets and Brotherton remain **BLOCKED HISTORICAL REGRESSION CASES**. Focus School retains proposed **CLOSED_WITH_EXPLICIT_LIMITATION**. None is relabelled passed or replaced by a holdout identity. Product Owner must decide whether this holdout plus existing safeguards is sufficient to accept the historical evidence limitations. No nine-source recovery programme was undertaken.

## S–T. Tests and hosted CI

SOURCE VALIDATION: six council-backed identities; two complete committee reports, one committee minute/agenda item, five application summaries. Independent source review plus visual confirmation of the substantive Rochdale conflict. These source observations prove what the reviewed records say, not software behaviour.

OFFLINE SOFTWARE TESTS: first holdout run **9passed**, no failing assertion, no runtime change, no post-result assertion tuning. Focused AH selection **146passed +10subtests**,0failures. Source hash guard included. Existing selections: count thresholds, KPI/classification/tenure presentation, AH scope consumers, wholly-affordable state, trusted-consumer alignment, affordable-housing scope. Supplemental denominator observation reran the same9unchanged assertions successfully; it only adds output fields. Existing network-denial spawn runner, in-memorySQLite and no production credentials/access.

HOSTED CI: normal `AH web-only acceptance` is required on exact final candidate; final result/run identity is provided in handoff after publication. This document itself does not predeclare a result. `verification/web_ah/check.sh` adds the9holdout tests to the existing selection; no skip/xfail/deselection/weakening. Existing renderedCSV walkthrough remains part of hosted gate. Native-postgres/security-artifact rehearsal is neither repaired nor activated by this work.

## U. Source-validation qualification

This is independent of existing AH rule-design fixtures, but the four summary-only controls cannot establish what unavailable supporting documents might say. No current real-world delivery, S106 execution, funding availability or completeness is inferred. Rochdale's inconsistent document wording is not adjudicated. Bolton's favourable report is not preferred over its later refusal. No source fact is treated as installed PropertyAIgent data. Full transient source bytes are not claimed to be durable Git artifacts; minimal reviewed facts/anchors/hashes are. Current production state UNKNOWN; no production queries occurred.

## V. Independent review

`/root/ah_case_audit` independently reviewed both complex sources before any runtime comparison: confirmed Bolton's bound/conditionaltenure and Rochdale's47total/25vs35conflict. `/root/ah_review` independently reviewed frozen expectations, tests and first-run output; found no demonstrated runtime defect and considered limitedGO defensible conditional on regressions/hostedCI/REVIEW, while requiring all six limitations below. This is independent agent review, not a human REVIEW acceptance or merge authority.

## W–Y. Recommendation, limitations and next decision

**GO — bounded unseen validation passed locally; closure recommendation conditional on exact-candidate hostedCI and explicit Product Owner acceptance of limitations.** Stage3 remains OPEN until REVIEW/PO exit decision.

Material limitations:

1. Two substantiveAH cases plus four narrow UNKNOWN controls, not broad statistical validation.
2. Human source interpretation/transcription; no automated extraction/conflict detection/legal interpretation claim.
3. Six legacy-input consumer paths; richer qualified claims only contract/KPI/tenure/export helpers. No uninstalled reader/importer is assumed.
4. Shared builders/export dictionaries tested; full per-case rendered UI/download not tested. Existing hosted walkthrough is separate evidence.
5. No unseen competing sibling/phase pair; direct accepted regressions supply that protection, not the new cohort.
6. Full per-field matrix combines observed builders with deliberately unexposed/UNKNOWN fields; tests do not mechanically assert every source fact.
7. Nine original historical regressions remain blocked. Security artifact`5f1c41027ee1052c131faaeac83d9e04b3a8cf2d` remains **BLOCKED/DEFERRED, NOT PRODUCTION-INSTALLED**; failed prior rehearsal not closed by this candidate.

Exact next decision requested: REVIEW the exact remotely durable candidate and green hosted run; Product Owner decide whether this bounded successful holdout, existing regressions and explicit limitations are sufficient to close Stage3 while retaining the nine historical blocked cases honestly. If accepted, grant Stage3 exit and separately specify merge authority. No new AH infrastructure is required to make this acceptance pass. If this evidence level is rejected, identify the specific acceptance limitation to resolve; do not infer an AH implementation programme.

Stage4 planning freshness remains the next core reliability concern after the appropriate Stage3 exit decision: known-reference refresh and new-application discovery, including ten-council operational scope. It was not begun or validated by this six-council AH sample.

## Z. Actions deliberately not taken

No AH runtime correction/tuning, production access/write, new source-discovery engineering, council-wide enumeration, scraper, account creation, council contact, bulk acquisition, schema/migration/importer/reader/RLS repair, security-artifact installation, new model calls, ranking changes, deployment, merge, monitoring activation or Stage4implementation. No historical case was passed by substitution. No future holdout was fabricated to erase a failure.
