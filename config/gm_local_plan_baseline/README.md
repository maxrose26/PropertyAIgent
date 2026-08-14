# GM Local Plan Baseline — proposed ingestion manifests

Frozen output of the Greater Manchester Local Plan / Strategic Allocation
Baseline research (branch `feature/complete-gm-local-plan-baseline`). These
are **review-only data manifests**, not an ingestion mechanism — nothing in
this repository reads them automatically, and no production write occurs
from their presence here.

- `gm_local_plan_new_sites.json` — 207 proposed new `LocalPlanSite` rows
  across Bolton, Manchester, Oldham, Salford, Tameside, Trafford, Wigan.
  Field names match `app.db.models.LocalPlanSite`. Null is valid where a
  source doesn't support a value — never inferred.
- `gm_local_plan_updates.json` — 38 proposed updates to existing rows: 36
  PfE `submitted_allocation` → `adopted_allocation` status corrections, 1
  Medipark council reattribution (Trafford → Manchester), 1 Heywood/
  Pilsworth (JPA1.1) capacity/use correction from employment-only to
  mixed-use (~200 dwellings) — the resolution of the Bury "Castle Road
  (Unsworth)" completeness question.
- `gm_local_plan_relationship_review.json` — 10 proposed `AllocationRelationship`
  candidates. **Deferred** — Product Owner decision: not included in the
  first production ingestion pass.
- `gm_local_plan_ah_sidecar.json` — affordable-housing intelligence that has
  no semantically correct home in the current `LocalPlanSite` schema.
  Review-only; not forced into an existing field.
- `gm_local_plan_manual_review.json` — non-blocking issues attached to
  otherwise-evidenced sites (stale monitoring data, pending council
  decisions, unresolved source discrepancies).
- `gm_local_plan_excluded.json` — candidate sites/sources considered and
  excluded, with reason, so the audit trail doesn't silently drop them.

Recovered from prior research already completed in this task's session
(conversation context, sub-agent outputs, committed test fixtures, and one
local read of an already-downloaded PDF to resolve Castle Road) — no new
web research was performed to build these files. See the task's final
report for full per-council provenance and the 1-row Bolton reconciliation
note (108 nominal vs 107 recovered — reference `15SC` does not exist in
Bolton's own numbering, confirmed by primary-source research, not a
recovery gap).
