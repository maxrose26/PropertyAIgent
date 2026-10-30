# B inspection package — INACTIVE

Stage 4 OPEN. A technical acceptance is preserved. No production execution,
grant, Render operation or B processing is authorised by this package.

Baseline: c47b829ab766d2bdc7dfb329b9384c403ecb6a7d.
SQL SHA256: 131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997.
The fixed SQL is unchanged from the reviewed proposal. The adjacent client is
a fixed psql invocation, not a lifecycle controller or reusable recovery service.

## Inactive owner-terminal invocation

From an exact clean checkout of the final reviewed package (not merely the
baseline, which lacks these files), after separate inspection approval:

```bash
python3 -I -S docs/design/daily-intake-20261029/b-readonly-client.py
```

Requires existing psql, reviewed IPv4 and CA path, the existing approved owner
inspection identity postgres, and its hidden password. Host, database and pooler
routing user are fixed in the script. No new credential/privilege is issued.
The IPv4/CA must be established from approved route evidence, not guessed.
The default read-only/statement/lock/idle settings are applied at connection
startup, as well as within SQL. The password lives in a private temporary
0600 pgpass file, removed after the client terminates, never in arguments.
Do not share that file or the password. Evidence output directory is new/private.

Client execution is bounded to 60 seconds including termination allowance;
connection timeout 5 seconds; psql stdout/stderr share a bounded pipe. Evidence
files plus the short terminal classification fit 64 KiB. Timeout/overflow/error
means INCOMPLETE. No reconnect. Normal SQL ends in ROLLBACK; error process
closure requests server cleanup but does not prove remote termination. Server
statement/idle timeouts provide additional bounds, not an acknowledged receipt.
Forced-exit status says NOT_ACKNOWLEDGED. No follow-up connection is automatic.

## Interpretation: observations are not B approval

psql exit zero means only SQL execution completed. Review all ten result sets.
Expected rows: Q1=1, Q2=2, Q3<=30, Q4<=32, Q5=14, Q6=6, Q7=12,
Q8=4, Q9=1, Q10<=200. Sentinel rows (31/33/15/25/49/5/2/201 at
their respective queries) expose overflow; they never authorise truncation.
Q3 must establish all required effective timeout settings; absent settings
are not a default-value pass. Q4 requires interpretation of the complete
membership set; Q5 does not inventory arbitrary unlisted capability roles.
Q6 requires each expected function exactly once and every comparison true.
Q7/Q8 require comparison with the exact candidate's intended permissions,
not all flags true. Required NULLs/missing rows/roles/functions are INCOMPLETE.
False required comparisons are a demonstrated mismatch, never permission to
repair. Q9's stop-presence fields are observations, not an active-stop verdict.
Do not treat empty RLS-filtered results as global absence: when observer RLS
is active, establish applicable SELECT-policy coverage independently or report
INCOMPLETE. Do not change permissions to gain visibility.

This is a partial readiness inspection: not restricted-login authentication,
complete session inventory, archive access, source qualification, period issuance,
the complete production gate, or B execution acceptance. Stop digest is not the
application's canonical registration binding. No auto-repair or go/no-go engine.

## Source evidence and unresolved inputs

Manchester historical checkpoint SHA256:
b486cea799886fd4317e18241a4ea6615969a27012b7de3af98be9ab395b2210.
Historical metadata is evidence for qualification, not a current execution
receipt. SOURCE_BINDING refusal must remain; do not relabel the old case.
Current runtime constructs ArcusListingContract from UI_CASES via
assessment_dated_config, validate and qualify_segment, and the period supplies
contract/qualification_sha256. A proposed qualification must bind the historical
checkpoint, those current reader/validator/adapter hashes, date semantics and
field/truncation/zero-result limitations. No accepted current binding is claimed
by this package; a hash of a new manifest would bind an assessment, not transform
historical output into a new run receipt. Reuse retained Manchester evidence;
do not request a scrape solely for a changed run identity.

Tameside expected original archive:
discovery-idox-family-38551641270-1d56634aaf991ee8c1d3760cba3172245bfde3d4.zip
Expected SHA256:
ea58c15c5a6300ab554cf8e6dfede367ce729800026cdd910b2e975501fddc20.

Owner can check a known local copy without exposing its contents:

```bash
read -r -p 'Original Tameside archive path: ' archive_path
sha256sum -- "$archive_path"
```

Location remains owner input; no GitHub artifact is not proof no copy exists.
If unavailable/insufficient, retain a separate one-window, listing-only metadata
qualification proposal: proposal/address/type/date, truncation, provenance and
pagination, existing finite Idox limits, no details/database/retry. No execution.

A administrative closure requires the existing RESTORATION_VERIFIED output;
do not rerun restoration merely because the record has not been supplied here.
