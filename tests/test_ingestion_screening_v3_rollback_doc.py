"""The recovery sequence of the screening-v3 activation (PR #175) names real artefacts, real inventory states and the ordering the code and the disposable rollback test establish."""
from pathlib import Path

import pytest

pytest.importorskip('resource')

from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / 'docs/design/ingestion-screening-v3-activation-20261030/ROLLBACK.md').read_text(encoding='utf-8').replace('\r\n', '\n')


def test_the_document_names_the_exact_scripts_and_they_exist():
    for path in (orr.SV3_WORKER_ROLLBACK, oo.GENERATION3_WINDOW_POLICY):
        assert (ROOT / path).is_file() and path.name in DOC
    assert 'worker-step-original.sql' in DOC and 'policy-window-allowance.sql' in DOC


def test_the_document_names_every_reviewed_inventory_state_the_owner_recognises():
    source = (ROOT / 'verification/ingestion_storage/operational_owner.py').read_text(encoding='utf-8')
    for state in ('GENERATION3_WINDOW_POLICY_APPLIED', 'GENERATION3_SCREENING_V3_POLICY_APPLIED', 'GENERATION3_SCREENING_V3_APPLIED'):
        assert state in DOC and "'%s'" % state in source


def test_the_order_and_the_stop_conditions_are_stated():
    assert 'worker function first' in DOC and 'policy second' in DOC
    assert DOC.index('## B.') < DOC.index('Confirm invalidation FIRST') < DOC.index('Reconcile active work') < DOC.index('restore the worker function, verify, restore the policy')
    for phrase in ('UNCERTAIN_RECONCILE', 'NO rollback script is run', 'Do not run any script', 'never run blindly', 'are not deleted or rewritten'):
        assert phrase in DOC
