"""Closed target and pre-source refusals, synthetic records only."""
from copy import deepcopy
from datetime import date
from dataclasses import replace
from unittest.mock import patch
import pytest
from app.ingestion.ledger import Denied,DEFAULT_LIMITS,digest
from tests.e2e_connection_support import idox_audit,idox_contract,entry,SCHEME,outer
from verification.ingestion_storage import idox_target as t
from verification.ingestion_storage.scope_binding import binding_for,check_detail_target,check_contract,check_capture
from verification.ingestion_storage.operational_source import read

START,END=date(2026,11,9),date(2026,11,15)
COUNCILS=sorted(t.COUNCILS)

def record(c):return idox_contract(c,START,END).project(idox_audit(c,[entry('SYNTHETIC/1',SCHEME)],START,END),outer(),DEFAULT_LIMITS)['records'][0]

@pytest.mark.parametrize('c',COUNCILS)
def test_closed_bindings_targets_and_default_scope(c):
 b=binding_for(c);r=record(c);target=t.derive(c,r)
 assert b.semantics==('VALIDATED' if c=='stockport' else 'RECEIVED')
 assert target['verification_scope']=='COUPLED' and target['record_sha256']==digest(r)
 assert check_detail_target(b,r,target)==target and t.validate(target)==target
 assert check_contract(b,idox_contract(c,START,END),START.isoformat(),END.isoformat())['semantics']==b.semantics
 with pytest.raises(Denied):check_contract(b,replace(idox_contract(c,START,END),partial_observation=True),START.isoformat(),END.isoformat())

@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('field,value',[('council','tameside'),('reference','OTHER'),('source_identifier','OTHER'),('source_url','https://example.org/'),('case','OTHER'),('verification_scope','INITIAL_STATUS_ONLY'),('record_sha256','f'*64),('extra',True)])
def test_every_target_substitution_refuses_before_source(c,field,value,tmp_path):
 r=record(c);target=t.derive(c,r);target[field]=value
 with pytest.raises(Denied):check_detail_target(binding_for(c),r,target)
 with patch('verification.ingestion_storage.operational_source.supervise',side_effect=AssertionError('source started')):
  with pytest.raises(Denied):read('detail',target,root=tmp_path/'source',closed_target=True)

@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('field',('qualification_sha256','date_semantics','outer_supervisor','kind'))
def test_capture_qualification_supervisor_and_complete_kind(c,field):
 contract=idox_contract(c,START,END);rc=contract.project(idox_audit(c,[entry('SYNTHETIC/1',SCHEME)],START,END),outer(),DEFAULT_LIMITS)
 assert check_capture(binding_for(c),contract,rc)==rc
 rc[field]=None
 with pytest.raises(Denied):check_capture(binding_for(c),contract,rc)

@pytest.mark.parametrize('c',COUNCILS)
@pytest.mark.parametrize('field,value',[('base_url','https://example.org/online-applications'),('date_field_mode','other'),('doc_system','arcus')])
def test_reviewed_council_configuration_cannot_drift(c,field,value):
 from app.config import get_council
 cfg=replace(get_council(c),**{field:value})
 with patch('app.config.get_council',return_value=cfg):
  with pytest.raises(Denied,match='SCOPE_BINDING_CONFIGURATION_MISMATCH'):binding_for(c)

@pytest.mark.parametrize('c',COUNCILS)
def test_missing_worker_selection_fields_cannot_downgrade_to_legacy(c,tmp_path):
 target=t.derive(c,record(c));target.pop('target_sha256');target['case']='legacy'
 with patch('verification.ingestion_storage.operational_source.supervise',side_effect=AssertionError('source started')):
  with pytest.raises(Denied):read('detail',target,root=tmp_path/'source',closed_target=True)

@pytest.mark.parametrize('field,value',[('case','legacy'),('target_sha256',None),('verification_scope','INITIAL_STATUS_ONLY'),('source_url','https://example.org/')])
def test_private_worker_independently_refuses_before_parser(field,value,tmp_path,monkeypatch):
 import json,sys,os
 from verification.ingestion_storage import operational_source
 target=t.derive('bury',record('bury'));target[field]=value
 plan=tmp_path/'plan.json';plan.write_text(json.dumps(target))
 with patch.dict(os.environ,{'INGESTION_SOURCE_PRIVATE':'ONCE'},clear=True),patch.object(sys,'argv',['source','--worker','detail','--closed-idox-target','--plan',str(plan),'--output',str(tmp_path/'out')]),patch('verification.discovery.material_qualification.idox_worker',side_effect=AssertionError('parser started')):
  with pytest.raises(Denied):operational_source.main()
 assert not (tmp_path/'out').exists()
