"""Which limit applies at each layer, and the refusal of a selection whose layers do not fit, BEFORE any source work (dormant; pure).

Layers, outermost first, with the exact comparison each one makes in the existing code:
  reader      the named execution budget (verification.discovery.execution_budget): worker_seconds, source_outer_seconds, source_memory_bytes, rss_ceiling_bytes, slot_active_seconds
  supervisor  IDOX_REQUESTS: operational_supervisor.supervise(source=True) kills a source at 45 s and a non-source child at 165 s;
              BROWSER_RELEASE: the release Source kills the source cgroup at the budget's source_outer_seconds
  ledger      the work item's `limits`, enforced AFTER the work by coordinator.validate_source_resources / validate_outer:
              supervisor_seconds <= worker_seconds; outer elapsed_seconds < outer_seconds; source peak <= source_rss; outer peak <= aggregate_rss
  grant       expires_at (the SQL step accepts 0 < expiry <= 24 h), source_calls and writes
An incompatible selection is refused with the layer and field. Nothing is raised, lowered, clamped or substituted: the caller must select compatible values explicitly.
"""
from app.ingestion.ledger import DEFAULT_LIMITS, Denied
from verification.discovery.execution_budget import select

IDOX_SUPERVISOR = dict(source_seconds=45, controller_seconds=165)      # operational_supervisor.supervise
GRANT_MAX_SECONDS = 86400
STAGE_LEASE_SECONDS = 165      # the lease the chain caller claims each post-capture stage with (the non-source supervisor ceiling)

# The reviewed ledger item limits for a browser (Arcus) capture under BROWSER_SOURCE_V2. Chosen EXPLICITLY (never derived at run time): each value is the smallest round figure that
# satisfies `required_item_limits` and the other limits keep their DEFAULT_LIMITS values. Reconciliation verifies them; it does not produce them.
BROWSER_SOURCE_V2_ITEM_LIMITS = dict(DEFAULT_LIMITS, worker_seconds=75, outer_seconds=90, source_rss=1536 * 1024 ** 2, aggregate_rss=1536 * 1024 ** 2)


def layers(binding, item_limits, *, lifetime_seconds=None):
    """The limit that applies at every layer for this selection (a record for the report, not a decision)."""
    budget = select(binding.execution_budget)
    if binding.supervisor == 'IDOX_REQUESTS':
        supervisor = dict(source_deadline_seconds=IDOX_SUPERVISOR['source_seconds'], controller_deadline_seconds=IDOX_SUPERVISOR['controller_seconds'])
    else:
        supervisor = dict(source_deadline_seconds=budget['source_outer_seconds'], slot_active_seconds=budget['slot_active_seconds'], source_memory_bytes=budget['source_memory_bytes'])
    return dict(reader={k: budget[k] for k in ('worker_seconds', 'source_outer_seconds', 'source_memory_bytes', 'rss_ceiling_bytes', 'slot_active_seconds')},
                supervisor=supervisor,
                ledger={k: item_limits[k] for k in ('worker_seconds', 'outer_seconds', 'source_rss', 'aggregate_rss', 'requests', 'bytes', 'rows', 'pages', 'audit_bytes')},
                grant=dict(lifetime_seconds=lifetime_seconds, maximum_seconds=GRANT_MAX_SECONDS))


def required_grant_seconds(binding, *, batches, nominees):
    """Worst-case sequential time the registered authority must outlive: the capture slot, then one lease per batch and per nominee."""
    return select(binding.execution_budget)['slot_active_seconds'] + STAGE_LEASE_SECONDS * (batches + nominees)


def reviewed_item_limits(binding):
    """The ONE ledger limits value reviewed for this binding. A caller never names limits: it passes this constant, and `item_problems` refuses anything else."""
    return BROWSER_SOURCE_V2_ITEM_LIMITS if binding.execution_budget else DEFAULT_LIMITS


def item_problems(binding, item_limits):
    if binding.supervisor == 'IDOX_REQUESTS' and binding.execution_budget is not None:
        return ['reader.execution_budget_not_supported_by_supervisor']
    if not isinstance(item_limits, dict) or set(item_limits) != set(DEFAULT_LIMITS) or any(type(v) is not int or v < 0 for v in item_limits.values()):
        return ['ledger.item_limits_malformed']
    budget = select(binding.execution_budget)
    need = {'ledger.worker_seconds': (item_limits['worker_seconds'], '>=', budget['worker_seconds']),
            'ledger.outer_seconds': (item_limits['outer_seconds'], '>', budget['source_outer_seconds']),
            'ledger.source_rss': (item_limits['source_rss'], '>=', budget['rss_ceiling_bytes']),
            'ledger.aggregate_rss': (item_limits['aggregate_rss'], '>=', budget['source_memory_bytes'])}
    if binding.supervisor == 'IDOX_REQUESTS':
        need['supervisor.source_seconds'] = (IDOX_SUPERVISOR['source_seconds'], '>=', budget['worker_seconds'])
    problems = [name for name, (have, op, want) in need.items() if not (have >= want if op == '>=' else have > want)]
    if item_limits != reviewed_item_limits(binding):      # fits the budget is necessary, not sufficient: the stored limits are exactly the reviewed value (requests, bytes, rows, pages, audit_bytes included)
        problems.append('ledger.item_limits_not_reviewed')
    return problems


def grant_problems(binding, lifetime_seconds, *, batches, nominees):
    required = required_grant_seconds(binding, batches=batches, nominees=nominees)
    return [] if isinstance(lifetime_seconds, (int, float)) and required <= lifetime_seconds <= GRANT_MAX_SECONDS else ['grant.lifetime_seconds']


def reconcile_items(binding, item_limits):
    """The ledger/reader/supervisor fit of a work item's limits, checkable before any chain is known (capture registration, and the preflight of a registered root)."""
    problems = item_problems(binding, item_limits)
    if problems:
        raise Denied('LIMIT_INCOMPATIBLE:' + ','.join(problems))
    return layers(binding, item_limits)


def reconcile(binding, item_limits, *, lifetime_seconds, batches, nominees):
    """Return `layers(...)` for a compatible selection; raise Denied('LIMIT_INCOMPATIBLE:...') naming EVERY violated layer.field otherwise."""
    problems = item_problems(binding, item_limits) + grant_problems(binding, lifetime_seconds, batches=batches, nominees=nominees)
    if problems:
        raise Denied('LIMIT_INCOMPATIBLE:' + ','.join(problems))
    return layers(binding, item_limits, lifetime_seconds=lifetime_seconds)


INTAKE_SCOPE_SECONDS = 300


def pending_grant_problems(lifetime_seconds,*,phase,batches=0,nominees=0,cumulative_screening=False):
    """New staged path only: completed stages consume no second expiry reservation."""
    pending={'CAPTURE':1,'SCREENING':batches,'ADMISSION':nominees}
    if phase not in pending:raise Denied('STAGED_PHASE')
    if type(cumulative_screening) is not bool or cumulative_screening and phase!='SCREENING':raise Denied('STAGED_PHASE')
    # Intake's explicit mode enforces ONE cumulative scope deadline through the
    # production DatabaseBudget, rather than granting 165s anew to every batch.
    # Historical callers retain their original per-item lifetime calculation.
    required=(INTAKE_SCOPE_SECONDS if cumulative_screening else STAGE_LEASE_SECONDS*pending[phase])+30
    return [] if isinstance(lifetime_seconds,(int,float)) and required<=lifetime_seconds<=GRANT_MAX_SECONDS else ['grant.pending_lifetime_seconds']
