# TO REVIEW — UNIFIED SUSPENSION CATCH-UP AND PROSPECTIVE ACCEPTANCE PREPARATION

Stage4 OPEN. Offline working candidate and revised plan only. NO live authority, final freeze, workflow registration/dispatch, production read/write or source research. Supersedes planning assumptions in readiness7993196, not accepted evidence or historical results.

## 1. Accepted baseline and coverage ledger

Base master db8779467017d3973c00dc6b34eefba3e94a767e/tree1fb47fa901c59c94ecfbbedca9f495cf5698015d. Known-reference sub-gate accepted with explicit118-record retained cohort:52FULL/18STATUS_ONLY/4FIELD_LEVEL,44residuals. This updates known records; it is not new-application catch-up. Three committee-triggered identities1501/1502/1503 accepted from run38712922112, with2COUPLED/1INITIAL_STATUS_ONLY, discovery_pending/siteNULL/unknown roles, no automatic sites/opportunities. Their creation is not broad council catch-up. Initial population is not proven source change. Consumed workflow/manifests remain unchanged.

| Council | Retained historical source qualification,28Sep–4Oct | 29Sep–4Oct discovery evidence |5Oct through proposed cut |Actual new-application catch-up|
|---|---:|---|---|---|
|Bolton|22references/3segments,RECEIVED|PARTIAL: source enumeration, not DB-new reconciliation|UNCOVERED by retained primary enumeration|UNPROVEN|
|Bury|18/2,RECEIVED|PARTIAL|UNCOVERED|UNPROVEN|
|Manchester|57/6,VALIDATED|PARTIAL|UNCOVERED;2exact committee admissions do not fill interval|UNPROVEN beyond2fixed identities|
|Oldham|14/2,RECEIVED|PARTIAL|UNCOVERED|UNPROVEN|
|Rochdale|12/2,VALIDATED|PARTIAL|UNCOVERED|UNPROVEN|
|Salford|26/3,VALIDATED|PARTIAL|UNCOVERED|UNPROVEN|
|Stockport|49/5,VALIDATED|PARTIAL; accepted primary source shape|UNCOVERED|UNPROVEN|
|Tameside|15/2,RECEIVED|PARTIAL|UNCOVERED;1exact committee admission does not fill interval|UNPROVEN beyond1fixed identity|
|Wigan|17/2,RECEIVED|PARTIAL|UNCOVERED|UNPROVEN|

None has fully evidenced suspension-to-cut NEW-application coverage. Counts above describe the original entire28Sep–4Oct window, not a freshly measured29Sep subset. No future publication is described as already assessed. Committee assessment is finite observed evidence, not complete public-availability coverage. Stockport supplemental limitation and Trafford deferral preserved; no source work reopened. Machine-readable council/date ledger: coverage-matrix.json.

## 2. Unified timeline and catch-up scope

Drop the unnecessary first-Monday rule. No retained evidence establishes a universal council publication week. Proposed shared audit week:7consecutive Europe/London calendar days starting at cut C, irrespective of weekday; source-native date semantics stay separate. If a qualified official publication cycle is later established, record it without secretly moving already observed windows.

C is00:00Europe/London on the first local date after the final reviewed candidate/method freeze. Before source observations, record exact C and offset. Catch-up eligible interval[29Sep2026,C). W1[C,C+7calendar days);W2[C+7,C+14). Later correction audit atC+21. Half-open calendar intervals account for BST/GMT changes. No temporal gap exists at C; source filters use inclusive dates ending C-date minus1day. A call occurring after C still records actual observation time; it does not pretend catch-up occurred earlier.

Illustration ONLY, not frozen: if preparation/freeze allowed C=16Oct00:00BST, catch-up[29Sep,16Oct), W1[16Oct,23Oct), W2[23Oct,30Oct), audit6Nov. If freeze is later, the same predeclared next-midnight rule applies before observation; no idle Monday wait and no result-dependent date choice.

R0 catch-up: trailing28calendar days ending C, with records before29Sep classified OVERLAP_CONTEXT, not catch-up successes. R1/R2 at W1/W2close: trailing28days ending at that cut. R3 atC+21: trailing28days, comparing late additions/corrections with sealed earlier outputs. This is one finite four-round programme, not separate overlapping canaries. Four contiguous7day child windows per council/round; max36children. Deduplicate exact council/reference across children/rounds. Keep original first detection and later recovery timestamps.

If C moves so29Sep is more than28days earlier, one R0 cannot cover the suspension. Do not silently truncate it: request an explicit extra older catch-up round of up to28days, with exact partition and aggregate resource approval. Current working example covers the entire suspension. Cap exhaustion stops incomplete; smaller partitions require an amended finite manifest, not an unlimited split/retry loop.

Discovery catch-up means detecting/reconciling candidate identities. This proposed programme is credential-free and does not authorise production creation. Current full DB identity baseline and any eventual candidate admission require their own explicit minimal read-only snapshot/ingestion authority. Accepted shared writer is reusable, not permission for arbitrary bulk writes. All records lacking reliable materiality stay potential candidates. Complete field population,10units or known site relationship are not entry requirements.

## 3. Offline caller implemented

verification/discovery/finite_acceptance.py builds a canonical nine-council manifest from bounded dates/purpose, four7day children maximum per council and fixed semantics. It checks the expected manifest hash and rejects DB/model credential context before reader invocation. No workflow or round CLI is registered; private Idox child entry only. No new persistence path.

Idox uses existing WindowConfig/live through the existing50second process supervisor with a minimal credential-free environment and512000byte output cap. Arcus uses existing instrumented supervised browser worker, same source controls, with an optional date-window context. UIConfig dated_config changes only the two already-qualified valid-date filter values in the ordinary public URL; date echo and row checks use that context. Original historical configurations and all source-specific field/identity/budget rules retain their defaults. No synthetic RPC, new host, generic URL input, detail/document traversal or source-rule expansion.

Arcus audit validation can accept an explicit dated configuration while its default historical behaviour remains unchanged. The finite caller reports enumeration_completeness=COMPLETE only for reconciled count/criteria/identity/resource evidence, while coverage completeness remains UNKNOWN and source_contract_qualified=false. An explicitly reviewed new-window source-contract qualification is still required before a future registered caller can claim coverage COMPLETE; raw historical UNKNOWN audits are not rewritten. Idox explicit zero requires actual qualified zero evidence. Partial page/cap/criteria failure, exception, missing resource accounting and unknown termination cannot become COMPLETE. Failure stops the finite round and records untouched children. No watermark is advanced even on COMPLETE; this caller is acceptance evidence only.

The caller is offline-tested and callable, NOT a final execution registration: exact SHA/run/authority/manifest admission and hard outer1900second wrapper must still be registered/reviewed before live calls. It does not certify an independent denominator or broad publication recall.

## 4. Concrete budgets and finite call accounting

Per normal round: <=36children, concurrency1, <=1200requests, <=323658240accounted source bytes,1900seconds outer hard-deadline requirement,20MB aggregate JSON output. This is a conservative ceiling:24Idox children x10requests/3MB plus12Arcus children x80requests/20MiB. Caller reserves each next child's maximum cost before invoking it and stops on absent/invalid accounting. Per-child source audit caps remain unchanged: Idox512000bytes; Arcus65536bytes.

Each Idox child:6pages,10requests,3MB total/500k response/45second source budget plus50second supervisor; Stockport2.5second request gap unchanged. Each Arcus child:6segments,80requests/20MiB combined inbound/outbound/45seconds/1GiB supervisor-owned RSS, bounded pages/navigation/cleanup. Existing per-family retry behaviour unchanged; caller introduces no retry. Accounting uses source-specific measured fields; does not invent encoded bytes for Idox. The1900second outer budget must be enforced by the future registered wrapper, not merely this Python clock check.

Four normal rounds maximum144children/4800requests/1294632960bytes/7600seconds cumulative ceiling, not a target. These are public-source traffic ceilings, not Supabase egress; this caller has no DB access. Independent manual enumeration traffic is separate and MUST NOT be hidden in these totals: proposed max6pages/segments per child,1ordinary navigation chain at a time, no document downloads/retries, with36child-window assessments per round and a separately reviewed finite browser budget before approval. An inability to finish independently under that bound means denominator INCOMPLETE, not unlimited owner labour or a false100percent. REVIEW should consider this ceiling against commercial value before approving all four rounds; actual observed qualification traffic was far below ceilings but is not a guarantee.

## 5. Independent denominator — assigned process, not Product Owner transcription

Owner does not transcribe portals. DEVELOPMENT assigns a separate assessor agent/session for Idox and a separate assessor for Arcus, using ordinary official browser pages and their own bounded extraction/transcription of visible reference/date/count/segment metadata. They must not import/call the primary parser, reuse its returned reference set or inspect its output until their denominator is sealed. A different session/assessor can inspect the same official portal: parser-independent, not source-independent. Pure reconciliation reuses discovery_acceptance.reconcile only AFTER the ledger is sealed.

Use independent-denominator-form.json for each council/window, recording assessor, timestamps, exact criteria, count continuity, segments/terminal/zero proof, unique explicit references, materiality and evidence fingerprints. Populate future reference rows during/after the actual week; blank forms are not future denominators. All9councils are assigned this method, with source semantics/routes in coverage-matrix.json. If the page cap prevents independent enumeration, return INCOMPLETE and predeclare a smaller bounded date partition before comparison. Manual corrections after sealing append a versioned correction ledger; never overwrite the original denominator.

A source-only identity with sparse metadata remains POTENTIALLY_MATERIAL/INSUFFICIENT_METADATA. Separate confirmed/potential denominators. Confident exclusions require explicit reason/evidence/rule version; unknown scale/relationship never silently excluded. Source count of all records and commercial eligibility denominator remain distinct. Already-known identities remain visible in accounting. Identity withholding is WITHHELD_AFTER_DETECTION, not an unexplained miss and not successful admission.

## 6. Publication gap — retained inventory and exact unresolved questions

No qualified independent publication-availability feed is established. Inventory is retained evidence only:
- Bury: ordinary Weekly/Monthly Lists control was inspected; offered VALIDATED/DECIDED weeks, not a separate published/received list. Its publication semantics/completeness were NOT qualified.
- Manchester: official guidance described weekly/monthly viewing; no separate complete availability feed established.
- Bolton/Oldham/Stockport/Tameside/Wigan: existing Idox date-search mechanisms qualified. No retained qualified publication list/feed/first-publication timestamp contract found in the inspected source code/evidence.
- Rochdale/Salford: Arcus validated-date listings qualified; no separate availability ordering/feed qualified.
- Committee evidence: useful secondary challenge, but incomplete and not a complete availability denominator; Stockport limitation stays accepted. No committee/archive investigation proposed.

Same-portal source-date matching cannot establish publication recall. A newly published application whose received/validated date is older than28days can be missed by both primary and independent searches. Retain observed out-of-overlap applications as PUBLICATION_COVERAGE_CHALLENGE, not OUTSIDE_INTERVAL solely to avoid a miss. No blanket limitation is accepted by this pack.

Small live qualification is required before claiming that blind spot solved. Proposed scope for separate approval: ONE ordinary official Bury Weekly/Monthly Lists surface and ONE Manchester weekly/monthly/public-listing surface; inspect visible date labels, list ordering, retained criteria/count/terminal semantics and whether a publication/first-public-availability date actually exists. At most one selected recent list week, two pages/segments and three exact listed-reference cross-checks per family, sequential, no documents/database/production/model use, no new infrastructure or access-control workaround. Do not rerun the historical qualification windows. Exact question: does either surface enumerate NEWLY PUBLIC records independently of old received/validated dates, or merely repackage those same dates? Positive family evidence must not automatically be extended to every council; at most one equivalent label/shape confirmation per remaining council would need explicit subsequent bounded scope. Stop after the two representative surfaces if neither supplies an independent availability signal.

If a valid official availability surface exists, propose its bounded complementary integration/configuration for review; do not implement it silently. If not, return the concrete remaining public-availability coverage gap for Product Owner decision. Broader all-history enumeration is disproportionate and not proposed. Existing committee-triggered discoveries may challenge the gap but cannot certify its absence.

Latency: official timestamp or independently observed absence/presence bounds only. No received/validated substitution. Report measured <=7calendar-day cases, breached cases and UNKNOWN separately. First-seen alone is not an exact publication time. Out-of-overlap/backfills remain explicit even if later recovered. No retrospective insertion into the original primary result.

## 7. Acceptance and stopping conditions

Freeze code/method/config/rules/manifest/calendar BEFORE observations. Current hashes in candidate-proposal.json are review working identities, NOT a final freeze. Future references cannot be frozen in advance. Proposed earliest next-midnight weeks replace first-Monday only after REVIEW approval; exact C must be committed before any source observation.

Each source child/parent retains separate enumeration and coverage states; candidate count completion alone leaves coverage UNKNOWN. States are COMPLETE/INCOMPLETE/FAILED/UNKNOWN with original audit, applied/requested interval, date semantics, segment/count/resource/cleanup evidence. No completed-through advance for noncomplete; no watermark advancement by this acceptance caller. Independent denominator completeness is separate. Recall UNKNOWN on incomplete denominator; zero eligible denominator N/A, not100percent. Require zero unexplained confirmed/potential material misses, with original miss/recovery histories intact. Admission success and factual verification are separate and outside this live-source proposal's persistence scope.

Preserve original28Sep–4Oct comparison unchanged. Catch-up recovery is not original detection success. Historical committee interval[14Jul,14Oct) unchanged. No new source availability claim from committee snapshot absence. No closure of Stage4 without REVIEW.

Stop on source/identity/security/cleanup/resource failure or uncertain persistence if later separately authorised, route/candidate drift, need for access circumvention/new infrastructure, systemic primary defect or unexplained material misses beyond current architecture. No blind retries, consumed workflow reruns, arbitrary references, secret changes, new writers, models, scheduling, Render deployment, Trafford, Stockport research or Stage5.

## 8. Precise next authority requested

A. Review this offline candidate/diff and unified timeline; approve any necessary corrections, not final code freeze yet.
B. Authorise ONLY the two bounded publication-surface qualifications above to resolve whether an independent availability challenge exists. This is a source-contract question, not another committee programme or production canary.
C. Then review the exact executable candidate, complementary-route finding, council/date manifests and primary/independent aggregate budgets; authorise finite R0/R1/R2/R3 source observation and independent assessment only after final freeze and exact-head tests/review/CI. A current identity snapshot or any new production admission needs explicit scope; neither is silently included.

No live call has been made under A/B/C. No workflow registered or dispatched. Secure GitHub sign-in remains a small pending owner device-verification dependency; prior request timed out. It may be reinitiated under existing login authority when needed; no PAT, permission expansion or environment-protection change. This does not block offline preparation or invalidate the accepted production admission.

Preparation pack COMPLETE; live execution/final freeze NOT AUTHORISED and publication-availability coverage remains UNRESOLVED. Stage4 OPEN.

## Offline validation and independent review

Final affected network-denied suite:67passed (finite caller, exact audit-context binding, sparse/empty/cap/failure accounting, date substitution, existing Idox/Arcus readers and instrumented controls, pure acceptance reconciliation). Initial test run exposed only the fixture retaining synthetic DATABASE_URL; fixture correction removes that synthetic context after seccomp installation, production credential guard unchanged. Earlier65passed preceded two new context-regression tests; counts overlap, not additive. No hosted CI, live worker or disposable PostgreSQL call was needed for this nonpersistent caller slice; no DB code changed.

Independent review identified two concrete gaps, corrected before publication: wrong council/case/requested-window audit acceptance and count reconciliation being promoted to coverage. Tests now reject wrong contexts, and coverage remains UNKNOWN despite reconciled counts until reviewed qualification. Existing source rules/defaults preserved. Outer hard deadline/registration and publication coverage remain explicit prerequisites, not claimed complete. No new testing programme or deployment.
