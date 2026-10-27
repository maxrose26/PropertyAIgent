"""Exact council/family scope bindings for the integrated chain (dormant: nothing here registers, issues or runs anything).

A binding names ONE council, its source family, its date basis, the supervisor profile its source runs under, the execution budget its reader may select and the detail-identity
factory its nominees go through. The registry is closed: a council that is not listed is refused, and the councils that need qualification the repository does not yet hold are
refused with the exact reason instead of being guessed. Historical single-use registrations keep their own constants (the Bolton ceremonies are untouched and are not chain-bound).
Pure: no I/O, no URLs, no commands, no configuration beyond the reviewed table below.
"""
import re
from dataclasses import dataclass
from datetime import date

from app.ingestion.ledger import Denied

MAX_WINDOW_DAYS = 7      # the finite acceptance manifest's own window length (`verification.discovery.finite_acceptance.manifest`)


@dataclass(frozen=True)
class ScopeBinding:
    council: str
    family: str                 # 'idox' | 'arcus'
    semantics: str              # 'RECEIVED' | 'VALIDATED'
    supervisor: str             # 'IDOX_REQUESTS' (operational_supervisor) | 'BROWSER_RELEASE' (four-council release Source)
    execution_budget: str|None  # a named browser budget (Arcus UI reader only) or None for the historical envelope
    detail_factory: str         # the accepted new-identity factory the nominee's fresh detail verification goes through
    initial_status_states: tuple = ()


CHAIN_BINDINGS = {
    'bury': ScopeBinding('bury','idox','RECEIVED','IDOX_REQUESTS',None,'accepted_idox_new_identity'),
    'oldham': ScopeBinding('oldham','idox','RECEIVED','IDOX_REQUESTS',None,'accepted_idox_new_identity'),
    'stockport': ScopeBinding('stockport','idox','VALIDATED','IDOX_REQUESTS',None,'accepted_idox_new_identity'),
    'tameside': ScopeBinding('tameside', 'idox', 'RECEIVED', 'IDOX_REQUESTS', None, 'accepted_idox_new_identity'),
    'manchester': ScopeBinding('manchester', 'arcus', 'VALIDATED', 'BROWSER_RELEASE', 'BROWSER_SOURCE_V2', 'accepted_arcus_new_identity', ('Under Consideration',)),
}
HISTORICAL_ONLY = frozenset({'bolton'})      # single-use ceremonies with their own pinned constants; never a chain scope
UNQUALIFIED = {'rochdale': 'ROCHDALE_INITIAL_STATUS_UNQUALIFIED'}      # Rochdale's initial-status literal is not recorded in the repository: its mapping is not guessed


def binding_for(council):
    """The reviewed binding for a council, validated against the platform's own council configuration and the finite-acceptance date basis."""
    if council in HISTORICAL_ONLY:
        raise Denied('SCOPE_HISTORICAL_ONLY')
    if council in UNQUALIFIED:
        raise Denied('SCOPE_' + UNQUALIFIED[council])
    binding = CHAIN_BINDINGS.get(council)
    if binding is None:
        raise Denied('SCOPE_NOT_BOUND')
    from app.config import get_council
    from verification.discovery.finite_acceptance import ARCUS, SEMANTICS
    configured = get_council(council)
    expected_mode = 'validated' if binding.semantics == 'VALIDATED' else 'received'
    from .idox_target import COUNCILS
    closed_summary=False
    if council in COUNCILS and binding.family=='idox':
        from app.pipeline.discovery_contract import SOURCE_ROOTS
        from verification.direct_reference.refresh import IDOX
        host,prefix=SOURCE_ROOTS[council]
        closed_summary=(configured.base_url.rstrip('/')=='https://'+host+prefix.rstrip('/')
            and IDOX[council]==(host,prefix.rstrip('/')+'/applicationDetails.do')
            and configured.doc_system in ({'idox','idox_anite'} if council=='bury' else {'idox'}))
    family_ok = ((binding.family == 'arcus') == (council in ARCUS)
        and (binding.family == 'arcus' or configured.doc_system == 'idox' or (council=='bury' and closed_summary))
        and (council not in COUNCILS or closed_summary))
    if SEMANTICS.get(council) != binding.semantics or configured.date_field_mode != expected_mode or not family_ok:
        raise Denied('SCOPE_BINDING_CONFIGURATION_MISMATCH')
    return binding


def scope_for(binding, start, end):
    """The exact DISCOVERY_SCOPE (ledger task subject) of a window under this binding. Dates are ISO calendar days, start <= end, at most MAX_WINDOW_DAYS days."""
    if not isinstance(binding, ScopeBinding) or CHAIN_BINDINGS.get(binding.council) != binding:
        raise Denied('SCOPE_NOT_BOUND')
    for value in (start, end):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise Denied('SCOPE_WINDOW')
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise Denied('SCOPE_WINDOW') from None
    if a > b or (b - a).days >= MAX_WINDOW_DAYS:
        raise Denied('SCOPE_WINDOW')
    return {'kind': 'DISCOVERY_SCOPE', 'council': binding.council, 'start': start, 'end': end, 'semantics': binding.semantics}


def check_contract(binding, contract, start, end):
    """The listing contract a caller supplies must be this family's, capture exactly this scope and (Arcus) select exactly the binding's budget. Returns the scope."""
    from app.ingestion.arcus_adapter import ArcusListingContract
    from app.ingestion.idox_adapter import IdoxListingContract
    expected = ArcusListingContract if binding.family == 'arcus' else IdoxListingContract
    if type(contract) is not expected or contract.scope() != scope_for(binding, start, end):
        raise Denied('SCOPE_CONTRACT_MISMATCH')
    if binding.family == 'arcus' and contract.execution_budget != binding.execution_budget:
        raise Denied('SCOPE_BUDGET_MISMATCH')
    from .idox_target import COUNCILS
    if binding.council in COUNCILS and contract.partial_observation:raise Denied('CLOSED_IDOX_COMPLETE_REQUIRED')
    return contract.scope()


def check_detail_target(binding, record, target):
    """A fresh-detail case target must name exactly the nominated record of exactly this council: no other URL, reference or identifier can be verified under a nomination."""
    from .idox_target import COUNCILS,derive,validate
    if binding.council in COUNCILS:
        if target!=derive(binding.council,record):raise Denied('SCOPE_DETAIL_TARGET_MISMATCH')
        return validate(target)
    if (not isinstance(target, dict) or target.get('council') != binding.council or target.get('reference') != record['reference']
            or target.get('source_url') != record['source_url'] or target.get('source_identifier') != record['source_record_id']):
        raise Denied('SCOPE_DETAIL_TARGET_MISMATCH')
    return target


def check_capture(binding,contract,receipt):
    """Additional closed-chain binding; historical capture paths keep their defaults."""
    from .idox_target import COUNCILS
    if binding.council not in COUNCILS:return receipt
    scope=contract.scope()
    if (receipt.get('kind')!='LISTING_RECEIPT_V1' or receipt.get('council')!=binding.council
        or receipt.get('contract')!=contract.name or receipt.get('date_semantics','RECEIVED')!=binding.semantics
        or receipt.get('interval')!=[scope['start'],scope['end']]
        or receipt.get('qualification_sha256')!=contract.qualification_sha256
        or receipt.get('cleanup')!='CLOSED' or receipt.get('accounting_complete') is not True):
        raise Denied('CLOSED_IDOX_CAPTURE_BINDING')
    from app.ingestion.coordinator import validate_outer
    from .limit_reconciliation import reviewed_item_limits
    outer=receipt.get('outer_supervisor')
    if not isinstance(outer,dict):raise Denied('CLOSED_IDOX_SUPERVISOR_REQUIRED')
    validate_outer(outer,reviewed_item_limits(binding))
    return receipt
