# Minimum restricted partial-observation candidate — Stage 4 OPEN

Baseline master: `2af9a4fbfb5e7d894e928a72c4b7727e87adccdc`, tree
`0cfff362ca3c920775b0fb347f20bc9e66092c23` (PR178 integrated).

## Reconciliation and scope

Specification 032 §14.5 supplies the requirement; integrated Specification 033
supplies the receipt schema, strict admission and append-only history.
Specification 034 remains draft PR164, head
`9c8c08dfb0d13ace0c56dcf7df69b78da779ab0e`. Its historical two-site derivation
and tests are reused, not merged wholesale or represented as current worker SQL.
The open PR and local worktree inventory showed no overlapping published
implementation; the specification/proposal branches are left unchanged.

The current v3 worker has further receipt-only checks. The combined replacement
is mechanically derived from that current reviewed v3 body, with unique-site
checks and a reversible substitution list. The original PR164 derivation remains
available as historical proposal evidence. The combination also binds each
observation's screening task revision to its immutable observation digest, so a
later observation of an unchanged row cannot collide with the old child's
single-parent dependency. Configuration and decision rules are unchanged.
This is task/evidence versioning, not a second screening engine or history store.
Complete-receipt and historical v1 task identities remain unchanged.

## What the minimum path does

- Explicit controller selection `observation_councils=('bolton',)`, existing
  observation-enabled IdoxListingContract, and independently enforced exact
  SQL grant `observation_councils=["bolton"]` are all required. Default off.
- Existing idox_source first tries complete projection; only TOTAL_UNKNOWN may
  reach the existing observe validator. All its Bolton RECEIVED, strict echo,
  one-page, non-empty/below-page-size, provenance/accounting/cleanup checks run.
- Existing archive_capture verifies raw archive readback before the checkpoint.
  The existing broker owns source resolution; arbitrary worker checkpoints are
  refused even if capture_only is absent/false. No enqueue/issuer capability.
- Existing batch plans/SQLLedger/process_batch and Coordinator.screening accept
  observations only under the explicit selections. The result adds source kind,
  observation/record digests, timestamp, display label and window_claim NONE.
  v3 configuration/code binding and authoritative routing remain unchanged.
  Restricted callers select link_related=False; history is a separate bounded
  read, never a reason to supply an Application engine.
- retain_observation is a real ControllerLedger/DatabaseBudget controller seam,
  not a disposable Ledger shortcut or a production CLI. The controller checks
  the exact installed worker body/owner/search path/security-definer profile
  through the restricted connection before source intent/calls. A claim may
  already exist and remains for explicit recovery if that gate refuses. Rollback
  disables capture before an observation can be stored. Direct queued-child
  screening also checks the same body pin before recording an assessment. Source-free recovery
  requires a sealed prior receipt and separately authorised operator claim
  recovery; an unresolved source intent is never replayed. The fixture activates
  the already mapped restricted recovery login only in disposable PostgreSQL.
- Existing observation_history is rebuilt over immutable explicitly named
  checkpoints. Exact duplicate evidence delivery is idempotent; distinct
  observations and assessments are preserved, with no current/supersedes state.

A ledger task state COMPLETE means that task finished; it is not a window claim.
The existing approved internal task outcome ENUMERATED_METADATA_RETAINED is
reused as specified in 034; the observation kind and display label always carry
window_claim NONE. This candidate does not emit the full owner/hosted status
ending AUTHORITY_INVALIDATED, since that lifecycle is not implemented here.

## Hard boundaries

No Application engine is supplied to this path. No Application, Site, opportunity,
scheme, unit fact, model, document or parent effects. PR178 requires a complete
receipt and rejects this kind. Complete-window batching remains default-deny for
observations without explicit enablement. Existing capture_once, resume_capture,
metadata/admission and coverage contracts retain their kind checks. No absence,
newly-submitted, coverage, watermark or complete-superset inference is introduced.
Only a valid supported observation avoids the source contract hard stop; source,
identity, resource, archive, SQL and uncertainty failures retain stop behaviour.

## SQL review and held installation dependencies

`worker-step-observation.sql` replaces only public.ingestion_worker_step, using
the existing temporary ownership ceremony. The rollback restores the exact
reviewed v3 worker, not the obsolete pre-v3 body. No schema, role, signature,
ACL, search path, policy, exception or recovery-function changes. Scripts are
review artifacts only and must not be installed under this authority.

The existing Owner.verify_installed inventory does NOT recognise this new body.
A later exact inventory/owner-hosted enablement and registration/allowance review
is required before production use. This candidate deliberately does not teach
current modes to accept a new state, add a campaign runner, issue a grant or
change a stop. Existing access/credential approvals cannot silently enable it.
No production access is used to determine the currently installed body here.

## Validation and evidence limits

Disposable PG17 uses the actual restricted worker/effect/recovery logins and real
ControllerLedger/DatabaseBudget. Bootstrap only installs/asserts/constructs
fixtures; operational effects use the restricted identities. Existing PR178
restricted admission tests and complete/v1 regressions are retained.
Injected crashes and acknowledgement loss (before and after broker commit) are explicit simulation boundaries;
recovery expires a fixture lease to avoid sleeping, then invokes the existing
restricted recovery function. No source call or effect is replayed.

Single-page HTML is RECONSTRUCTED via existing fixtures; the original sparse
Bolton body was not retained. It does not qualify real markup or any other
council. The archive test writes/readbacks a disposable file with an explicitly
synthetic Git commit reference: it proves the existing archive contract and
checkpoint hash binding, not GitHub durability or a new publisher. Earlier
accepted publisher/authority/kernel-memory evidence is reused, not rerun live.

CI exports runtime command/connection/returned-value/time/closure receipts,
retained archive bytes and separate fixture cursor/connection calls. These are
measured rehearsal costs, not proposed production limits or total network bytes.
The supervisor includes fixture/test overhead; no production RSS fit is claimed.
The draft PR records exact head, final tests/review, CI/artifact hashes and costs.

## Coverage and priority

Useful for a later separately authorised Bolton RECEIVED sparse observation,
including a relevant historical/bridge interval if genuinely supported evidence
is acquired. It cannot reconstruct the missing original sparse body, revive a
consumed authority or automatically resolve any historical task. It does not
address Bury/Oldham/etc completeness gaps, Arcus routes or the 401 metadata tasks.
Those populations and earlier admission outcomes remain separately reconciled.

Partial retention is useful acquisition evidence but is NOT itself a mandatory
complete-enumeration mechanism. The finite Stage 4 campaign still needs the
Specification 029 qualified complete-window route, denominators, overlap,
public-availability/latency evidence and gap handling. This capability is needed
only if that campaign explicitly elects to retain/screen supported partials;
it cannot waive completeness or make a sparse window COMPLETE. No freeze or
acceptance dates are established here. Retention remains no-pruning pending the
existing unresolved policy decision; no deletion path is added.
