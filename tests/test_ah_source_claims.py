"""Disposable-only provenance acceptance. No app bootstrap or live credentials."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import create_engine, select, text, inspect, event
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Base, Council, Application, Document
from app.db.ah_claim_schema import claims, events, migrate_local, verify_schema, require_local
from app.policy.ah_claim_store import import_claim, review_claim, preview, ClaimError, text_hash
from app.policy.ah_claim_selection import select_claims, for_applications
from tests.test_ah_qualified_discovery import record


@pytest.fixture
def db(tmp_path):
    engine=create_engine('sqlite:///' + str(tmp_path/'claims.sqlite'))
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as s:
        s.add(Council(code='testcouncil',name='Test',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
        s.commit()
        site,app,_=record(s)
        app.scheme_intelligence.development_type='mixed_retirement_and_market_housing'
        doc=Document(application_id=app.id,document_name='Synthetic evidence',source_url='https://example.invalid/doc1',
            extracted_text='Approximately 72 affordable retirement apartments in the retirement component. Scheme total 82 homes.')
        s.add(doc); s.commit()
        before=set(inspect(engine).get_table_names())
        migrate_local(engine)
        assert set(inspect(engine).get_table_names())-before=={'ah_source_claims','ah_claim_events'}
        yield engine,s,site,app,doc
    engine.dispose()


def manifest(db, **changes):
    _,_,site,app,doc=db
    data=dict(application_id=app.id,site_id=site.id,scheme_application_id=app.id,
        scope_kind='component',scope_key='RETIREMENT',scope_label='Retirement apartments',scope_basis='Named retirement component in source',
        metric='affordable_count',qualifier='approximate',value=72,document_id=doc.id,
        document_url_snapshot=doc.source_url,document_title_snapshot=doc.document_name,
        document_date='2026-01-01',passage_text='Approximately 72 affordable retirement apartments',passage_locator='page 1 paragraph 1',
        extracted_text_hash=text_hash(doc.extracted_text),origin_kind='reviewed_import',origin_reference='fixture:1',
        created_by='operator:test',import_key='fixture:1',planning_stage='proposed')
    data.update(changes)
    return data


def add(db, **changes):
    return import_claim(db[0],manifest(db,**changes),apply=True)['id']


def request(db, claimid, action='ACCEPT', **changes):
    roots=changes.pop('roots',[db[3].id])
    p=preview(db[0],roots)
    data=dict(claim_id=claimid,action=action,reason='Operator checked captured source and scope; synthetic test only',
        request_key=f'{claimid}:{action}:{p["heads"][str(claimid)]}',expected_token=p['token'],expected_heads=p['heads'],
        source_checked=action=='ACCEPT',scope_checked=action=='ACCEPT')
    data.update(changes)
    return data


def review(db, claimid, action='ACCEPT', **changes):
    return review_claim(db[0],request(db,claimid,action,**changes),reviewer='operator:reviewer',apply=True)


def selected(db):
    with db[0].connect() as c:
        return select_claims(c,[db[3].id])


def document(db, passage):
    doc=Document(application_id=db[3].id,document_name='Synthetic source fixture',extracted_text=passage)
    db[1].add(doc); db[1].commit()
    return doc


def test_narrow_migration_and_retained_rollback(db, monkeypatch):
    engine,s,site,app,doc=db
    assert {'ah_source_claims','ah_claim_events'}.isdisjoint(Base.metadata.tables)
    assert migrate_local(engine) is False
    assert app.scheme_intelligence.affordable_units_final==72
    cid=add(db); review(db,cid)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    assert for_applications([app]).count.qualified
    monkeypatch.delenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS')
    assert for_applications([app]) is None
    with engine.connect() as c:
        assert len(c.execute(select(claims)).all())==1
        assert len(c.execute(select(events)).all())==1


@pytest.mark.parametrize('table', ['ah_source_claims','ah_claim_events'])
@pytest.mark.parametrize('operation', ['UPDATE','DELETE'])
def test_append_only_db_protections(db,table,operation):
    cid=add(db); review(db,cid)
    sql=f'UPDATE {table} SET id=id' if operation=='UPDATE' else f'DELETE FROM {table}'
    with pytest.raises(DBAPIError,match='append-only'):
        with db[0].begin() as c:
            c.execute(text(sql))


def test_missing_or_partial_schema_fails(tmp_path):
    engine=create_engine('sqlite:///' + str(tmp_path/'partial.sqlite'))
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE ah_source_claims (id INTEGER PRIMARY KEY)'))
    with pytest.raises(ValueError,match='incompatible'):
        migrate_local(engine)
    assert not inspect(engine).has_table('ah_claim_events')


def test_missing_protection_fails(db):
    with db[0].begin() as c:
        c.execute(text('DROP TRIGGER ah_source_claims_deny_update'))
    with pytest.raises(ValueError,match='protection'):
        migrate_local(db[0])


def test_duplicate_keys_and_changed_content(db):
    data=manifest(db)
    assert import_claim(db[0],data)['would_insert']
    assert selected(db) is None
    result=import_claim(db[0],data,apply=True)
    assert import_claim(db[0],data,apply=True)['id']==result['id']
    with pytest.raises(ClaimError,match='import_key_content_changed'):
        import_claim(db[0],dict(data,value=73),apply=True)
    with pytest.raises(ClaimError,match='duplicate_payload_use_original_key') as error:
        import_claim(db[0],dict(data,import_key='other',origin_reference='other'),apply=True)
    assert error.value.details=={'id':result['id'],'import_key':data['import_key']}
    with db[0].connect() as c:
        assert len(c.execute(select(claims)).all())==1


@pytest.mark.parametrize('changes', [dict(value=-1),dict(value='NaN'),dict(value='Infinity'),dict(value='1.1234567'),
    dict(value=1,lower_bound=2),dict(qualifier='range',value=None,lower_bound=80,upper_bound=60),
    dict(qualifier='unknown',value=None),dict(scope_key='WHOLE_SCHEME'),dict(metric='percentage'),
    dict(document_date=None),dict(passage_text=''),dict(passage_start=0,passage_end=4),dict(document_id=99999)])
def test_invalid_import_rejected_without_rows(db,changes):
    with pytest.raises((ClaimError,ValueError)):
        add(db,**changes)
    assert selected(db) is None


def test_independent_documents_corroborate(db):
    a=add(db); review(db,a)
    _,s,_,app,doc=db
    second=Document(application_id=app.id,document_name='Independent document',extracted_text=doc.extracted_text)
    s.add(second); s.commit()
    b=add(db,document_id=second.id,import_key='second',origin_reference='second')
    review(db,b)
    result=selected(db)
    assert result.count.value==72 and result.count.state=='estimated'
    assert len(result.source_claims)==2
    assert not result.alternatives
    assert 'Equivalent checked sources' in result.label()


def test_concurrent_reviews_reject_stale_head(db):
    cid=add(db)
    a=request(db,cid)
    b=dict(a,action='REJECT',source_checked=False,scope_checked=False,request_key='other-review')
    barrier=Barrier(2)
    def run(r):
        barrier.wait()
        try:
            return review_claim(db[0],r,reviewer='operator:reviewer',apply=True)
        except ClaimError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(run,[a,b]))
    assert results.count('stale_review_preview')==1
    with db[0].connect() as c:
        assert len(c.execute(select(events)).all())==1


def test_concurrent_duplicate_imports_one_row(db):
    barrier=Barrier(2)
    def run(_):
        barrier.wait()
        return import_claim(db[0],manifest(db),apply=True)
    with ThreadPoolExecutor(2) as pool:
        result=list(pool.map(run,[1,2]))
    assert result[0]['id']==result[1]['id']
    assert sorted(x['replayed'] for x in result)==[False,True]


def test_review_replay_and_import_invalidates_preview(db):
    a=add(db)
    old=request(db,a)
    add(db,value=73,import_key='new',origin_reference='new')
    with pytest.raises(ClaimError,match='stale_review_preview'):
        review_claim(db[0],old,reviewer='operator:reviewer',apply=True)
    new=request(db,a)
    result=review_claim(db[0],new,reviewer='operator:reviewer',apply=True)
    assert review_claim(db[0],new,reviewer='operator:reviewer',apply=True)['id']==result['id']
    with pytest.raises(ClaimError,match='review_key_content_changed'):
        review_claim(db[0],dict(new,reason='different'),reviewer='operator:reviewer',apply=True)


def test_scope_correction_retains_unrelated_evidence(db):
    wrong=add(db,scope_kind='whole_scheme',scope_key='WHOLE_SCHEME',scope_label='Whole scheme')
    review(db,wrong)
    corrected=add(db,import_key='corrected',origin_reference='corrected')
    review(db,corrected)
    review(db,wrong,'CORRECT',related_claim_id=corrected)
    r=selected(db)
    assert r.count.scope_type=='component' and r.count.value==72
    assert next(c for c in r.source_claims if c['id']==wrong)['historical']
    _,s,_,app,doc=db
    other=Document(application_id=app.id,extracted_text='Whole scheme has 60 affordable homes.')
    s.add(other); s.commit()
    unrelated=add(db,document_id=other.id,extracted_text_hash=None,value=60,qualifier='exact',
        scope_kind='whole_scheme',scope_key='WHOLE_SCHEME',scope_label='Whole scheme',
        passage_text=other.extracted_text,import_key='other',origin_reference='other')
    review(db,unrelated)
    assert selected(db).count.state=='conflicting'
    with pytest.raises(ClaimError,match='same_source_assertion'):
        review(db,unrelated,'CORRECT',related_claim_id=corrected)


def test_unclear_scope_requires_new_claim(db):
    old=add(db,scope_kind='unclear',scope_key='UNRESOLVED',scope_label='Unclear')
    with pytest.raises(ClaimError,match='scope_requires_corrected_claim'):
        review(db,old)
    new=add(db,import_key='resolved'); review(db,new)
    review(db,old,'CORRECT',related_claim_id=new)
    assert selected(db).count.qualified


def test_stage_alone_and_date_do_not_resolve_conflicts(db):
    a=add(db); review(db,a)
    later=document(db,'Synthetic later source: 40 affordable homes in the retirement component. The stated provision is legally secured.')
    b=add(db,value=40,import_key='later',planning_stage='legally_secured',document_date='2026-09-30',
        document_id=later.id,passage_text='40 affordable homes in the retirement component',extracted_text_hash=text_hash(later.extracted_text),
        stage_document_id=later.id,stage_passage_text='The stated provision is legally secured.',stage_passage_locator='page 1')
    review(db,b)
    assert selected(db).count.state=='conflicting'
    assert 'unverified' in selected(db).alternatives[1].stage
    review(db,b,stage_checked=True)
    assert selected(db).count.state=='conflicting'
    review(db,a,'SUPERSEDE',related_claim_id=b)
    assert selected(db).count.value==40
    assert selected(db).count.stage=='legally_secured'
    review(db,b,'REJECT')
    assert selected(db).search(minimum=50)=='investigate'
    assert next(c for c in selected(db).source_claims if c['id']==a)['historical']


def test_reversal_and_cycle(db):
    a=add(db); review(db,a)
    b=add(db,value=73,import_key='corrected'); review(db,b)
    link=review(db,a,'CORRECT',related_claim_id=b)
    with pytest.raises(ClaimError,match='replacement_cycle'):
        review(db,b,'CORRECT',related_claim_id=a)
    review(db,a,'REVERSE_LINK',reversed_event_id=link['id'])
    assert selected(db).count.state=='conflicting'
    with pytest.raises(ClaimError,match='already_reversed'):
        review(db,a,'REVERSE_LINK',reversed_event_id=link['id'])


def test_unknown_legacy_zero_and_source_zero(db,monkeypatch):
    _,s,_,app,_=db
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    from app.policy.buyer_matching import build_planning_delivery_matching_facts
    app.scheme_intelligence.affordable_units_final=0; s.commit()
    assert build_planning_delivery_matching_facts(app.scheme_intelligence).affordable_assessment.search(maximum=50)=='unknown'
    source=document(db,'Synthetic whole scheme evidence: zero affordable homes.')
    zero=add(db,value=0,qualifier='exact',scope_kind='whole_scheme',scope_key='WHOLE_SCHEME',scope_label='Whole scheme',
        document_id=source.id,passage_text=source.extracted_text,extracted_text_hash=text_hash(source.extracted_text))
    assert selected(db).search(maximum=50)=='unknown'
    review(db,zero)
    assert selected(db).search(maximum=50)=='meets'
    assert selected(db).search(minimum=50)=='does_not_meet'


def test_component_zero_and_unknown_do_not_prove_maximum(db):
    source=document(db,'Synthetic evidence: zero affordable homes within the named retirement component.')
    zero=add(db,value=0,qualifier='exact',document_id=source.id,passage_text=source.extracted_text,extracted_text_hash=text_hash(source.extracted_text)); review(db,zero)
    assert selected(db).search(maximum=50)=='investigate'
    review(db,zero,'REJECT')
    source=document(db,'Synthetic evidence: affordable home count is not established.')
    unknown=add(db,qualifier='unknown',value=None,unknown_reason='Source does not establish count',import_key='unknown',
        document_id=source.id,passage_text=source.extracted_text,extracted_text_hash=text_hash(source.extracted_text))
    review(db,unknown)
    assert selected(db).search(maximum=50)=='unknown'


def test_enabled_reader_missing_schema_fails(session,monkeypatch):
    _,app,_=record(session)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    with pytest.raises(ValueError,match='schema missing'):
        for_applications([app])


def test_no_writes_on_read_and_specialist_exclusion(db,monkeypatch):
    a=add(db); review(db,a)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    engine,s,site,app,doc=db
    statements=[]
    def capture(conn,cursor,statement,parameters,ctx,many):
        statements.append(statement.strip().split()[0].upper())
    event.listen(engine,'before_cursor_execute',capture)
    try:
        from app.policy.buyer_matching import build_planning_delivery_matching_facts, assess_buyer_fit, NOT_SUITABLE
        from app.policy.buyer_profiles import NESTEN_HOMES
        assessment=for_applications([app])
        facts=build_planning_delivery_matching_facts(app.scheme_intelligence)
        fit=assess_buyer_fit(NESTEN_HOMES,facts)
        assert assessment.count.value==72
        assert fit.classification==NOT_SUITABLE
        assert not {'INSERT','UPDATE','DELETE','CREATE','ALTER','DROP'} & set(statements)
    finally:
        event.remove(engine,'before_cursor_execute',capture)


def test_same_selection_across_consumers_and_csv(db,monkeypatch):
    a=add(db); review(db,a)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    engine,s,site,app,doc=db
    from app.reporting.scheme_reconciliation import build_operative_planning_facts,resolve_operative_filter_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative,B2MatchingContext
    from app.reporting.affordable_housing_scope import select_affordable_position_for_scope
    from app.reporting.site_profile import _ah_position
    from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    facts=build_operative_planning_facts([app])
    filters=resolve_operative_filter_facts(facts)
    matching=build_planning_delivery_matching_facts_from_operative(facts,[app])
    position=select_affordable_position_for_scope(facts.affordable_housing)
    detail=_ah_position(position)
    packet=build_opportunity_intelligence_packet(s,SimpleNamespace(opportunity_id=f'planning_delivery:site:{site.id}',
        opportunity_type='planning_delivery',kind='site',entity_id=site.id,phase_code=None,matching_facts=matching),context=B2MatchingContext())
    cards=[{'params':{'site_id':str(site.id)}}]
    _attach_planning_delivery_matching_facts(s,cards)
    expected=filters.affordable_assessment.payload()
    assert expected['count']['value']==72
    assert matching.affordable_assessment.payload()==expected
    from app.policy.buyer_matching import build_planning_delivery_matching_facts
    assert build_planning_delivery_matching_facts(app.scheme_intelligence).affordable_assessment.payload()==expected
    assert detail['assessment']==expected
    assert packet.affordable_assessment.payload()==expected
    assert cards[0]['matching_facts'].affordable_assessment.payload()==expected
    import pandas as pd
    from io import StringIO
    exported=pd.DataFrame([filters.affordable_assessment.columns()]).to_csv(index=False)
    row=pd.read_csv(StringIO(exported)).iloc[0]
    assert row['AH Qualified'] and row['AH Scope']=='Retirement apartments'
    assert json.loads(row['AH Source Claims'])[0]['id']==a


def test_remote_write_boundary():
    engine=SimpleNamespace(dialect=SimpleNamespace(name='postgresql'),url=SimpleNamespace(host='remote.invalid'))
    with pytest.raises(ValueError,match='local database'):
        require_local(engine)


@pytest.mark.parametrize('table', ['ah_source_claims','ah_claim_events'])
def test_sqlite_replace_cannot_erase_history(db,table):
    cid=add(db); review(db,cid)
    with pytest.raises(DBAPIError,match='append-only'):
        with db[0].begin() as c:
            c.execute(text(f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'))


def test_database_rejects_invalid_quantity_shape(db):
    cid=add(db)
    with db[0].connect() as c:
        original=dict(c.execute(select(claims)).mappings().one())
    original.pop('id')
    original.update(import_key='direct-invalid',lower_bound=2)
    with pytest.raises(IntegrityError):
        with db[0].begin() as c:
            c.execute(claims.insert().values(**original))


def test_changed_document_invalidates_review_and_selection(db):
    a=add(db); review(db,a)
    p=request(db,a,'REJECT')
    db[4].extracted_text='Changed captured document text'
    db[1].commit()
    assert not selected(db).count.qualified
    with pytest.raises(ClaimError,match='stale_review_preview'):
        review_claim(db[0],p,reviewer='operator:reviewer',apply=True)


def test_review_source_check_is_not_stage_or_availability(db):
    a=add(db,planning_stage='legally_secured')
    with pytest.raises(ClaimError,match='stage_source_required'):
        review(db,a,stage_checked=True)
    review(db,a)
    r=selected(db)
    assert r.count.state=='estimated'
    assert r.count.stage=='legally_secured (reported; stage unverified)'
    assert 'not a statement of current availability' in r.label()


def test_extractor_cannot_review(db):
    a=add(db,origin_kind='extraction',extractor_version='test-parser:1')
    with pytest.raises(ClaimError,match='operator_reviewer_required'):
        review_claim(db[0],request(db,a),reviewer='extraction:test-parser',apply=True)
    assert not selected(db).count.qualified


def test_scope_correction_does_not_hide_other_component(db):
    wrong=add(db,scope_kind='whole_scheme',scope_key='WHOLE_SCHEME',scope_label='Whole scheme'); review(db,wrong)
    correct=add(db,import_key='correct'); review(db,correct)
    other=add(db,scope_key='OTHER',scope_label='Other component',value=12,import_key='other-component',passage_locator='page 1 paragraph 2')
    review(db,other)
    review(db,wrong,'CORRECT',related_claim_id=correct)
    r=selected(db)
    assert not next(c for c in r.source_claims if c['id']==other)['historical']
    assert any(c.scope_label=='Other component' for c in r.alternatives)
    with pytest.raises(ClaimError,match='same_source_assertion'):
        review(db,other,'CORRECT',related_claim_id=correct)


def test_dirty_session_not_flushed_by_claim_reader(db,monkeypatch):
    a=add(db); review(db,a)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    db[3].scheme_intelligence.affordable_units_final=999
    for_applications([db[3]])
    from app.db.models import SchemeIntelligence
    with db[0].connect() as c:
        assert c.execute(select(SchemeIntelligence.affordable_units_final).where(SchemeIntelligence.application_id==db[3].id)).scalar_one()==72
    db[1].rollback()


def test_audit_only_reaccept_does_not_change_projection(db):
    a=add(db); review(db,a)
    before=selected(db).payload()
    review(db,a,reason='Second human review, same evidence and checks')
    assert selected(db).payload()==before
    review(db,a,'NEEDS_REVIEW')
    assert selected(db).payload()!=before


@pytest.mark.parametrize('qualifier,quantities', [('range',dict(value=None,lower_bound=60,upper_bound=80)),
    ('at_least',dict(value=None,lower_bound=60)),('up_to',dict(value=None,upper_bound=72))])
def test_bound_forms_preserved(db,qualifier,quantities):
    a=add(db,qualifier=qualifier,**quantities); review(db,a)
    r=selected(db)
    assert r.count.qualifier==qualifier and r.count.state=='estimated'
    assert r.count.value is None
    assert r.search(minimum=50)==('investigate' if qualifier=='up_to' else 'likely_meets')


def test_tenure_does_not_become_total_or_infer_opso(db):
    a=add(db,metric='tenure_count',tenure_name='Social rent'); review(db,a)
    r=selected(db)
    assert not r.count.qualified
    assert r.tenures[0].name=='Social rent'
    assert r.tenures[0].claim.scope_type=='component'
    assert 'OPSO' not in r.label()


@pytest.mark.parametrize('mode',['unknown','zero','conflict'])
def test_shared_consumer_outcomes_for_unknown_zero_conflict(db,monkeypatch,mode):
    from app.reporting.scheme_reconciliation import build_operative_planning_facts,resolve_operative_filter_facts
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    if mode=='zero':
        doc=document(db,'Synthetic authoritative statement: whole scheme contains zero affordable homes.')
        a=add(db,value=0,qualifier='exact',scope_kind='whole_scheme',scope_key='WHOLE_SCHEME',scope_label='Whole scheme',
            document_id=doc.id,passage_text=doc.extracted_text,extracted_text_hash=text_hash(doc.extracted_text))
        review(db,a)
    elif mode=='conflict':
        a=add(db); review(db,a)
        source=document(db,'Synthetic competing document: approximately 40 affordable retirement apartments.')
        b=add(db,value=40,import_key='other',document_id=source.id,passage_text=source.extracted_text,extracted_text_hash=text_hash(source.extracted_text)); review(db,b)
    operative=build_operative_planning_facts([db[3]])
    filters=resolve_operative_filter_facts(operative)
    buyer=build_planning_delivery_matching_facts_from_operative(operative,[db[3]])
    assert filters.affordable_assessment.payload()==buyer.affordable_assessment.payload()
    assert filters.affordable_assessment.search(maximum=50)=={'unknown':'unknown','zero':'meets','conflict':'investigate'}[mode]
    from app.reporting.affordable_housing_scope import select_affordable_position_for_scope
    from app.reporting.site_profile import _ah_position
    from app.reporting.opportunity_intelligence_packet import build_opportunity_intelligence_packet
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    from app.policy.buyer_matching import B2MatchingContext
    expected=filters.affordable_assessment.payload()
    position=select_affordable_position_for_scope(operative.affordable_housing,active_position_count=len(operative.active_positions))
    assert _ah_position(position)['assessment']==expected
    packet=build_opportunity_intelligence_packet(db[1],SimpleNamespace(opportunity_id=f'planning_delivery:site:{db[2].id}',
        opportunity_type='planning_delivery',kind='site',entity_id=db[2].id,phase_code=None,matching_facts=buyer),context=B2MatchingContext())
    assert packet.affordable_assessment.payload()==expected
    cards=[{'params':{'site_id':str(db[2].id)}}]
    _attach_planning_delivery_matching_facts(db[1],cards)
    assert cards[0]['matching_facts'].affordable_assessment.payload()==expected


def test_postgresql_ddl_contract_compiles():
    # Compilation is explicitly NOT an executed PostgreSQL migration/concurrency test.
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    from app.db.ah_claim_schema import protections
    ddl=str(CreateTable(claims).compile(dialect=postgresql.dialect()))
    assert 'NUMERIC(18, 6)' in ddl and 'ON DELETE RESTRICT' in ddl
    assert 'TRUNCATE' in protections('postgresql')['ah_source_claims_deny_mutation']


def test_postgresql_execution_fails_closed_until_runtime_validation():
    engine=SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
    with pytest.raises(ValueError,match='migration remains disabled'):
        migrate_local(engine)


def test_actual_explore_report_row_and_csv(db,monkeypatch):
    """Execute the page's actual row assembler without running UI/bootstrap code."""
    import ast
    from pathlib import Path
    from collections import defaultdict
    from datetime import date
    import pandas as pd
    from io import StringIO
    from app.reporting.scheme_reconciliation import (build_operative_planning_facts,
        resolve_operative_filter_facts,format_operative_decision_status_label)
    a=add(db); review(db,a)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    tree=ast.parse(Path('app/ui/pages/0_Explore.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_report_rows')
    engine,s,site,app,doc=db
    scope=dict(Site=type(site),session=s,site_applications={site.id:[app]},all_apps_by_site={site.id:[app]},council_regions={},
        pick_representative_application=lambda apps:apps[0],aggregate_scheme_fields=lambda apps:defaultdict(lambda:None),
        compute_lapse_status=lambda apps,site:dict(granted_app=None,build_status='unknown',status='unknown',deadline=None),
        build_operative_planning_facts=build_operative_planning_facts,resolve_operative_filter_facts=resolve_operative_filter_facts,
        format_operative_decision_status_label=format_operative_decision_status_label,
        resolve_explore_affordable_percentage_display=lambda facts:None,HOUSING_TYPE_LABELS={'unknown':'Unknown'},
        classify_housing_type=lambda *args:'unknown',housing_type_note=lambda *args:None,
        BUILD_STATUS_LABELS={'unknown':'Unknown'},LAPSE_STATUS_LABELS={'unknown':'Unknown'},parse_portal_date=lambda v:date.min)
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual_explore_row','exec'),scope)
    frame=pd.DataFrame(scope['build_report_rows']([site.id])).drop(columns=['decision_status','lapse_status','build_status','Applications Detail'])
    csv=pd.read_csv(StringIO(frame.to_csv(index=False))).iloc[0]
    assert csv['AH Reported Count']==72 and csv['AH Qualified']
    assert csv['AH Scope']=='Retirement apartments'
    assert json.loads(csv['AH Source Claims'])[0]['id']==a
    assert 'stage unverified' in csv['AH Assessment']


def test_phase_claim_without_legacy_phase_position(db,monkeypatch):
    a=add(db,scope_kind='phase',scope_key='PHASE_2',scope_label='Phase 2'); review(db,a)
    monkeypatch.setenv('PROPERTYAIGENT_AH_SOURCE_CLAIMS','1')
    from app.reporting.scheme_reconciliation import build_operative_planning_facts
    from app.reporting.affordable_housing_scope import select_affordable_position_for_scope
    facts=build_operative_planning_facts([db[3]])
    p=select_affordable_position_for_scope(facts.affordable_housing,phase_code='2')
    assert p.assessment.count.scope_type=='phase'
    assert p.assessment.search(maximum=100)=='investigate'
    assert select_affordable_position_for_scope(facts.affordable_housing,phase_code='3') is None


def test_concurrent_identical_review_replays(db):
    a=add(db); r=request(db,a)
    barrier=Barrier(2)
    def run(_):
        barrier.wait()
        return review_claim(db[0],r,reviewer='operator:reviewer',apply=True)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(run,[1,2]))
    assert results[0]['id']==results[1]['id']
    assert sorted(r['replayed'] for r in results)==[False,True]


def test_tenure_conflict_does_not_replace_independent_count(db):
    a=add(db); review(db,a)
    b=add(db,metric='tenure_count',tenure_name='Social rent',value=30,import_key='tenure1'); review(db,b)
    c=add(db,metric='tenure_count',tenure_name='Social rent',value=40,import_key='tenure2'); review(db,c)
    r=selected(db)
    assert r.count.value==72 and r.count.qualified
    assert all(t.claim.state=='conflicting' for t in r.tenures)
    assert 'Conflicting tenure quantities' in r.label()


def test_replacement_chain_can_resolve_rejected_intermediate(db):
    a=add(db); review(db,a)
    b=add(db,value=73,import_key='corrected'); review(db,b)
    review(db,a,'CORRECT',related_claim_id=b)
    review(db,b,'REJECT')
    c=add(db,value=74,import_key='corrected-again'); review(db,c)
    review(db,b,'CORRECT',related_claim_id=c)
    r=selected(db)
    assert r.count.value==74
    assert len(r.source_claims)==3 and len(r.relationships)==2
