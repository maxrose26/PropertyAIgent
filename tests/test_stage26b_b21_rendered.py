"""Actual offline B2.1 Streamlit journeys; browser viewport proof is separate."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import csv, io
import datetime as dt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest
from app.db.models import Base,Council,Site,Application,SchemeIntelligence,Settings
from app.security import access
from app.ui import common,access as ui_access
from tests.test_family_dashboard_render import render
from tests.test_family_dashboard import world,view_of


def text(at):
    return '\n'.join(str(e.value) for kind in ('markdown','caption','info','subheader','title','warning') for e in at.get(kind))


def test_representative_and_related_render_exact_source_dates(world):
    s=world.site(outline_age=300,rm_age=200,parent='S',phase='S',units_out=500,units_rm=68)
    apps=list(s.applications)
    for a in apps:a.status_verified_at=dt.datetime(2026,9,18) if a.reference.startswith('OUT') else dt.datetime(2026,10,8)
    world.session.commit()
    view=view_of(world).families[0]
    rendered,at=render(view)
    assert 'Verified as of:' in rendered and 'current status may require refresh' in rendered
    assert all(subject.planning_freshness for subject in (view.best,*view.related))
    assert all(e.label for e in at.expander)
    assert not at.exception


def test_full_dashboard_phase_profile_history_and_real_scheme_csv(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'b21.sqlite'));Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Council(code='stockport',name='Synthetic',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
        site=Site(council_code='stockport',canonical_address='b21 synthetic',display_address='B2.1 synthetic scope');session.add(site);session.flush();sid=site.id
        parent=Application(council_code='stockport',site_id=sid,reference='OUT/B21',proposal='Outline erection of 500 dwellings',decision='Granted',decision_issued_date='2024-01-01',application_received='2023-01-01',estimated_unit_count=500,status_verified_at=dt.datetime(2026,9,18),summary_url='https://example.invalid/parent')
        child=Application(council_code='stockport',site_id=sid,reference='RM/B21',proposal='Reserved matters for Phase 1 erection of 68 dwellings pursuant to OUT/B21',decision='Granted',decision_issued_date='2026-09-25',application_received='2026-01-01',estimated_unit_count=68,status_verified_at=dt.datetime(2026,10,8),summary_url='https://example.invalid/child')
        parent.scheme_intelligence=SchemeIntelligence(total_units_final=500,development_type='houses');child.scheme_intelligence=SchemeIntelligence(total_units_final=68,development_type='houses')
        session.add_all([parent,child]);session.commit()
    actor=access.current_actor()
    def admitted(**kwargs):access.registry.check(actor);access._current.set(actor);return actor
    @contextmanager
    def scope():
        with access.actor_scope(actor):yield actor
    @contextmanager
    def db():
        with access.actor_scope(actor),Session(engine) as session:yield session,session.get(Settings,1)
    monkeypatch.setattr(ui_access,'admitted_actor',admitted);monkeypatch.setattr(ui_access,'page_scope',scope)
    monkeypatch.setattr(common,'get_db',db);monkeypatch.setattr(common,'bootstrap',lambda:(access.require_admitted(), __import__('app.config',fromlist=['load_councils']).load_councils())[1]);monkeypatch.setattr(common,'credits_sidebar',lambda *_:None)
    from app.ui import protected_download
    import streamlit as st
    monkeypatch.setattr(protected_download,'download_button',st.download_button) # existing offline media-byte adapter
    root=Path(__file__).resolve().parents[1]
    from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
    stores=[]
    def storage(*a,**kw):
        obj=MemoryMediaFileStorage(*a,**kw);stores.append(obj);return obj
    monkeypatch.setattr('streamlit.testing.v1.app_test.MemoryMediaFileStorage',storage)
    at=AppTest.from_file(str(root/'app/ui/streamlit_app.py'));at.session_state['active_buyer_key']='nesten_homes';at.run(timeout=30)
    assert not at.exception
    assert 'Verified as of:' in text(at)
    from app.reporting.buyer_family_feed import build_buyer_opportunity_families
    with Session(engine) as session:
        families=build_buyer_opportunity_families(session,'nesten_homes',limit=10)['families']
        child_subject=next(m for f in families for m in f.members if m.source.get('phase_code')=='1')
    at.switch_page('pages/1_Scheme_Detail.py');at.query_params.update({'site_id':str(sid),'subject_key':child_subject.subject_key,'origin':'opportunities'});at.run(timeout=30)
    assert not at.exception,[(e.message,e.stack_trace) for e in at.exception]
    content=text(at)
    selected=content.index('Originating acquisition subject');wider=content.index('The evidence profile below covers the wider site')
    # Streamlit groups element types, so assert the contextual section's exact payload independently too.
    assert 'RM/B21' in content and '08 Oct 2026' in content and '18 Sep 2026' in content
    assert child_subject.source['planning_freshness'][0][1]=='RM/B21'
    assert child_subject.source['planning_freshness'][0][2].last_successful_verification==dt.datetime(2026,10,8)
    history=[e.value for e in at.dataframe if 'Planning Verified As Of' in e.value.columns]
    assert history and 'RM/B21' in str(history)
    at.switch_page('pages/0_Explore.py');at.run(timeout=30)
    assert not at.exception,[(e.message,e.stack_trace) for e in at.exception]
    download=next(d for d in at.download_button if d.key=='download_all_filtered_report')
    file_id=download.proto.url.rsplit('/',1)[-1].split('.')[0]
    data=stores[-1].get_file(file_id).content
    rows=list(csv.DictReader(io.StringIO(data.decode())))
    assert rows and 'Planning Verified As Of' in rows[0]
    assert 'OUT/B21: 2026-09-18' in rows[0]['Planning Verified As Of']
    assert 'RM/B21' not in rows[0]['Planning Verified As Of'] # phase time cannot verify wider-site status
    # Actual Local Plan detail must use the same eligibility decision as reports/CSV.
    from tests.test_allocation_report import _make_local_plan, _make_allocation, _make_relationship, _make_summary
    from app.reporting.allocation_report import build_allocation_report_context, to_csv_rows
    with Session(engine) as session:
        plan=_make_local_plan(session,council_code='stockport')
        allocation=_make_allocation(session,plan.id,council_code='stockport')
        _make_relationship(session,allocation.id,sid)
        summary=_make_summary(session,allocation.id,headline='B21 stored prose must be withheld',overview='Old authoritative context')
        aid=allocation.id
        session.query(Application).filter_by(reference='RM/B21').one().decision='Refused'
        session.commit()
        report=build_allocation_report_context(session,[aid])
        assert report.entries[0].ai_intelligence.requires_refresh
        assert 'B21 stored prose must be withheld' not in str(to_csv_rows(report))
    at.switch_page('pages/3_Local_Plan_Sites.py');at.query_params.clear();at.query_params['allocation_id']=str(aid);at.run(timeout=30)
    assert not at.exception,[(e.message,e.stack_trace) for e in at.exception]
    assert 'B21 stored prose must be withheld' not in text(at)
    assert 'requires refresh' in text(at).lower()
    engine.dispose()
