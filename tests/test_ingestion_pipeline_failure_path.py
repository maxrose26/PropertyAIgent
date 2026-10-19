"""The owner's failure path in pipeline mode: ending the authority is database-only and is attempted whatever the GitHub state is."""
import time
from types import SimpleNamespace
import psycopg
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import Uncertain
from verification.ingestion_storage.tls_trust import owned_resources


def pipeline_runner(tmp_path,*,mutation_uncertain,invalidation='ACKNOWLEDGED_READBACK'):
    r=orr.Runner.__new__(orr.Runner)
    r.journal=Journal(tmp_path/'j');r.emit=r.journal.emit;r.baseline=owned_resources();r.receipts={};r.closed=True;r.memory=None;r.pipeline_mode=True
    r.started=time.monotonic();r.phase='admin';r.phase_started=r.started;r.admin_seconds=0;r.runtime_seconds=0;r.source_attempts=0;r.capture=None;r.source_resources={'status':'NOT_STARTED'};r.operation_phase='PIPELINE_SCREENING_AUTHORITY'
    calls=[]
    def invalidate():
        calls.append(r.owner.diagnostic_mode);return invalidation
    r.owner=SimpleNamespace(authorities=['A_CAPTURE','A_SCREEN'],urls={},effect_uncertain=False,diagnostic_mode=False,invalidation='REQUIRED',invalidate_authorities=invalidate,diagnostics=lambda:{'roles':[]},
                            accounting=lambda:dict(connections_opened=1,connections_closed=1,failed_native_connections=0,failed_native_finished=0,uncertain_effect=False))
    r.github=SimpleNamespace(mutation_uncertain=mutation_uncertain,requests=0,names=lambda:['DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'])
    return r,calls


def test_an_uncertain_github_publication_never_prevents_the_revocation(tmp_path):
    r,calls=pipeline_runner(tmp_path,mutation_uncertain=True)
    result=r.failed(Uncertain('SOMETHING_UNCERTAIN'))
    assert calls==[True]      # attempted exactly once, on the reserved failure allowance
    assert result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and result['access']=='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED'
    assert result['cleanup']=='UNCERTAIN'      # the run itself stays uncertain: a GitHub mutation is unresolved and the owner reconciles it


def test_a_revocation_that_stays_unreconciled_is_reported_as_such(tmp_path):
    r,calls=pipeline_runner(tmp_path,mutation_uncertain=False,invalidation='UNCERTAIN_RECONCILE')
    result=r.failed(psycopg.OperationalError('x'))
    assert calls==[True] and result['authority_invalidation']=='UNCERTAIN_RECONCILE' and result['access']!='AUTHORITY_INVALIDATED_STANDING_CREDENTIALS_UNCHANGED' and result['cleanup']=='UNCERTAIN'


def test_the_non_pipeline_modes_keep_their_existing_refusal_after_an_uncertain_github_mutation(tmp_path):
    r,calls=pipeline_runner(tmp_path,mutation_uncertain=True);r.pipeline_mode=False
    r.owner.invalidate_failure=lambda:(_ for _ in ()).throw(AssertionError('not called'))
    result=r.failed(Uncertain('SOMETHING_UNCERTAIN'))
    assert calls==[] and result['authority_invalidation']=='UNCERTAIN_RECONCILE'      # unchanged behaviour of the accepted modes
