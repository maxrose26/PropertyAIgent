"""The owner's definitive result: publication INSIDE the enforced memory scope and a bounded reserve, THEN the final closure, THEN the sealed local record (specification 032 section 14.7). Regression for the 20 October
window demonstration, where the owner closed the scope first, the closed-envelope guard denied its own publication, and the failure path overwrote a correct result with UNCERTAIN. The scope here is a stateful stand-in with the
production contract driving the REAL controller guard; the REAL cgroup-v2 scope is exercised by tests/owner_scope_publication_proof.py (stage4-hosted-memory-proof workflow). Offline."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from app.ingestion.ledger import Denied
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import stable_pipeline as sp
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import GitHub
from tests.test_ingestion_window_demonstration_owner import registration

ROOT=Path(__file__).resolve().parents[1]


class Scope:
    """The production contract of OperationalMemory: snapshot() only while enforcing, close() once."""
    source=None
    def __init__(self,fail_close=False):self.closed=False;self.fail_close=fail_close;self.events=[]
    def snapshot(self):
        if self.closed:raise AssertionError('snapshot after close')
        return {}
    def close(self):
        if self.fail_close:raise RuntimeError('scope close failed')
        self.closed=True;self.events.append('closed')
        return dict(owned_groups_removed=True,owned_survivors=0,memory=dict(aggregate=dict(events=dict(oom_kill=0))))


def runner(tmp_path,scope,mode='window'):
    r=orr.Runner(registration(mode),Journal(Path(tmp_path)/'j'),lambda:None,source_reader=None,github=None,url_factory=None,memory=scope)
    calls=[]
    def fake_gh(command,**kw):
        calls.append(command);return subprocess.CompletedProcess(command,0,stdout=b'{}',stderr=b'')
    r.github=GitHub(r.emit,lambda:r.check(),runner=fake_gh,bound=orr.PIPELINE_GITHUB_BOUND)
    return r,calls


def result_for(r,**over):
    components=r.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',memory_close=False)
    return dict(status='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED',authority_invalidation='ACKNOWLEDGED_READBACK',cleanup=components['overall'],closure_components=components,
                access='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',screening='COMPLETE',application_writes=0,stage4='OPEN',pipeline_retry='HELD',**over)


def test_the_original_ordering_is_denied_by_the_unchanged_guard_which_is_the_20_october_defect(tmp_path):
    scope=Scope();r,calls=runner(tmp_path,scope)
    r.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED')      # what the owner used to do first: close the scope
    assert scope.closed
    with pytest.raises(Denied,match='RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS'):r.github.call('GET','user')
    assert calls==[]      # the guard is NOT weakened: it still denies every GitHub call once the scope is gone


def test_publication_is_made_inside_the_enforced_scope_and_reserve_then_the_scope_closes_then_the_guard_denies(tmp_path):
    scope=Scope();r,calls=runner(tmp_path,scope);seen={}
    base=result_for(r)
    assert base['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE' and base['closure_components']['process']['memory']=='ENFORCED_PENDING_CLOSURE' and not scope.closed      # the pending record: the scope still enforces
    def publish(pending):
        seen.update(scope_closed=scope.closed,reserve=r.github.reserve is not None,stage=pending['closure_stage'],before=len(calls))
        for _ in range(6):r.github.call('GET','repos/x')      # the real GitHub object, real guard, real reserve
    sealed=r.seal_owner_result(base,publish)
    assert seen==dict(scope_closed=False,reserve=True,stage='PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE',before=0) and len(calls)==6 and scope.closed
    assert sealed['closure_stage']=='FINAL_AFTER_PUBLICATION' and sealed['publication']=='PUBLISHED' and sealed['cleanup']=='CLOSED' and sealed['closure_components']['process']['status']=='CLOSED'
    assert sealed['status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED' and sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK'
    assert sealed['published_status']==base['status'] and sealed['published_cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'      # provisional versus final, both stated
    with pytest.raises(Denied,match='RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS'):r.github.call('GET','user')
    assert len(calls)==6 and orr.exit_status(sealed)==0
    on_disk=json.loads((Path(tmp_path)/'j'/'final-result.json').read_bytes())
    assert on_disk['closure_stage']=='FINAL_AFTER_PUBLICATION' and on_disk==json.loads(json.dumps(sealed))      # the definitive local record is written AFTER closure
    events=[json.loads(l)['event'] for l in (Path(tmp_path)/'j'/'events.jsonl').read_text().splitlines()]
    assert events[-1]=='owner_final_closure'


def test_a_publication_failure_after_confirmed_invalidation_is_reported_accurately_and_never_undoes_the_invalidation(tmp_path):
    scope=Scope();r,calls=runner(tmp_path,scope)
    from verification.ingestion_storage.operational_publication import Uncertain
    def publish(pending):raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')
    sealed=r.seal_owner_result(result_for(r),publish)
    assert sealed['publication_reason']=='GITHUB_RESPONSE_UNCERTAIN'
    assert sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK' and sealed['access']=='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED'      # confirmed invalidation preserved
    assert sealed['publication'].startswith('UNCERTAIN_') and sealed['publication_reason'] and sealed['cleanup']=='CLOSED' and scope.closed      # the scope is still closed
    assert sealed['status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED_PUBLICATION_UNCERTAIN' and sealed['published_status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED'
    assert orr.exit_status(sealed)==1      # never a quiet success


def test_a_publication_that_exceeds_its_reserve_is_stopped_by_the_reserve_not_the_overall_bound(tmp_path):
    scope=Scope();r,calls=runner(tmp_path,scope)
    def publish(pending):
        for _ in range(40):r.github.call('GET','repos/x')
    sealed=r.seal_owner_result(result_for(r),publish)
    assert len(calls)==orr.OWNER_PUBLICATION_RESERVE['requests'] and sealed['publication'].startswith('UNCERTAIN_') and sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK' and sealed['cleanup']=='CLOSED'
    assert orr.OWNER_PUBLICATION_RESERVE==dict(requests=sp.PUBLICATION_RESERVE_REQUESTS,seconds=sp.PUBLICATION_RESERVE_SECONDS)      # the same reserve the hosted job uses


def test_a_closure_failure_is_reported_as_uncertain_cleanup_while_the_publication_and_invalidation_stay_as_they_were(tmp_path):
    scope=Scope(fail_close=True);r,calls=runner(tmp_path,scope)
    sealed=r.seal_owner_result(result_for(r),lambda pending:r.github.call('GET','repos/x'))
    assert sealed['publication']=='PUBLISHED' and sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK'      # what was true stays true
    assert sealed['cleanup']=='UNCERTAIN' and sealed['status']=='STOP_RECONCILE_NO_RETRY' and orr.exit_status(sealed)==1


def test_both_owner_tails_use_the_sealing_method_and_none_publishes_after_closing_the_scope():
    text=(ROOT/'verification/ingestion_storage/operational_runner.py').read_text()
    assert text.count('return self.seal_owner_result(result,lambda pending:self.publish_owner(pending))')==2      # pipeline (stable, capture, window) and the form probe
    assert text.count("self.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED',memory_close=False)")==2
    assert "self.closure('AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED')\n" not in text      # no tail closes the scope before publishing
    body=text[text.index('    def publish_owner'):text.index('    def seal_owner_result')]
    assert body.count('github.publish')==1      # the only owner publication is the one inside the reserve


def test_the_exit_status_distinguishes_closed_published_stopped_and_unpublished():
    assert orr.exit_status(dict(cleanup='CLOSED',status='X'))==0 and orr.exit_status(dict(cleanup='CLOSED',status='X',publication='PUBLISHED'))==0
    assert orr.exit_status(dict(cleanup='CLOSED',status='STOP_RECONCILE_NO_RETRY'))==1 and orr.exit_status(dict(cleanup='UNCERTAIN',status='X'))==1 and orr.exit_status(dict(cleanup='CLOSED',status='X',publication='UNCERTAIN_ValueError'))==1


def test_an_unclassified_publication_exception_exports_only_a_fixed_literal(tmp_path):
    scope=Scope();r,calls=runner(tmp_path,scope)
    def publish(pending):raise RuntimeError('secret-looking text must never be exported')
    sealed=r.seal_owner_result(result_for(r),publish)
    assert sealed['publication_reason']=='UNCLASSIFIED_PUBLICATION_FAILURE' and 'secret-looking' not in json.dumps(sealed) and sealed['publication']=='UNCERTAIN_RuntimeError'


def test_a_failed_github_mutation_is_a_publication_fact_not_a_closure_fault(tmp_path):
    from verification.ingestion_storage.operational_publication import Uncertain
    scope=Scope();r,calls=runner(tmp_path,scope)
    def publish(pending):
        r.github.mutation_uncertain=True      # what publish() does when a POST/PATCH to the evidence ref fails
        raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')
    sealed=r.seal_owner_result(result_for(r),publish)
    assert scope.closed and sealed['cleanup']=='CLOSED' and sealed['closure_components']['overall']=='CLOSED'      # the scope, processes, sockets and connections closed cleanly
    assert sealed['publication']=='UNCERTAIN_Uncertain' and sealed['publication_reason']=='GITHUB_RESPONSE_UNCERTAIN' and sealed['publication_mutation_uncertain'] is True
    assert sealed['status']=='STABLE_PIPELINE_AUTHORITY_COMPLETED_AUTHORITY_INVALIDATED_PUBLICATION_UNCERTAIN' and sealed['authority_invalidation']=='ACKNOWLEDGED_READBACK' and orr.exit_status(sealed)==1


def test_the_saved_record_binds_the_audit_it_closes(tmp_path):
    import hashlib
    scope=Scope();r,calls=runner(tmp_path,scope)
    sealed=r.seal_owner_result(result_for(r),lambda pending:r.github.call('GET','repos/x'))
    events=(Path(tmp_path)/'j'/'events.jsonl').read_bytes()
    assert sealed['audit_sha256']==hashlib.sha256(events).hexdigest() and sealed['audit_chain_head']==r.journal.head
    assert json.loads((Path(tmp_path)/'j'/'final-result.json').read_bytes())['audit_sha256']==sealed['audit_sha256']
