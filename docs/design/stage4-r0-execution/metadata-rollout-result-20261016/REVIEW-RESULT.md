# Finite metadata qualification and conditional rollout — consolidated result

Stage 4 OPEN. Salford qualification NO-GO; global stop preserved. Rochdale and all 11 rollout observations NOT EXECUTED. No retry, replacement, detail/document/model/database/parent calls, scheduling, deployment or stage advancement. This is listing-metadata recovery, not commercial qualification or database catch-up.

## Binding and implementation

Accepted predecessor evidence:6ed051d6d8e70855ecee58bfa2cc2b2d5e1e3ff0. Its originalManchester 14, artifact, citations and provenance are preserved unchanged; completed1–3October window excluded from all 13 successor partitions.

- PR 112, final reviewed head:f42238641e96280d35e2705ff95acc6cc55395ec.
- Integration/runtime revision:f5a5d92c42c6708c24c9f6c6cf10d6310b1bbedf; parents a32e2d1a0cd532ab3b209530ce76f1e5de4695c2 and f42238641e96280d35e2705ff95acc6cc55395ec.
- Reviewed/integrated tree:5b35da2516f1a97490bc044ff504c0d64f6bb7d9; clean execution checkout verified.
- Workflow:.github/workflows/stage4-metadata-rollout-once.yml; blob8dfae81a9bfa499d5ca4012849221b07d07b75f6; SHA2566d87bfd048a28e0866d192008c2e60c5c50a5e8330b73e217a192c833176845b.
- Manifest blob9da6736e075ce9f54c94474b6c8c12c7d6e7b4bc; SHA256db867ad45e1425c603edd9729efe1127f2eb6a38998baf0cbdcf8631b79bd5d1.
- Authority AUTHORISE_METADATA_13_SEQUENTIAL_20261016_ONCE is consumed. Only run1/attempt1 admitted; no rerun/resume. Remaining jobs cannot be bypassed through another workflow.
-170 targeted offline checks pass; independent review PASS exacttree. Final-head hosted13PASS plus intentional live-probe skip; postmerge6PASS. Initialhead e60f2cea637971b7d0a618ddb8c6d576d4e6ac36 had14 stale registry/date assertions fail (682pass); tests were corrected before integration, without runtime change. History is preserved.
-13 fixed nonoverlapping windows cover401 retained identities: qualificationSalford 8–14October12; qualificationRochdale 17–23September13; Manchester 17–19Sep27,20–23Sep46,24–26Sep25,27–30Sep44,4–7Oct53,8–14Oct43; Salford 17–23Sep39,24–30Sep37,1–7Oct29; Rochdale 24–30Sep15,1–7Oct18. Counts contextual, never forced source results.
- One workflow with13 dependent jobs, no resource stacking/borrowing. Each setup260 + active60 + cleanup160 =480s; finite combined allocation6240s.13× per-observation caps bound aggregate13obs/1040requests/260MiB/585worker seconds/780outer seconds/26MiB exported audit. All successors require verifiedGO and prior job success, including upload.

## Execution and retained failure

Run 38884069913, number1, attempt1, created2026-10-16T09:58:09Z. Sole executed job scope_00 /116917461431 ran09:58:13–09:59:22Z (69s). Source observation09:59:13.929315–09:59:17.992467Z. Source destination exactly the frozen ordinarySalford public listing URL, requested VALIDATED2026-10-08–2026-10-14.

Retained checkpoint reports failureLISTING_NOT_QUALIFIED, listing_stageCRITERIA, listing_failureTargetClosedError, applied_intervalnull, no listing segments or qualified rows. Safety eventLISTING_NOT_QUALIFIED correctly causes GLOBAL_STOP_NO_SUCCESSOR. The cause of the target closure is UNKNOWN from retained evidence; neither selector failure, source outage, bot block nor resource exhaustion is established. No additional live diagnosis was attempted.

Enumeration FAILED, usable proposals0, no screening dispositions or citation results from this observation. This is not an explicit-zero source result. Optional fields were not assessed, so no claim that description/address/type/date fields are absent. Truncation/ambiguity for the unobservedSalford rows is UNASSESSED. Its historical_only12 list in the original result is context set subtraction after a failed enumeration; it is not evidence of current absence, deletion or changed identities. Original result is preserved verbatim.

All12 successors are recorded skipped by GitHub: Rochdale qualification was NOT EXECUTED, and no rollout window ran. Source00 is exhausted; no replacement/retry. The authority as a whole is consumed and globally stopped.

## Artifact and checkpoint integrity

Artifact 12038766451, name metadata-scope-00-f5a5d92c42c6708c24c9f6c6cf10d6310b1bbedf-38884069913. OriginalZIP3071bytes, verified SHA2565f57cc450619db261f009df903690cb7d83e1eade016db1a879c9a9daea955d3 matchesGitHub digest and joblog. Archived before hosted expiry.

- checkpoints/000.json: a2345cf136fc92abf13bb55772f5c14a7a299b7f2b9cb0b89fe6037ccdb8a10e (4298bytes).
- execution.json:4c639be248c1231ec7d649e6d487c8af20d07808280dc6aa34f8955a4cf97951.
- result.json:bd3f2bc2976c190e457c7f5270b75f7ed5a2763a1d5098bcce132a19d3a44531.

Exact execution metadata, manifest/run/revision/scope binding, allowed paths, aggregate byte bound and checkpoint digest pass readback. Original worker audit is6111bytes total; source checkpoint4298bytes. The frozen manifest/workflow, execution screenshot, joblog and API readbacks are also archived; they are publication evidence outside the worker export allocation. SHA256SUMS covers publication files.

PreservedManchester run38880753411, number1/attempt1; artifact12037845540, ZIP SHA2561b16636771c623345b12676d008c39ba0a2b76db6d42cc21f172b203eee562f6; checkpointb486cea799886fd4317e18241a4ea6615969a27012b7de3af98be9ab395b2210; resultab29ee32e0e3da1a7786f87bf3a62fb2d8ac691d70b488cf89f93062df67bf2e. Original archive remains inherited from accepted predecessor; no new observation.

## Actual resources and cleanup

Sole observation:20requests; decoded10,845,097bytes; encoded2,650,524bytes; outbound5130bytes. Accounted max(decoded,encoded)+outbound=10,850,227bytes. Two ordinaryUI POSTs, one navigation/page; no qualified result pagination. Worker2.844s; source supervisor3.624s; outer4.375s. Source peakRSS809,578,496bytes; aggregate owned peak881,168,384bytes. Eight owned processes observed; zero survivors. BrowserCONTEXT_BROWSER_CLOSED, source processCLOSED, outerCLOSED; no supervisor limit hit, no expired outer deadline, accounting_complete true. Disposable hostedVM remains final containment. Job69s within480s; setup approximately58s before source admission, cleanup/upload completed within remaining allocation. No subsequent resources spent on skipped observations.

##415 coverage and screening review

| Council | Original cohort | Usable captured proposals | Remaining |
|---|---:|---:|---:|
| Manchester |252|14|238|
| Salford |117|0|117|
| Rochdale |46|0|46|
| Total |415|14|401|

Manchester 14 accepted proposals/address/type/validated dates present; received dates14UNKNOWN; no truncation or ambiguity; historical/current identity match was accepted. There are no newly observed changed identities from this failed successor. Current source differences forSalford/Rochdale/rollout remain unassessed.

Original screening remains5RELATED_APPLICATION_FOLLOW_THROUGH and9INSUFFICIENT_EVIDENCE,0 affirmative processing priorities and0 accepted deeper-processing exclusions. All14 identities retained. Detailed14-row proposal/type table and grouped positive/negative/related examples are in OFFLINE-SCREENING-REVIEW.md. The nineIE outcomes are not missing proposal capture: the wrapper deliberately preserves many legacyIgnore results; minor-work vocabulary/type gaps and misleading categories require separate treatment from policy changes.

Advisory recommendations only: six reversible shallow exclusions (cash-and-carry ancillary works, greenhouses/wall, trees, dormer, householderEV, householder rear extension); two strategy holds (existing7-bedHMO, C4→C2children's home); one limited-context pitched-roof hold. Generic erection and houses substring inGreenhouses are category defects without positive commercial promotion. BNG discharge vocabulary misses a condition category but preserved citation correctly protects its RELATED disposition. No new thresholds/rules have been applied. No deeper retrieval is purchased because a rule returnedIE.

Five preserved literal leads:144426/FO/2025;144656/FO/2025;144669/FO/2025;140916/FO/2024;PLA-2026-000439. Full wording/offsets/source fields/URLs/checkpoint provenance preserved in citation-leads.json. Exact literal matching against947 retained primary/comparison identity union produces no matches. This is not DB absence. Target councilUNKNOWN; no verified relationship/site/phase/progress/opportunity. A minor child can retain its lead without full extraction. No parent retrieval.

## Remaining coverage and next REVIEW

Priority1: accept the truthfulNO-GO/global-stop disposition and decide whether any finite continuation may be proposed. There is no authorised automatic recovery, identical replay or separate-workflow bypass. RetainedTargetClosedError evidence does not establish a repair. Rochdale remains unqualified and401 metadata identities remain open.

Priority2: one grouped offline product decision: approve/decline the six reversible minor-work exclusions; separately hold/define specialist existing-stock strategy and roof-only policy. Preserve citations/identities and no generic-count→dwelling inference. No live allowance is needed for this decision.

Priority3: separate held sourcecoverage gaps remain Bury 8–14OctUNKNOWN, Oldham 8–14OctFAILED, Rochdale 8–14OctFAILED, Tameside 1–7OctFAILED;15October bridgeBolton total/terminal proof blocked, Oldham sort proof blocked, Salford/Rochdale/Stockport/Tameside/Wigan held. Bury 15October complete andManchester 15October bounded explicit-zero remain preserved. Independent-only Rochdale 8/Tameside 16 identities retained; original independent seal unchanged. No silent reduced-coverage acceptance.

PreserveBolton production1504–1506; Oldham 1507–1508 committed pending identities, FACTS_WITHHELD, INITIAL_FACTS_VERIFIED0 and UNCERTAIN_COMMIT_OR_READBACK0. The priorBolton01859/26,01860/26,01861/26 comparison remains snapshot absences only at2026-10-16 08:05:15.526766+00:00; consumed944 comparison unchanged. No factual recapture or DB query occurred here. Parents,Stockport factual expansion,Trafford remain held/out-of-scope.

Earlier shared evidence maintenance duringStages 5–8 is agreed in principle;Stage 9 gates recurring buyer-specific acquisition interpretation, not all shared ingestion. Operational acceptance still requires cadence/resource ceilings, multi-day pagination, late-publication/overlap cost evidence, checkpoints, explicit per-source gaps, durable separate historical/ongoing ledgers, dedup/safe failure, alerts/pause/recovery and bounded prospective acceptance. Factual refresh requires its own existing accepted council contracts. No autonomous promotion/ranking/new semantics. No scheduling/prospective test is authorised. Subsequent interval starts16October2026 (open local day at this handoff; first closed-day cut16October23:00UTC/17October00:00BST); a fixed15October bridge is not ongoing catch-up. No watermarks moved.

Stage 4 and database catch-up remain incomplete pending REVIEW acceptance. No additional live allowance requested or used in this handoff.
