"""Existing Stage2 extraction/persistence, synthetic documents and fake provider.

No new extractor and no model/document calls. Raw stored scalars are NOT proof
of consented whole-site totals, additional capacity or complete scheme extraction.
"""
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Application,Document,SchemeIntelligence,Site
from app.pipeline.run_weekly import stage_extraction
from app.reporting.scheme_reconciliation import build_operative_planning_facts,count_assessment_for_facts,scoped_count_assessment
from tests.test_ai_processing_reliability import COUNCILS


class RetainedProvider:
 def __init__(self,total):self.total=total;self.calls=[];self.responses=self
 def create(self,**kw):
  name=kw['text']['format']['name'];self.calls.append(name)
  d={'total_units_context':self.total,'affordable_data_status':'unknown'} if name=='affordable_classifier' else {}
  # Name is schema-dependent; only the third existing pass supplies totals.
  if len(self.calls)==3:d={'total_units_context':self.total,'affordable_data_status':'unknown'}
  return SimpleNamespace(output_text=json.dumps(d))


@pytest.fixture()
def unit_paid_context(tmp_path,monkeypatch):
 from verification import stage1_test_context as ctx
 monkeypatch.setattr(ctx,'PAID_ACTIONS',[*ctx.PAID_ACTIONS,'pipeline.extract'])
 root=tmp_path/'unit-authority';root.mkdir()
 with ctx.synthetic_context(root):yield


def test_existing_extractor_persistence_and_count_semantics(session,monkeypatch,record_property,unit_paid_context):
 from app.extraction import prompts
 monkeypatch.setattr(prompts,'SLEEP_BETWEEN_CALLS',0)
 rows=[];apps={}
 cases=[('BASE','Erection of 100 dwellings',100,'Granted',None),
        ('PROPOSED','Section 73 variation of BASE to provide 120 dwellings',120,None,None),
        ('CAP','Outline development of up to 200 dwellings',200,'Granted',None),
        ('PHASE','Reserved matters for 30 dwellings in Phase 2',30,'Granted','2'),
        ('ADDITIONAL','An additional 20 dwellings pursuant to BASE',20,None,None),
        ('UNKNOWN','Residential development; number of dwellings to be confirmed',None,'Granted',None)]
 for index,(ref,proposal,total,decision,phase) in enumerate(cases):
  a=Application(council_code='testcouncil',reference=ref,proposal=proposal,decision=decision,status='Decided' if decision else 'Awaiting decision',decision_issued_date='2026-01-01' if decision else None,application_category='variation_or_amendment' if ref=='PROPOSED' else 'primary_residential')
  session.add(a);session.flush();session.add(Document(application_id=a.id,doc_type='planning_statement',document_name='Synthetic retained evidence',text_extracted=True,extracted_text=proposal));session.commit()
  provider=RetainedProvider(total);result=stage_extraction(session,provider,COUNCILS['testcouncil'],limit=1)
  assert result.succeeded==1 and len(provider.calls)==3
  with Session(session.bind) as read:
   persisted=read.scalar(select(SchemeIntelligence).where(SchemeIntelligence.application_id==a.id))
   assert persisted is not None
   rows.append(dict(reference=ref,proposal=proposal,stored_total=persisted.total_units_final,provider_calls=len(provider.calls),meaning='RAW_EXISTING_EXTRACTION_FIELD_NOT_VERIFIED_WHOLE_SCHEME'))
  session.refresh(a);apps[ref]=a
 # Proposed amendment cannot replace a granted base total merely by extraction.
 facts=build_operative_planning_facts([apps['BASE'],apps['PROPOSED']]);consented=count_assessment_for_facts(facts)
 assert consented.value==100 and any(p.proposed_units.value==120 for p in facts.active_positions)
 # Phase remains its own source scope; never added to a parent total.
 phase=scoped_count_assessment([apps['PHASE']],'phase','2');assert phase.value==30
 # Unknown has a real persisted NULL, not an invented zero.
 assert apps['UNKNOWN'].scheme_intelligence.total_units_final is None
 # The legacy scalar for 'additional' is an extraction candidate, not a delta
 # or a new consented total. No confirmed parent link is created.
 assert apps['ADDITIONAL'].site_id is None
 # Preserve conflicting granted primary totals using existing Stage2 assessment.
 other=Application(council_code='testcouncil',reference='CONFLICT',proposal='Erection of 180 dwellings',decision='Granted',status='Decided',decision_issued_date='2026-01-01')
 other.scheme_intelligence=SchemeIntelligence(total_units_final=180);session.add(other);session.commit()
 conflict=count_assessment_for_facts(build_operative_planning_facts([apps['BASE'],other]));assert conflict.value is None and conflict.resolution=='material_conflict'
 cap=count_assessment_for_facts(build_operative_planning_facts([apps['CAP']]))
 record_property('unit_acceptance_cases',json.dumps(rows,sort_keys=True))
 record_property('up_to_assessment',json.dumps(dict(value=cap.value,precision=cap.precision,resolution=cap.resolution),sort_keys=True))
