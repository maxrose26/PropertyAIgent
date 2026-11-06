# Manchester worker correction and fixed period10 proposal

MASTER STAGE 4 OPEN. Current gate: verified Manchester collection through screened,
discoverable backlog. Next gate: REVIEW of connected live evidence. This handoff
does not authorise a live submission. Period09 is settled and consumed.

## Demonstrated defect and limits of the finding

Period09 remains bound to run bc4a50f3e4f44262a41a1b4036c3392b and job
job-dbmfo1t6e07s73c68ee0. Its physical request count and historical cause remain
UNKNOWN. Its retained error identifies the outer output/exit/cleanup boundary,
but the original outer receipt and child exception were not retained. The existing
bounded source_boundary_failed diagnostic remains in the successor.

The earlier loopback test called the real browser probe directly from source_worker;
it bypassed finite_acceptance and the inner probe subprocess/export checks. The new
test executes source_worker -> finite_acceptance -> supervised instrumented worker
-> Chromium -> actual capture validator. Only Chromium destination resolution/TLS
and the CI host-context check are substituted. All network traffic is loopback;
the test owns no runtime database credential or intake claim.

The uncorrected inner worker applies a 65,536-byte identity-audit limit to the
SCREENING_METADATA proof. A representative six-page/60-record audit is 305,657 bytes
indented and 211,389 bytes compact. It reproducibly raises WORKER_AUDIT_BOUND;
the parent then rejects its missing profile audit. Compact JSON alone is insufficient.
The corrected exact Manchester VALIDATED 2026-10-27..2026-11-02 proof uses the
existing 512,000-byte metadata allowance at the child, parent and finite-reader
checks. Other profiles retain their original bounds and serialization behaviour.
No fields are dropped. Original evidence and historical hashes are not rewritten.

A second observed issue was overlapping private child and parent audit copies:
the temporary-directory sampler saw approximately 606 KB against the unchanged
512 KiB aggregate envelope. The supervisor now closes the consumed child temporary
directory before exporting its validated parent receipt. Failure to clean up still
raises and produces no successful export. The final test observed 394,497 bytes,
no symlinks, exit 0, no limit hit, cleanup CLOSED and zero survivors. This removes
a demonstrated timing-dependent output-bound risk without relaxing the guard.

The full fixture now performs a measured browser POST as well as its initial GET.
Its two physical loopback requests match the audit; a DOM-only fixture's zero POSTs
correctly failed the existing accounting validator. No accounting assertion was
weakened. The corrected audit passes the actual capture validator with 60 records
and COMPLETE coverage. Original period09 causation is still not established.

A third defect appeared only when the real 60-record browser audit was connected
through actual runtime intake to disposable PostgreSQL. SQLLedger.batch_row embeds
the canonical capture as a JSON string; escaping expanded a valid checkpoint into
a 134,863-byte request, over the unchanged 131,072-byte payload guard. Job127633224853
on run 42138460540 records the exact stack from intake_slot through process_batch,
batch_row and _step to bounded. This is a demonstrated successor defect, not proof
of the lost period09 exception.

Period 10 alone now omits duplicate dom_text_content and rendered_label strings from
the projected checkpoint fields after full source validation. The complete original
audit is unchanged and retained/read back by source_sha256. Values, labels, locators,
state, truncation, original length, value hashes and row/segment provenance remain.
Screening decisions are identical. The representative nested payload becomes 118,655
bytes locally. No SQL guard, permission, completeness or accounting rule changes;
historical and non-period10 projection defaults remain unchanged.

## Exact releases

- Scraper: `5af5f42ca8e299a83017851fc8c61a03880ced2e`.
- Tree: `87125a88c1e4b1879a1d06fcf68099340d983562`.
- Workflow SHA256: `946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9`.
- Manifest SHA256: `044819280bfd7ac0850a79c9ddf8a409716175865a7494e19f0502be13e43a2c`.
- Owner code/pin: `c8b3950ea74c462843791f041349a4bd655110f7`.
- Source branch: `prep/b-timing-pg17-current-20261103`, unchanged at
  `c7e8b51eac69686f8d54ac2c295f5cb2f0002dd7`; scraper is 22 commits ahead / 0 behind,
  merge base exactly that baseline. Changes are scoped code/tests/sanitised evidence.
- Successor: `b-dbpilot-20261027-1102-10`; only new journal namespace is
  `b-dbpilot-20261027-1102-10_owner`. Runtime run ID is allocated once by the existing path.
- New Render artifact/job: NOT CREATED. Current historical artifact remains
  `dep-dbmflfbl550s7391n3eg` at c7e8b51. Never substitute it for the proposed release.

Owner and scraper bound files are byte-identical. The exact scraper entry point
admits 10; its registrar inventory matches the owner code, body SHA256
`cb49b35fa350446b9a17f70d8c61690227666ef08c2ec4d7bba4ebe8569f5717`.
The owner pin is outside the scraper bound-file manifest. Worker SQL, intake_finish,
the shared ledger and daily-intake implementation are unchanged.

## Fresh live read-only evidence

The exact owner CLI in `/tmp/propertyaigent-p10-c8b395-readonly` at c8b3950e returned
PRE_DISPOSITION_VERIFIED / ROLLED_BACK. The release was supplied only to that Python
process; no service environment setting changed.

- Settled09 receipt SHA256:
  `2549b1cde3f78f38b338a980003231ff8c9bc375de6720b40d05d4053afd0f1d`.
- Original09 final-result/event hashes remain
  `e423763cd0338d4c62839e07f263f5f61ecf353b68b1743760717bc286519725` /
  `121be5065c3b29b23dc367661f04cd6f888c7ebb8f27b62966bc11670d3324ff`.
- Original encrypted journal ordinal 55/hash
  `32f6a6cbc2419570dfce518afd40862ec6b3cb2913b40b32e97ef1cec2205d56` was readable.
- No active marker; period10 absent from periods, work revisions, evidence and owner
  journal. Exact old namespace/registrar, receipt, prior histories, Tameside work,
  required owner permissions and no-hazard checks passed.
- Generation 13; global_stop `{reason: DAILY_INTAKE_SHARED_FAILURE}`;
  manual_stop and last_hard_stop `ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP`.
- Runtime logins disabled, memberships 0, sessions 0, stable verifiers MATCH,
  temporary owner absent. Scraper suspended, exact saved configuration/environment
  equal, provider mutations 0; 75 terminal deployments and 23 terminal jobs observed
  at 2026-11-06T00:10:38.241571Z.
- Separate actual backlog reader at 2026-11-06T00:26:04.654284Z returned 24 Tameside
  records, completed screening and original period08/run768e1bd059474281ae9dc5113db42a99
  provenance. READ ONLY, ROLLBACK, connection closed. Protected work fingerprint:
  `959cc7c96a9fcd90446472da56e2209cacedbbef4fa3ea441d82d215fcf62f09`.

## Validation

The pinned scraper browser job 127624604330/run 42136130774 passed its file measurement
and all 4 outer/inner-worker regressions. Corrected full path: 6.190s, peak owned
RSS 851,038,208 bytes, 60 records/six pages, two loopback requests, COMPLETE capture,
cleanup CLOSED/zero survivors. The old-limit variant refuses WORKER_AUDIT_BOUND.
No council HTTP was spent. Browser binary remains the previously measured SHA256
`ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e`.

Hosted PG job 127621145319/run 42135106117 passed 103 checks plus 6 polling/accounting
checks. These cover actual owner entry points, fixed09->10 disposition, namespace
migration, registration, activation, successful/incomplete intake, archive readback,
screening/backlog, closure, duplicates, wrong receipt/stops/scope, rollback and
uncertain-acknowledgement readback. The later connected60-record validation is
recorded in the final validation addendum below.

Focused local source/transport/profile checks: 203 passed; two old Idox timeout
expectations failed identically on baseline 2d099e1 (2 failed/2 passed). These do not
execute the Manchester Arcus path. Broader frozen-hash/import-oracle reds retain
their documented baseline in PERIOD09-MANCHESTER-ONLY-REVIEW.md; historical hashes
were not rewritten. The repository is not represented as wholly green.

At final owner revision c8b3950e, four broader jobs fail the same frozen assertion
`test_stage4_direct_registration.py::test_exact_cohort_and_shared_bytes`: jobs
127633863392 (384 passed),127633863339 (493 passed),127633864216 (504 passed),
127633863334 (826 passed). The same assertion was reproduced independently at
baseline 2d099e1: expected probe hash 18819882..., actual baseline decc2b92.... The new
worker deliberately has another digest and an exact new release binding; rewriting
the historical oracle would hide the baseline discrepancy. These reds are disclosed,
not counted as successful checks or evidence against the connected fixed-window test.

The original midnight PG failure was OWNER_FULL_DAY_AND_CLOSURE_MARGIN at 23:58UTC;
the unchanged tests passed 60+6 after midnight. No clock or expiry guard was relaxed.
Intermediate browser failures (identity byte bound, fixture projection default and
missing fixture POST) were investigated and resolved, not hidden as passing runs.

## One executable live proposal — INACTIVE until approved

One approval should cover the fixed disposition, namespace/registrar migration,
source-branch fast-forward, build/startup verification, one Manchester-only10 run,
monitoring, independent evidence readback and cleanup. No owner web deployment,
new framework, new credentials, Tameside recollection or scheduled restart.

Before any mutation, repeat the exact read-only preflight and provider baseline,
verify no competing operation and enough day/cleanup margin. Refuse any drift.
Verify source branch still equals c7e8b51; conditional fast-forward only that branch
to 5af5f42, expected_sha=c7e8b51, force=false, then independently read back the head.

Existing owner Web Shell commands, only after approval:

```bash
cd /tmp/propertyaigent-p10-c8b395-readonly
test "$(git rev-parse HEAD)" = c8b3950ea74c462843791f041349a4bd655110f7
test -z "$(git status --porcelain)"
export PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-dbpilot-20261027-1102-10
export PROPERTYAIGENT_INTAKE_SOURCE_RELEASE='{"execution_binding":{"revision":"5af5f42ca8e299a83017851fc8c61a03880ced2e","workflow_sha256":"946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9","manifest_sha256":"044819280bfd7ac0850a79c9ddf8a409716175865a7494e19f0502be13e43a2c"},"tree":"87125a88c1e4b1879a1d06fcf68099340d983562","branch":"prep/b-timing-pg17-current-20261103"}'
python -B -m scripts.owner_period10 --action inspect
```

Stop unless PRE_DISPOSITION_VERIFIED/ROLLED_BACK and all independent checks match.
The source checkout is already prepared; if absent after service recycling, fetch
the exact owner commit from the existing GitHub repository and add a detached
worktree. Do not replace an existing dirty or mismatched checkout.

```bash
python -B -m scripts.owner_period10 --action dispose
python -B -m scripts.owner_period10 --action inspect
```

One transaction appends intake_periods[09].failure_disposition, bound to the settled
receipt, successor 10 and release, and clears only the two matched global/manual
failure stops. Generation 13, last_hard_stop and every other work/history/evidence
field remain unchanged. Expected disposition SHA256:
`65c0d9c865f615a6235cafd50a735eac74ca0a96b90e8bf4ad6dbd45055a1d69`.
Fresh connection must return DISPOSITION_COMMITTED_VERIFIED. Temporary permissions
must be absent. Unknown acknowledgement: inspect only; never repeat dispose to
discover whether it committed.

```bash
python -B -m scripts.owner_period10 --action prepare-successor
python -B -m scripts.owner_period10 --action verify-successor
python -B -m scripts.owner_period10 --action status
```

Preparation uses the existing atomic paired namespace/registrar migration, preserving
ownership/ACL/search_path and removing temporary SET/schema/issuer permissions before
commit. It then uses the existing journalled build/startup path. Verify artifact
commit/tree/workflow/manifest/branch and browser SHA, clean checkout, zero startup
runtime authentications and zero council requests, cleanup reserve, dormant access,
exact baseline restoration and suspension. No intake is allowed on an unverified
artifact. On uncertain migration/build/startup acknowledgement read back the exact
function pair, journal and provider history; never repeat preparation blindly.

Immediately before the single submission, independently observe Dashboard isolation:
no inherited environment groups/credentials, secret files, competing deploy/job/owner
operation; scheduling suspended. Timestamp only after that observation; submit
within 300 seconds:

```bash
P10_OWNER_CHECKED_AT="$(date +%s)"
python -B -m scripts.owner_period10 --action run-successor --owner-checked-at "$P10_OWNER_CHECKED_AT"
```

Manchester only, VALIDATED 27 October–2 November 2026 inclusive. Existing ceilings:
80 requests, 20 MiB network bytes, 60 listings/six pages,75s source, 1 GiB source group,
2 MiB per file only for this fixed Manchester profile,512 KiB exported output,
960s aggregate intake. Zero retries/replay; GitHub publication NOT_REQUESTED.

Follow the existing job to terminal. Uncertain submission: reconcile journal and
Render history before any further action; never submit again. Use status and, if
supported cleanup is required, close-successor. Independently verify both restricted
roles qualified; terminal traversal/reconciled coverage/accounting; durable capture
body/hash readback; all screenings and metadata batches; discoverable Manchester
backlog. Re-read the shared backlog with original Tameside 24 provenance kept separate.
Verify logins disabled, memberships/sessions 0, authorities closed, temporary permission
absent, unchanged stable verifiers, exact scraper config/environment restored and
suspension. Any partial or UNKNOWN result is NO-GO for pilot acceptance.

No additional Render loopback fixture was run: the meaningful missing nested boundary
is now covered in disposable CI. Render cgroup, real source behaviour, final artifact
and connected live success remain to be established by the approved sequence.
Stage 4 stays OPEN. A functioning narrow Manchester window is not GM-wide readiness.

## Final connected validation

Pinned scraper 5af5f42: workflow 42138690828, browser job 127633218237 passed the file
measurement and four real outer/inner-worker regressions. Full path observed 60
records/six pages, two physical loopback requests, COMPLETE actual capture validation,
6.013s, 851,816,448-byte peak owned RSS, 394,496-byte temporary regular files,
exit 0, no limit hit, cleanup CLOSED and zero survivors. The old-limit variant refused
WORKER_AUDIT_BOUND (305,656-byte indented / 211,388-byte compact audit).

The same retained synthetic browser capture was downloaded into disposable PG17;
no second source collection occurred. Job127634035182 passed the two focused actual
owner/runtime cases (17.96s), then 104 full successor/recovery/rollback/history/
permission/closure checks (245.69s), plus 6 polling/accounting checks (9.39s).
The successful connected case completes 60 Manchester screenings and 60 discoverable
backlog entries alongside the unchanged 24 Tameside records, with separate archive
period/run provenance. The incomplete case remains unverified; duplicate admission
refuses before transport. Independent owner finalisation and access closure pass.

Owner c8b3950e: diagnostic workflow 42138884551/job 127633863954 passed 47 checks;
period08 preservation workflow 42138884564/job 127633863411 passed 26 checks.
Focused local tests passed 17 plus the unchanged historical compact-projection check.
New release source branch ancestry was independently reread: 22 ahead/0 behind c7e8b51.

The real live source may differ in content, size, timing or browser behaviour. This
fixture does not guarantee every legal 60-record response fits the existing envelopes;
oversized or ambiguous responses still refuse. No live Manchester coverage, new
Render artifact, startup job or intake success is claimed.

Synthetic evidence artifact 13467655191 ZIP digest: `1ec52328020734a46c39b1960a3e7710f6dfe1eb0b71fdcb7dde97682c091fc3`. PG result artifact 13468155311 ZIP digest: `fc6c16eb1075ff18b282b5171d038726a22f71f5381ed2683dcf6cc6427365ec`. These are disposable evidence, not production captures.

Final owner pin validation: workflow 42138884528/job 127634699148 passed the two
focused actual owner/runtime cases (22.50s), all 104 checks (290.31s), and all 6
polling/accounting regressions (9.57s). Browser job 127633863338 also passed.
The exact owner checkout independently returned PRE_DISPOSITION_VERIFIED with
ROLLBACK against live state. No live database/provider configuration was changed.

Recommendation: GO for REVIEW to authorise the single fixed period10 sequence above;
NO-GO for claiming Manchester live success or closing Stage 4. The remaining decision
is one combined approval for disposition, namespace migration, source-branch
fast-forward, exact artifact build/startup verification, restricted activation,
one bounded Manchester-only submission and independent cleanup. Period 10 remains
unused. No owner credential setup or routine log relay is required.

Remaining broad CI reds are also accounted for. AH job 127634283528 has the old
frozen-v6 import-oracle assertion (1867 passed). Discovery job 127633864198 has the
11 old Idox timeout/three-council continuation expectations (1508 passed after an
initial 414 passed). A fresh baseline 2d099e1 reproduction of those files plus the
oracle produced exactly 12 failures/279 passes; the historical DB inspection test
was skipped without PG. Its failing first inventory assertion was separately
reproduced without a DB: the old frozen SQL lacks the baseline registrar hash
1d05b3f4476a8ad2a14aa083eb15396c9d157265dc19254df738777673cd995d,
matching job 127633864690 (16 other checks passed). Job127633864496 passed its listed
PG suites and credential-free cgroup startup, then failed the same old three-council
local-all continuation expectation; the corresponding baseline CLI test reproduces
that boundary. None is a newly failing Manchester-only path. These are retained
baseline debt, not grounds to claim repository-wide green status or Stage 4 exit.
