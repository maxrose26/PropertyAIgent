"""Small concrete positive commands under explicit synthetic operator fixture."""
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base,Council,Site

@pytest.fixture
def database():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Council(code='test',name='Fixture',base_url='https://example.invalid',doc_system='idox',date_field_mode='received'))
        session.add(Site(id=1,council_code='test',canonical_address='Synthetic',display_address='Synthetic'));session.commit()
        yield session
from app.security import access

class Client:
    def __init__(self,results):self.results=iter(results);self.calls=[];self.responses=self
    def create(self,**kwargs):self.calls.append(kwargs);return SimpleNamespace(output_text=json.dumps(next(self.results)),usage=None)


def test_search_and_narrative_positive():
    from app.search.query_parser import parse_query
    from app.reporting.pdf_report import generate_narrative,compute_aggregate_stats
    from verification.test_stage1_pdf_compatibility import frame
    client=Client([{'min_total_units':10}]);assert parse_query(client,'ten homes').min_total_units==10 and len(client.calls)==1
    client=Client([dict(executive_summary='Synthetic summary',buying_opportunities_and_risks='Synthetic unknowns')])
    assert generate_narrative(client,compute_aggregate_stats(frame()))['EXECUTIVE SUMMARY']=='Synthetic summary'
    assert len(client.calls)==1


def test_contacts_enrichment_and_committed_commands(database,monkeypatch):
    from app.enrichment import contact_pipeline as module
    from app.db.models import Application,ApplicationCompany,Contact,Settings,Site
    from app.services.ui_commands import add_credits,set_site_exclusion,save_contacts
    calls=[]
    monkeypatch.setattr(module.companies_house,'best_match',lambda key,name:calls.append(name))
    result=module.enrich_company('Synthetic Company','synthetic',None,None,None)
    assert calls==['Synthetic Company'] and result.company_name_raw=='Synthetic Company'
    company=module.upsert_company_from_enrichment(database,'Synthetic Company',result)
    database.flush();application=Application(council_code='test',reference='SYN/1',site_id=1);database.add(application);database.flush()
    database.add(ApplicationCompany(application_id=application.id,company_id=company.id,role='applicant'))
    contact=Contact(company_id=company.id,full_name='Synthetic Person',source='synthetic');database.add(contact);database.commit()
    save_contacts(database,1,company.id,{contact.id:('contacted',True)})
    add_credits(database,7);set_site_exclusion(database,1,True,'synthetic')
    database.expire_all();assert database.get(Contact,contact.id).suppressed
    assert database.get(Settings,1).credits_remaining==7 and database.get(Site,1).excluded


def test_matching_uses_authenticated_provenance(database):
    from app.db.models import LocalPlan,LocalPlanSite
    from app.policy.site_match_review import confirm_site_match,reject_site_match
    plan=LocalPlan(council_code='test',plan_name='Fixture');database.add(plan);database.flush()
    allocation=LocalPlanSite(council_code='test',local_plan_id=plan.id,site_name='Fixture',plan_name='Fixture',plan_status='draft',matched_site_id=1)
    database.add(allocation);database.commit()
    confirm_site_match(database,allocation,'forged-client-name','Verified fixture')
    assert allocation.review_status=='confirmed' and allocation.confirmed_by==access.actor_label() and allocation.confirmed_by!='forged-client-name'
    reject_site_match(database,allocation,'forged-client-name','Not a match')
    assert allocation.matched_site_id is None and allocation.review_status=='rejected' and allocation.confirmed_by==access.actor_label()


def test_extraction_three_existing_provider_calls_and_summary(monkeypatch):
    from app.db.models import Application,Document,Site
    from app.extraction import run_extraction as module
    from app.reporting.scheme_summary import generate_scheme_summary
    from tests.test_evidence_driven_intelligence_refresh import _merged
    application=Application(council_code='test',reference='SYN/1',address='Synthetic',proposal='20 homes',estimated_unit_count=20)
    application.documents=[Document(doc_type='planning_statement',document_name='Statement',text_extracted=True,extracted_text='A development of 20 homes.')]
    client=Client([{}, {}, {}]);monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    result=module.run_extraction_for_application(client,application)
    assert isinstance(result,dict) and len(client.calls)==3
    client=Client([{'summary':'Synthetic evidence summary'}]);site=Site(council_code='test',canonical_address='Synthetic',display_address='Synthetic')
    assert generate_scheme_summary(client,site,[application],_merged(),{'status':'unknown','build_status':'unknown'},[])=='Synthetic evidence summary'
    assert len(client.calls)==1
