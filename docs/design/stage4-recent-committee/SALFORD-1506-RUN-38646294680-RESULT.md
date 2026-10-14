# TO REVIEW — SALFORD PA/2025/1506 B2 ELIGIBILITY DIAGNOSTIC RESULT

**DIAGNOSTIC CONSUMED — EXACT-SOURCE QUALIFICATION STOP; EARLIER B2 INELIGIBILITY UNRESOLVED.** No rerun or production admission.

A. MASTER STAGE / CURRENT GATE / NEXT GATE: Stage4 bounded reliable pipeline; committee-discovered admission; REVIEW of exact Salford evidence eligibility. Stage4OPEN.

B. Baseline:38642693250run1attempt1,CONSUMED. Earlier exact source qualification succeeded but B2 eligibility was false. New diagnostic is separate and must not inherit those earlier identity/fact observations.

C. Audit defect:earlier rejected qualified observations lost their fields. PR85 corrected export before B2 eligibility. This new execution produced no qualified observation, so it did not exercise that previously missing B2-ineligible field audit.

D. Correction:whitelisted bounded states/literals/scope/eligibility/reason/provenance exported before eligibility checks. No acceptance/persistence semantic change.

E. Changed paths:sixPR85paths:rejection_audit.py,salford_diagnostic.py,committee_exact.py,test_discovery_rejection_audit.py,discovery-offline workflow,new salford-1506-diagnostic-once workflow.

F. Tests/CI:62focusedtestsPASS;sixhostedexact-headchecksPASS on65481a0e96fe733d049ca16379c46a0ed733368d. No tests rerun during analysis.

G. Independent review:approved observability-only fixed secret-free diagnostic before registration. This artifact does not prove evidence eligibility or authorize persistence.

H. Merge:25a21bf1ed5bb97d8c09b28fce234542884c1f59;tree3e82fdbfa309c0c92ed5976a88a0f2dddd505113;[skip render]. Exact executed SHA matches.

I. Workflow:.github/workflows/stage4-salford-1506-diagnostic-once.yml;blob0a51755b53f33a2b467e2fbf77638ff0ca56644a. Manual,single-use,master-bound. Authority nowCONSUMED. Run1attempt1. No attempt2/new invocation permitted.

J. Database:no secret references or production environment binding; env-i excludes database credential; diagnostic rejects database/Supabase credential names. Artifact records database_connections0,reads0,writes0,admission_attempts0. No production engine/admission path invoked. No independent production census performed.

K. Run38646294680;transportjob116133867897;failure. Source step22:15:54–22:16:07UTC;artifactupload succeeded. Exact exception salford_diagnostic.py line46: RuntimeError('diagnostic source boundary failed; no retry'). The job duration includes about50secondsdependency installation, not a71secondsource timeout.

L. Displayed reference:UNKNOWN/null. Only requested referencePA/2025/1506 retained.

M. Identity:NOT_QUALIFIED. transport_failureAMBIGUOUS_SOURCE_RESULT. Budget/cleanup passed, narrowing failure to shared exact-source/projection qualification rather than resource handling. The retained artifact cannot distinguish which guest identity/response guard or displayed-reference check failed. This is not proof of wrong-reference content, network outage or Salford-wide failure.

N. Extracted field states:UNAVAILABLE (empty map).

O. Supported literals:UNAVAILABLE (empty map).

P. Verification scope:UNKNOWN.

Q. B2 eligibility:false at the no-qualified-observation envelope. B2 evaluation was NOT_REACHED. Do not conflate this with earlier run's qualified-but-ineligible observation.

R. Rejection:AMBIGUOUS_SOURCE_RESULT at source qualification; downstream audit NO_QUALIFIED_OBSERVATION. Earlier exact B2 field rejection remainsUNKNOWN. Node.jsdeprecation warning was not causal: Pythonexception causedexit1;artifactupload succeeded afterwards.

S. Provenance:requested frozen manifestsha2568c8d6fb5de8997cf64bcfa95dd2d3c6c292d51dc1533f834e892728d372e25ad;executedSHA25a21bf;retrievalauditcompletion2026-10-14T22:16:07.526406UTC /23:16:07.526406BST. source_sha256null;no qualified factual response fingerprint retained.

T. Resource/cleanup:36requests,2redirects,0retries;1page,2navigations;11,801,783decodedbytes,3,139,679encodedbytes;worker11.362seconds,supervisor11.98seconds;peakownedRSS830,746,624bytes;8ownedprocessesseen,0liveowned survivors. BudgetWITHIN_LIMITS;cleanupCLOSED. Notimeout/limitincrease proposed.

U. Artifact11932951832,salford-1506-diagnostic-38646294680-25a21bf1ed5bb97d8c09b28fce234542884c1f59;ZIP820bytes,one result.json. SHA2569f87f5bb2d27f505b22932d3f8c8bcfb2af7604e49bb612e4671d4bde8892d18 independentlydownloaded+verifiedmatchesGitHubdigest. JSON retained asrun-38646294680-diagnostic.json. executionDIAGNOSTIC_STOP_NO_RETRY,model_calls0.

V. Privacy/security:no rawpayload/HTML,personal/contact information or credentials exported. Fail-closed identity preserved; no bypass or retry. No production transaction or uncertaincommit.

W. Existing semantics:withholding unqualified identity is correct under the existing contract. The correctness of the original qualified B2-ineligible result remainsundetermined because this diagnostic did not reach that stage.

X. Implementation defect:source guard rejected this response; artifact does not establish a parser defect, source defect or exact failed predicate. Prior observability correction cannot recover facts that never crossed the qualification boundary. No code corrected in this analysis.

Y. Product/evidence-contract change:no demonstrated need. Nothing here justifies relaxing identity or B2 evidence rules. Another execution would require new explicit authority and reviewed separate registration, not a consumed workflowrerun.

Z. Recommendation:keepSalfordwithheld from admission; preserve this exact-source stop. REVIEW may acceptthelimitation, authorise narrowly reason-coded existing source-guard diagnosis, or separatelyauthoriseManchester-onlyadmission. NeitherManchestereligibilitynoradmissionhasbeenlive-provenbythisrun. No new source investigation proposed automatically.

AA. Exact decision:choose whetherSalfordremainswithheld, whethera narrowlybounded further qualification diagnostic is justified, or whetherManchesterproceeds separately under fresh production authority. Do not rerun38646294680or38642693250. No evidence-contract change recommended.

AB. Manchester145583/FO/2026and143413/FO/2025preserved;zero requests/admissions in this task.

AC. Deliberatelynot taken:rerun/attempt2,productionaccess/write/admission/repair,B2change,eligibilityrelaxation,newsourceinvestigation,models,prospectivediscovery,scheduling,Stage5+,Stage4closure.
