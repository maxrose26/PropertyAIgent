# Retained v3 nominee to restricted admission: offline candidate

Baseline: `04b970f6ee049811d5a3a0cde7ca25b979cafde3`, tree
`fddcf5a17f8bf8ac21c40cf289cb9adde5e7ef73`. Stage 4 OPEN.

## Change and trust boundary

The existing `operational_controller.execute` dispatches SQL-backed v3 admission
only through `V3AdmissionBinding`. Historical v1 and disposable Ledger callers
retain their defaults. A complete retained capture, completed batch and exact
completed assessment are required. The wrapper binds the nominated row,
council, source key/URL, assessment/configuration/code identity and existing
factual contract/task before effects. It cannot register or enqueue anything.

Only ADMIT_SCHEME and ADMIT_FOR_ASSESSMENT can reach the remaining gates. Other
outcomes remain retained, with no detail call or application. The informational
v1 disposition is not routing authority. No count, approval, buyer-fit or scheme
qualification claim follows from an eligible assessment.

The unchanged controller, coordinator/new_identity, discovery_admission and B2
perform exact identity checks, duplicate handling, source intent, fencing and
committed readback. Pending identities remain isolated. The broker transaction
and application transactions are separate: this is not atomic exactly-once
delivery. Unknown acknowledgements preserve WRITE_INTENT/stop barriers and
require reconciliation before subsequent writes.

No schema, SQL function, role, grant, privilege or stop-policy file is changed.
Existing reviewed installation SQL is used only to construct disposable tests.
The application writer remains a trusted capability with constrained columns,
not a row-specific SQL policy. Its credential is never given to source code.

## Validation and simulation boundary

`tests/test_ingestion_v3_admission_pg.py` uses real PostgreSQL 17, SQLLedger,
ControllerLedger/DatabaseBudget, public execute wrapper and the shared writer.
Actual effects use ingestion_worker_login, ingestion_effect_login and
ingestion_application_login, all non-superuser and NOBYPASSRLS. Bootstrap is
limited to fixture construction/assertions/teardown. The new CI job has no
protected environment, secrets, source transport or dispatch operation.

The two eligible outcomes, misleading informational v1 disposition, wrong
bindings, unsupported facts, existing identity, competing delivery, expiry,
interruption, B2 rollback, acknowledged B2 commit followed by readback failure,
and lost ledger acknowledgement after application effects are covered. The
uncertain cases also deny an unrelated already-bound task. Runtime permission
denials are exercised using the actual logins.

The competing delivery is a separate accounted process that wins between
precheck and admission. One-connection permission is preserved, so database
effects are serialised; it is not a simultaneous unrestricted-writer stress
test. Parent and child database counters are summed, while parent elapsed time
already includes the child wait. Lost ledger acknowledgement is injected before
broker commit, after application effects have committed.

Synthetic proposal/detail bodies pass through existing parsers. This does not
qualify a council source or test durable GitHub archive publication. The fixture
archive reference is explicitly synthetic. The complete pytest fixture/wrapper
process runs under the existing supervisor; its receipt and JUnit are archived.
Existing kernel-memory enforcement evidence is reused, not re-proved by RSS.

Runtime receipts count driver commands, attempts, returned data-value bytes,
time and connection/socket closure. Separate fixture cursor/connection counts
include setup/assertions and are not labelled runtime driver statements.
Effects distinguish identity rows, observed persisted facts and acknowledged
factual delivery. Process costs include pytest and fixture overhead. No metric
is described as total network traffic.

## Review corrections and evidence

Focused independent review requested completed-batch enforcement, exact factual
component/source-key binding, restricted application-login proof, a genuinely
post-B2-commit readback failure, unrelated-task barriers and child accounting.
These are implemented. The original fixture omitted the LISTING_METADATA
completion outcome; it was corrected without SQL expansion. A threaded race
fixture correctly hit the existing main-thread deadline guard and was replaced
by a separate process, not by weakening the guard. A misleading v1 priority
correctly retains an ineligible v3 result instead of requiring an exception.

The draft PR records the final exact head, CI runs/artifacts/digests, measured
costs and review outcome. Earlier failed CI results remain in history. Network-
denied regression validation is reused; only affected checks are run manually.

## Supported scope and later dependencies

Demonstrated: synthetic Bolton RECEIVED, existing Idox COUPLED factual contract.
The factory is not Arcus qualification. Manchester, Rochdale and Salford are
unsupported by this Idox wrapper; the other Idox councils are not qualified by
the Bolton fixture. Oldham/Stockport factual limitations remain unchanged.

Later production use needs an exact reviewed owner/hosted call-site manifest
carrying the new nomination binding, permitted factual task/source/write
allowances, installed writer capability and restricted mapping/activation.
None is installed, issued or activated here. Existing stop policies may require
a separately reviewed exact allowance; this candidate does not alter them.

The smallest later live proof is one eligible genuinely new supported nominee
from an independently authorised capture, with no listing refetch or substitute
if none is eligible. Application identity, factual acceptance, scheme admission
and buyer matching remain separate. Integration and production remain held.

Preserve accepted storage, IDs1504-1508, all historical audits/uncertainty,
consumed authorities and the Salford stop. No sparse-observation Phase 2,
recovery campaign, scheduler, unit facts or later intelligence is included.
