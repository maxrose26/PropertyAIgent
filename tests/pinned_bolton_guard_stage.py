"""Run in the unchanged #213 checkout with the new guard loaded by file path."""
import importlib.util
import json
import os
from pathlib import Path

import pytest
from tests.test_bolton01_settlement_pg import (
    failed_bolton, succeeded10, ready10, ready09, failed09, failed08,
    settled08, failed07, world, Fault,
)
from verification.ingestion_storage import bolton01_settlement as recovery
from verification.ingestion_storage import intake_owner as owner

spec = importlib.util.spec_from_file_location('candidate_guard',
    Path(os.environ['S4_SUCCESSOR_ROOT']) / 'verification/ingestion_storage/bolton_recovery_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_guarded_real_recovery_and_lost_ack(failed_bolton):
    w = failed_bolton
    boot = w['boot']
    before = owner.ledger_sha(boot)
    # Previously missed state/phase, different authority: refuse under the
    # original table/controller locks, before any recovery write.
    boot.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=repeat('0',64)",
                 (json.dumps(dict(key='f'*64, state='CLAIMED', phase='IDLE', authority='unrelated')),))
    blocked = owner.ledger_sha(boot)
    with w['actor']() as actor:
        with pytest.raises(owner.Denied, match='OTHER_WORK'):
            guard.recover(actor, w['binding'], pinned_module=recovery)
    assert owner.ledger_sha(boot) == blocked
    boot.execute('DELETE FROM ingestion_work_items WHERE key=%s', ('f'*64,))
    assert owner.ledger_sha(boot) == before
    with w['actor']() as actor:
        with pytest.raises(RuntimeError):
            guard.recover(Fault(actor, 'lost'), w['binding'], pinned_module=recovery)
    # No repeat mutation after uncertain COMMIT: fresh connection readback.
    with w['actor']() as fresh:
        result = recovery.inspect(fresh, w['binding'])
    assert result['status'] == 'COMMITTED_STATE_VERIFIED_READ_ONLY'
    assert result['stop'] == recovery.STOP15
    assert recovery.all_other_work_sha(boot) == w['all_other']
    assert boot.execute(owner.MEMBERS).fetchall() == w['members']
    assert boot.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall() == w['evidence_before']
