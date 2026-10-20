# The 24 captured Bolton schemes (RECEIVED 28 September to 4 October 2026)

Status: **offline review, no production access, no council request.** Source: the archived worker audit `hosted-sealed-artifact/source/worker-result.json` (sha256 `b3d765e77df3602f732a2b37799745c7094ed3904e1cb56e7ea1c2e9b6ab6a67`) and the recorded run evidence. Window: 24 references over 3 pages, `COUNT_RECONCILED`.

## 1. What is recorded and what is not

| Item | Status |
|---|---|
| The 24 references, dates, proposal text and addresses | **Recorded** (archived audit and the durable capture `capture/source.json`, sha256 `5525be5a…`) |
| That every reference was screened | **Recorded**: five `BATCH_SCREENED` batch outcomes in the sealed hosted events (batches of 5,5,5,5,4 children) and the owner's database read (event 163: 5 of 5 batch items complete) |
| Aggregate screening outcome | **Recorded** (sealed hosted result): 1 `SUPPORTED_PROCESSING_PRIORITY`, 3 `RELATED_APPLICATION_FOLLOW_THROUGH`, 20 `INSUFFICIENT_EVIDENCE`; 24 proposal-usable; 3 citation leads |
| **Per-reference screening outcome, reasons and missing evidence** | **NOT available in the archived evidence.** Each reference's result is stored in its ledger child item (database), which this review did not read (no privileged observation was taken). The archive records only the aggregate and the child item keys |
| Which child item belongs to which reference | **Verified by recomputation (labelled LOCAL):** the 24 child keys recomputed from the archived records equal 24 of the 24 child keys recorded in the batch outcomes, so the reference-to-item mapping is evidenced. The receipt-level digest was *not* reproduced byte for byte (serialisation differences), only the per-record digests that the keys depend on |

## 2. LOCAL RECOMPUTATION (not recorded results)

Everything in the table below under "Local screening" is a **local recomputation** with the same pure function the run used (`app/ingestion/listing_screening.screen_row`, rule `manchester-listing-screen-assessment-v1`) over the archived, unchanged records. Consistency check against the recorded run: local aggregate **{'INSUFFICIENT_EVIDENCE': 20, 'RELATED_APPLICATION_FOLLOW_THROUGH': 3, 'SUPPORTED_PROCESSING_PRIORITY': 1}** equals the recorded aggregate **{'INSUFFICIENT_EVIDENCE': 20, 'RELATED_APPLICATION_FOLLOW_THROUGH': 3, 'SUPPORTED_PROCESSING_PRIORITY': 1}**; usable 24 = 24; citation leads 3 = 3. The recomputation is therefore consistent with the recorded aggregate, but it is **not** the recorded per-reference outcome and must not be cited as such.

| # | Reference | Received | Proposal (as listed) | Local screening (disposition) | Why (local) | Ledger child key (verified mapping) |
|---|---|---|---|---|---|---|
| 1 | 01797/26 | Fri 02 Oct 2026 | REMOVAL OF ROOF MOUNTED EXTRACT DUCTWORK AND INSTALLATION OF 1 NO. AIR HANDLING UNIT (AHU) TOGETHER WITH DUCTING AND ACOUSTIC FENCING | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore - under 10 units` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `b99019c0aed8…` |
| 2 | 01790/26 | Fri 02 Oct 2026 | INSTALLATION OF 1 NO. INTERNALLY ILLUMINATED REPLACEMENT HOARDING | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `c13dc2f71675…` |
| 3 | 01789/26 | Fri 02 Oct 2026 | ERECTION OF SINGLE STOREY FIRST FLOOR REAR EXTENSION TOGETHER WITH CONVERSION OF LOFT TO HABITABLE SPACE | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `a870ebe1fe82…` |
| 4 | 01787/26 | Fri 02 Oct 2026 | CERTIFICATE OF LAWFULNESS PROPOSED (S192) FOR CHANGE OF USE FROM DWELLING (C3) TO (C3b) RESIDENTIAL CARE FACILITY FOR 6 NO. YOUNG PERSONS | `INSUFFICIENT_EVIDENCE` | residential wording present but the existing unit filter does not qualify it (Ignore) | `fcf8e7c5445a…` |
| 5 | 01786/26 | Fri 02 Oct 2026 | NOTICE OF INTENTION TO FELL 1 NO. CYPRESS | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `76f17c9755b4…` |
| 6 | 01785/26 | Thu 01 Oct 2026 | CHANGE OF USE OF FIRST AND SECOND FLOORS TO CREATE 7NO. BEDROOM BED AND BREAKFAST TOGETHER WITH THE ERECTION OF 2NO. REAR DORMERS WITH THE ALTERATION OF FIRST FLOOR FENESTRATION TO FORM ACCESS AND EXTEND EXISTING TERRACE | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `d0bf44776213…` |
| 7 | 01784/26 | Thu 01 Oct 2026 | ERECTION OF FENCE AND ACCESS CONTROL GATES TO LEA FIELD WAY TOGETHER WITH CONSTRUCTION OF FOOTPATH FOR PUBLIC RIGHT OF WAY DIVERSION | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `12dfe6187c57…` |
| 8 | 01783/26 | Thu 01 Oct 2026 | PRIOR NOTIFICATION APPLICATION FOR A PROPOSED LARGER HOME EXTENSION AT REAR (6.00M LONG 4.00M MAX HEIGHT 3.00M EAVES HEIGHT) | `INSUFFICIENT_EVIDENCE` | residential wording present but the existing unit filter does not qualify it (Ignore) | `412b44e2dfee…` |
| 9 | 01782/26 | Thu 01 Oct 2026 | DEMOLITION OF UNIT H2 TO CREATE OPEN AIR STORAGE AREA, PARTIAL DEMOLITION AND ALTERATION OF UNIT H1 TO CREATE OFFICES AND TRAINING FACILITY TOGETHER WITH INSTALLATION OF BOUNDARY FENCING, TREE PLANTING, LANDSCAPING, DROP | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `589377d5b052…` |
| 10 | 01780/26 | Wed 30 Sep 2026 | ERECTION OF FIRST FLOOR EXTENSION AND CONVERSION OF GARAGE TO HABITABLE ROOM WITH RETENTION OF 1 NO. OUTBUILDING TOGETHER WITH ERECTION OF BASEMENT GARDEN ROOM | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `8619b9a4dd19…` |
| 11 | 01778/26 | Wed 30 Sep 2026 | NOTICE OF INTENTION TO :- PRUNING OF 2 NO. CHERRY, 1 NO. CYPRESS, 1 NO. WILLOW, 1 NO. STAGHORN | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `e142d0e01c52…` |
| 12 | 01777/26 | Wed 30 Sep 2026 | ERECTION OF SINGLE STOREY FRONT AND TWO STOREY REAR EXTENSION TOGETHER WITH CONVERSION OF GARAGE AND LOFT TO HABITABLE SPACE AND INSTALLATION OF NEW ROOF AND DORMERS TO REAR | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `01ff311f1dce…` |
| 13 | 01776/26 | Wed 30 Sep 2026 | EXTERNAL ALTERATIONS TO EXISTING BUILDING APPROVED UNDER PRIOR APPROVAL APPLICATION 00031/26 | `RELATED_APPLICATION_FOLLOW_THROUGH` | 1 reference-like citation(s) in the listing text -> related-application follow-through lead (unverified) | `b98c498bd962…` |
| 14 | 01775/26 | Wed 30 Sep 2026 | PART A - PRUNING OF 5 NO. SYCAMORE, 1 NO. NORWEGIAN MAPLE, 1 NO. MOUNTAIN ASH AND 1 NO. LIME PART B - FELL 3 NO ASH | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `unknown` ("primary_residential" means householder-type works, not a scheme) | `fedc083aae18…` |
| 15 | 01769/26 | Tue 29 Sep 2026 | NON-MATERIAL AMENDMENT TO APPLICATION 00284/26 TO AMEND FENESTRATION AND REMOVE DORMERS FROM PHASE 1E PLOT NOS. 151, 157, 164-165, 175-176, 177, 188, 192, 193, 198, 204 AND 205 AND PHASE 2 PLOT NOS. 7, 12, 13, 27, 31, 31 | `RELATED_APPLICATION_FOLLOW_THROUGH` | existing category `variation_or_amendment`; 1 reference-like citation(s) in the listing text -> related-application follow-through lead (unverified) | `674029f73967…` |
| 16 | 01768/26 | Tue 29 Sep 2026 | DEMOLITION OF 4 NO. BUILDINGS AND ERECTION OF 4 NO. APARTMENT BLOCKS COMPRISING OF NO. 49 SELF CONTAINED APARTMENTS (CLASS C3) TOGETHER WITH ACCESS, LANDSCAPING AND CAR PARKING | `SUPPORTED_PROCESSING_PRIORITY` | residential wording present and the existing unit filter qualifies it (Confirmed - 10+ units) | `59339be8756e…` |
| 17 | 01767/26 | Mon 28 Sep 2026 | DEMOLITION OF EXISTING GARAGE WITH ERECTION OF SINGLE STOREY SIDE EXTENSIONS | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `e850bac0b4da…` |
| 18 | 01766/26 | Mon 28 Sep 2026 | ERECTION OF A SINGLE STOREY MODULAR BUILDING FOR EXTERNAL DINING | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `75891ee46ea1…` |
| 19 | 01764/26 | Mon 28 Sep 2026 | CHANGE OF USE FROM DWELLING (CLASS C3) TO 5 NO. BEDROOM HMO (CLASS C4) FOR 5 OCCUPANTS TOGETHER WITH INSTALLATION OF REAR DORMER | `INSUFFICIENT_EVIDENCE` | residential wording present but the existing unit filter does not qualify it (Ignore) | `2ab30833c692…` |
| 20 | 01763/26 | Mon 28 Sep 2026 | DISCHARGE OF CONDITION 2 (FUMES AND NOISE) ON APPLICATION 00060/26 | `RELATED_APPLICATION_FOLLOW_THROUGH` | existing category `condition_discharge_or_details`; 1 reference-like citation(s) in the listing text -> related-application follow-through lead (unverified) | `0eb3e5b21a28…` |
| 21 | 01762/26 | Mon 28 Sep 2026 | PRIOR NOTIFICATION APPLICATION FOR A PROPOSED LARGER HOME EXTENSION AT REAR (5.00M LONG; 3.30M MAX HEIGHT; 2.35M EAVES HEIGHT) | `INSUFFICIENT_EVIDENCE` | residential wording present but the existing unit filter does not qualify it (Ignore) | `d484eee1dbfa…` |
| 22 | 01759/26 | Mon 28 Sep 2026 | CONVERSION OF GARAGE TO HABITABLE ROOM WITH ERECTION OF FIRST FLOOR SIDE EXTENSION | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `3460cf6323eb…` |
| 23 | 01758/26 | Mon 28 Sep 2026 | ERECTION OF FRONT PORCH, TWO STOREY FRONT, SIDE AND SINGLE STOREY REAR EXTENSION | `INSUFFICIENT_EVIDENCE` | no dwelling/housing keyword in the proposal text; existing filter classifies it `Ignore` / `primary_residential` ("primary_residential" means householder-type works, not a scheme) | `bbf7af1c551e…` |
| 24 | 01757/26 | Mon 28 Sep 2026 | ERECTION OF TWO STOREY RESIDENTIAL BUILDING COMPRISING 6 SELF CONTAINED FLATS | `INSUFFICIENT_EVIDENCE` | residential wording present but the existing unit filter does not qualify it (Ignore - under 10 units) | `f3fe53b1e0e3…` |

## 3. Addresses (as listed)

| # | Reference | Site address |
|---|---|---|
| 1 | 01797/26 | Farnworth Leisure Centre Brackley Street Bolton BL4 9DZ |
| 2 | 01790/26 | Land At Marsden Road Bolton BL1 2PF |
| 3 | 01789/26 | 3 Morrison Street Bolton BL3 3AN |
| 4 | 01787/26 | 44 Lower Leigh Road Bolton BL5 2EH |
| 5 | 01786/26 | Greenthorn Ladybridge Lane Bolton BL1 5DE |
| 6 | 01785/26 | Toro 69 Church Street Bolton BL6 6AA |
| 7 | 01784/26 | Unit A6b Lea Field Way Bolton BL5 1ED |
| 8 | 01783/26 | 18 Crescent Road Bolton BL4 8LF |
| 9 | 01782/26 | Unit H1 To H2 Europa Way Stoneclough Radcliffe Bolton Manchester M26 1GG |
| 10 | 01780/26 | 116 Beaumont Chase Bolton BL3 4XH |
| 11 | 01778/26 | Stoneyacre Foxholes Road Bolton BL6 6AL |
| 12 | 01777/26 | 15 Stapleton Avenue Bolton BL1 5ES |
| 13 | 01776/26 | Ormstons Farm Wingates Lane Bolton BL5 3LT |
| 14 | 01775/26 | 2 Clarendon Gardens Bolton BL7 9GX |
| 15 | 01769/26 | Horwich Golf Club Victoria Road Bolton BL6 5PH |
| 16 | 01768/26 | Land Between Bank Street And Queen Street Farnworth Bolton BL4 7PA |
| 17 | 01767/26 | 36 Catterall Crescent Bolton BL2 4AD |
| 18 | 01766/26 | Mount St Joseph Rc School Greenland Road Bolton BL4 0HT |
| 19 | 01764/26 | 134 Tonge Moor Road Bolton BL2 2DP |
| 20 | 01763/26 | 50 St Helens Road Bolton BL3 3NH |
| 21 | 01762/26 | 32 Clarendon Street Bolton BL3 6ST |
| 22 | 01759/26 | Braemar Salford Road Bolton BL5 1BW |
| 23 | 01758/26 | 62 Kilworth Drive Bolton BL6 4RL |
| 24 | 01757/26 | Land West Of Church Street Church Street Bolton BL5 3QR |

## 4. Citations and follow-through leads (local)

* #13 `01776/26` - `00031/26` in `proposal`: "EXTERNAL ALTERATIONS TO EXISTING BUILDING APPROVED UNDER PRIOR APPROVAL APPLICATION 00031/26" (relation: UNRESOLVED_CITATION; target council unknown; **unverified lead**)
* #15 `01769/26` - `00284/26` in `proposal`: "NON-MATERIAL AMENDMENT TO APPLICATION 00284/26 TO AMEND FENESTRATION AND REMOVE DORMERS FROM PHASE 1E PLOT NOS." (relation: EXPLICIT_WORDING_UNVERIFIED_LEAD; target council unknown; **unverified lead**)
* #20 `01763/26` - `00060/26` in `proposal`: "DISCHARGE OF CONDITION 2 (FUMES AND NOISE) ON APPLICATION 00060/26" (relation: EXPLICIT_WORDING_UNVERIFIED_LEAD; target council unknown; **unverified lead**)

## 5. Missing evidence common to every record (by construction of this stage)

The listing screening is deliberately shallow and source-free. For **all 24** records, the screening result itself states: `commercial_relevance = UNKNOWN`, `site_relationship = UNKNOWN`, `progress = UNKNOWN`, `residential_dwelling_count = null` (a raw generic unit count is shown only where the existing filter extracted one), `permanent_exclusion = false`. No detail page, document, decision notice, plan or consultation material was fetched, so unit numbers, tenure, affordable-housing content, applicant/agent, decision status and site identity are not established. The cited-reference leads, where present, carry no confirmed relationship.

Record fields captured per scheme: reference, proposal text, address, received date, validated date and application-type states (application type is not shown on the listing page).


## 6. Caveats

* All 24 are listing-level observations of one window (count 22 on 14 October, 24 here). They are not a statement about any other window, council or day.
* Dispositions here are screening triage labels, not planning judgements.
* Any statement about an individual scheme's *recorded* outcome requires reading the ledger child items; that read has not been made.
