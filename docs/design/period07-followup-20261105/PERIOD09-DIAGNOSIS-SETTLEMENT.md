# Period09 diagnosis and inactive settlement candidate

MASTER STAGE 4 OPEN. Period09 consumed. No live settlement, stop disposition,
deployment, runtime activation, council request or intake submission is authorised
by this preparation. Tameside's accepted period08 result remains separate.

## Bound historical run

- Period `b-dbpilot-20261027-1102-09`; run `bc4a50f3e4f44262a41a1b4036c3392b`.
- Render job `job-dbmfo1t6e07s73c68ee0`; failed.
- Historical scraper `c7e8b51eac69686f8d54ac2c295f5cb2f0002dd7`;
  artifact `dep-dbmflfbl550s7391n3eg`.
- Original handoff `b4d4227e8c4073364f904098e4efd0b34ca054d2`.
- Final result SHA256 `e423763cd0338d4c62839e07f263f5f61ecf353b68b1743760717bc286519725`.
- Final events SHA256 `121be5065c3b29b23dc367661f04cd6f888c7ebb8f27b62966bc11670d3324ff`.
- Physical requests UNKNOWN, accounted requests 0 (not evidence of zero requests).
  Manchester coverage NOT_ESTABLISHED; no capture/checkpoint/screening/backlog.

## Demonstrated boundary, not a recovered historical root cause

The exact source raises SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY only after the
supervisor thread returned one result and the final database policy check passed.
It tests, in order: cleanup != CLOSED; exit code != 0; limit_hit != null;
missing/non-file output; output larger than 512 KiB. Short-circuit evaluation and
lack of a retained outer receipt mean the historical failing condition is unknown.

The historical reason rules out the earlier source polling, thread join timeout,
supervisor exception/no-result and final policy-read refusals as its immediate
origin. JSON parsing, metrics validation and capture projection occur later and
were not reached. Both restricted roles qualified. Neither successful database
closure nor provider restoration establishes source browser/process closure.

The exact provider interval (21:58:31–22:00:03 UTC, 5 November 2026) returned three
log records and no further page: launch, successful runtime qualification and
final bounded failure. Final retained events are runtime_authentication and
supported_registration only. No retained supervisor exit/limit/output/cleanup
receipt was found. No raw child stderr is retained: it is deliberately discarded.
Do not infer that another file-limit increase, timeout or retry would fix this.

The narrow diagnostic emits source_boundary_failed before the unchanged refusal,
with a fixed version, bounded exit code/classification, cleanup status, allowlisted
limit reason and output presence/size classification. It exports no exception
message, command, filename, child stderr or output content. Request accounting
stays UNKNOWN until validated source metrics are accepted. No production fix is
claimed from this diagnostic improvement.

## Live read-only reconciliation

Actual candidate entrypoint, finally rechecked at e0b1914573c71facd12cfa872d75873387b5a2f2, returned
READY_FOR_REVIEW_NOT_AUTHORISED, ROLLED_BACK. Only source-checkout preparation and
read-only inspection occurred in the existing owner shell; no web/scraper deployment.

- Exact OPEN marker SHA256
  `d5126cf9628f2365119fcb1ed73e19a301f2dec4fa74d35af8eda653d0e5f4cb`.
- Manchester key `21330c060171f6f95286a8f31131bda00fa3c081a21ebfc0f418b10706e510e4`:
  CLAIMED / SOURCE_INTENT, fence 1, attempt_count 1, expired lease, null checkpoint;
  one unfinished fence-1 attempt with null checkpoint.
- Generation12; global/manual/last_hard_stop DAILY_INTAKE_SHARED_FAILURE.
- Exact two-artifact inventory/hash readback; retained predecessor history,
  receipt-bound period08 disposition, execution binding and dormant authority verified.
- Both runtime logins disabled, memberships 0, sessions 0, stable verifiers MATCH,
  temporary owner absent. Required owner/recovery admin-only membership and schema
  baseline verified by the candidate's common/pending checks.
- Tameside fingerprint unchanged:
  `959cc7c96a9fcd90446472da56e2209cacedbbef4fa3ea441d82d215fcf62f09`.
  Original period08 capture/24 screenings/5 metadata batches verified by its original
  verifier; prior histories and artifacts are included in these checks.
- Scraper suspended; exact configuration/environment equal to saved baseline.
  Latest deploy remains dep-dbmflfbl550s7391n3eg at historical scraper revision.
- Journal ordinal55 SHA256
  `32f6a6cbc2419570dfce518afd40862ec6b3cb2913b40b32e97ef1cec2205d56`.
- Proposed settlement receipt SHA256
  `2549b1cde3f78f38b338a980003231ff8c9bc375de6720b40d05d4053afd0f1d`.

## Exact proposed transaction

Entry point scripts.owner_period09_settlement, default inspect; settle requires
PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY=b-dbpilot-20261027-1102-09.
Reuse the existing owner connection/encrypted journal; never put credentials in chat.

1. Verify original journal/binding and complete read-only preconditions above.
2. In one transaction, take the existing recovery locks and recheck the bindings.
   Temporarily inherit the existing recovery operator, call
   ingestion_recover_abandoned(exact Manchester key,1,false), revoke the exact
   temporary membership. No source/write replay is authorised.
3. Manchester item becomes SAFETY_BLOCKED / RECOVERED, fence2, owner/lease/checkpoint
   null, reason ABANDONED_SOURCE_INTENT, next_action RECONCILE. Its fence1 attempt
   becomes RECOVERED with finished_at populated and checkpoint still null.
4. Archive the full original marker and exact receipt under
   intake_periods[period09].failed_runs[run09], then retire only active intake_run.
   The receipt preserves UNKNOWN requests/cause, failed coverage and no checkpoint.
   It references Tameside's prior period08 result without rewriting its outcome.
5. Generation12 → 13 is the existing abandoned-effect recovery invalidation.
   Global stop remains {reason: DAILY_INTAKE_SHARED_FAILURE}; manual_stop and
   last_hard_stop become ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP. No stop is cleared.
6. Verify receipt/item/attempt, every unrelated work row and attempt fingerprint,
   predecessor histories, evidence, Tameside work, and remove temporary owner
   permissions before COMMIT. No runtime login, password or source activation.
7. Fresh independent connection: inspect must return
   COMMITTED_STATE_VERIFIED_READ_ONLY with the exact proposed receipt hash and
   generation13 stop tuple; transaction ROLLED_BACK.

On any uncertain acknowledgement, run inspect on a fresh connection only. A
committed receipt is success; any changed/partial state refuses. Do not rerun settle
merely to find out whether it committed. Duplicate settlement refuses.

Inactive commands for REVIEW (do not execute until separately authorised):

```sh
# Existing owner Web Shell. Preparation only until REVIEW authorises settlement.
cd /tmp/propertyaigent-p09-settlement-review
test "$(git rev-parse HEAD)" = e0b1914573c71facd12cfa872d75873387b5a2f2
python -B -m scripts.owner_period09_settlement --action inspect
PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY=b-dbpilot-20261027-1102-09 \
  python -B -m scripts.owner_period09_settlement --action settle
# Independent readback, including after any uncertain acknowledgement:
python -B -m scripts.owner_period09_settlement --action inspect
```

## Validation and decision

Candidate production code is unchanged after 6be6aebae389dcfb79a7457368e086bf954f02eb;
905ae7b04ff22fb746d0cd0122311ba88bc1b391 corrects the synthetic qualification-event
fixture and adds actual owner CLI validation. e0b1914573c71facd12cfa872d75873387b5a2f2
adds the real-browser/outer-supervisor combined test.

Hosted browser job 127590436216 / run42126052458 passed. The actual normal worker
used the fixed 2 MiB profile, loopback TLS transport and 60 synthetic records over
six pages, inside the real supervisor with reviewed Render profile/owned subreaper,
75-second ceiling, 1 GiB RSS ceiling and unchanged output/path bounds. Result:
exit0, limit=null, cleanup CLOSED, survivors0, accounting complete, 3.878s,
sampled peak owned RSS772907008 bytes. One loopback HTTP request served the fixture;
no council request. This does not reproduce period09's historical failure or
prove the live Manchester page/network behaviour.

The real Runtime.collect → subprocess source_worker → supervisor tests cover a
valid output, invalid fixture JSON, missing fixture, and worker export-bound refusal.
The three failure cases produce nonzero exit/missing output with verified process
cleanup and UNKNOWN accounting; the bounded diagnostic distinguishes them from
cleanup uncertainty and limit rejection without logging raw content.

Local process-envelope tests refuse LAUNCH_OR_ACCOUNTING_UNCERTAIN in this Work
runtime; no guard was bypassed. Hosted Ubuntu executes the real process tests.
Local bounded diagnostics:5 passed; polling/accounting:6 passed.

The initial hosted run42125427522 had54 passes/5 failures: the synthetic settlement
fixture omitted runtime_authentication while the production evidence correctly
required it. The fixture was corrected; the production verifier stayed intact.
Hosted run42125723592 at905ae7b04ff22fb746d0cd0122311ba88bc1b391:
60 passed (175.81s), plus6 polling/accounting checks passed. Includes17 fixed
settlement tests: successful single transaction, rollback before commit/after
recovery/before cleanup, lost acknowledgement readback,11 changed-state refusals,
and actual owner CLI authority/inspect/settle/fresh-inspect sequence. Assertions
compare all prior evidence bytes, prior histories, all unrelated work/attempts,
Tameside capture/screens/batches and the actual cross-run backlog reader output.
No live recovery was performed. Period08 regression job127590435536 also passed (26 checks).

All candidate production files are byte-identical between6be6aeb ande0b1914.
Final combined workflow42126052458 at e0b1914573c71facd12cfa872d75873387b5a2f2
passed both successor-pg and browser-files jobs, including the combined browser
boundary. Existing unrelated
red suites remain subject to the documented baseline in
PERIOD09-MANCHESTER-ONLY-REVIEW.md; this is focused-path validation, not a claim
that the entire repository CI is green.
No new live source request is needed for settlement. Settlement does not establish
Manchester readiness. Prefer settlement review separately from any next collection:
without a retained source-boundary receipt, another intake would repeat an unresolved
failure and consume another identity. Any further live diagnostic or submission
requires its own bounded approval. Stage4 remains OPEN.


## Recommendation for REVIEW

GO for the prepared fixed settlement, conditional on repeating the unchanged
preflight immediately before any separately authorised transaction. The prepared
owner checkout is /tmp/propertyaigent-p09-settlement-review at the exact tested
e0b1914573c71facd12cfa872d75873387b5a2f2; inspect passed and rolled back there.
NO-GO for another intake submission based on these results alone. The exact
period09 source-boundary condition and physical request count remain UNKNOWN.
Smallest next decision: authorise this settlement only; preserve all failure stops.
A later live observation must retain the new supervisor-boundary diagnostic through
the actual normal collector path; repeating the already successful initial-navigation
probe would not establish why the full collector failed. No new live route, limits
increase, source deployment or replacement submission is included in this handoff.
