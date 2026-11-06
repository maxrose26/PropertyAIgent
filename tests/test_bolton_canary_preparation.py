"""Offline evidence for the proposed scope; NOT live admission or a release.

No council transport. Real Idox reader/validator, synthetic responses. Owner
boundary tests deliberately prove why the unchanged lifecycle is not a release.
"""
import copy
import json
from datetime import date

import pytest

from app.ingestion.ledger import DEFAULT_LIMITS, Denied
from tests.e2e_connection_support import entry, SCHEME, idox_audit, idox_contract, outer
from tests.test_owner_database_pilot import bound
from verification.ingestion_storage import intake_owner as owner
from verification.ingestion_storage.intake_budget import IntakeRun, LIMITS, RESERVE

START, END = date(2026, 11, 3), date(2026, 11, 5)


@pytest.mark.parametrize('count', [1, 24, 60])
def test_actual_bolton_reader_and_capture_contract(count):
    audit = idox_audit('bolton', [entry(f'B/{i}/26', SCHEME) for i in range(count)], START, END)
    receipt = idox_contract('bolton', START, END).project(audit, outer(), DEFAULT_LIMITS)
    assert len(receipt['records']) == count
    assert audit['enumeration_evidence'] == 'COUNT_RECONCILED'
    assert audit['resource']['requests_attempted'] <= 10
    assert audit['resource']['retries'] == 0
    assert audit['resource']['received_bytes'] <= 3_000_000
    assert audit['resource']['elapsed_seconds'] <= 45
    assert audit['cleanup'] == 'BOUNDARY_CLOSED'
    assert len(audit['pages']) <= 6
    assert len(json.dumps(audit).encode()) <= 512 * 1024


def test_sparse_page_without_terminal_proof_still_refuses():
    audit = idox_audit('bolton', [entry('B/1/26', SCHEME)], START, END, single_page_no_pager=True)
    assert audit['enumeration_evidence'] == 'TOTAL_UNKNOWN'
    with pytest.raises(Denied, match='IDOX_WINDOW_BINDING_OR_COMPLETENESS'):
        idox_contract('bolton', START, END).project(audit, outer(), DEFAULT_LIMITS)


@pytest.mark.parametrize('change', ['date', 'accounting', 'cleanup'])
def test_changed_or_incomplete_capture_is_not_success(change):
    audit = idox_audit('bolton', [entry('B/1/26', SCHEME)], START, END)
    if change == 'date':
        audit['applied_interval'] = ['2026-11-02', '2026-11-05']
    elif change == 'accounting':
        audit['resource']['budget_exhaustion'] = True
    else:
        audit['cleanup'] = 'UNKNOWN'
    with pytest.raises(Denied):
        idox_contract('bolton', START, END).project(audit, outer(), DEFAULT_LIMITS)


def test_whole_owner_lifecycle_960_is_not_current_job_limit(bound):
    binding, policy, _ = bound
    assert LIMITS['wall_seconds'] == 960
    assert RESERVE['wall_seconds'] == 180
    assert binding['valid_until'] - binding['timing_policy']['bound_at'] == 2100
    assert binding['valid_until'] - policy['expires_at'] == 185
    shortened = copy.deepcopy(binding)
    shortened['valid_until'] = shortened['timing_policy']['bound_at'] + 960
    shortened['runtime_deadline'] = shortened['valid_until'] - 185
    with pytest.raises(Denied, match='FINITE_FIXED_DEADLINE'):
        owner.validate_binding(shortened, opening=True, now=shortened['timing_policy']['bound_at'])


def test_existing_owner_refuses_proposed_bolton_identity_before_effects(bound):
    binding, _, _ = bound
    binding = copy.deepcopy(binding)
    binding.update(period='b-bolton-20261103-1105-01', fixed_window={'start': str(START), 'end': str(END)})
    with pytest.raises(Denied, match='OWNER_DATABASE_PILOT_SCOPE'):
        owner.validate_binding(binding)


def test_job_reserve_is_inside_960_not_owner_setup_or_restoration():
    clock = [0.0]
    run = IntakeRun(clock=lambda: clock[0])
    clock[0] = 780.0
    with pytest.raises(Denied, match='INTAKE_RUN_DEADLINE'):
        run.check()
    run.closing = True
    run.check()
    clock[0] = 960.0
    with pytest.raises(Denied, match='INTAKE_RUN_DEADLINE'):
        run.check()
