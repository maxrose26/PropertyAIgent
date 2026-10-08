"""Actual offline dashboard/profile/export and related-subject rendering."""
from contextlib import contextmanager
from pathlib import Path
import datetime as dt
import csv
import io
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest
from app.db.models import Base,Council,Site,Application,SchemeIntelligence,Settings
from app.security import access
from app.ui import common,access as ui_access
from app.reporting.scheme_reconciliation import build_operative_planning_facts,count_assessment_for_facts
from app.reporting.csv_safety import csv_bytes


def test_contained_count_dashboard_profile_related_and_export(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'ui.sqlite'));Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Council(code='stockport',name='Synthetic',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
        site=Site(council_code='stockport',canonical_address='synthetic',display_address='Synthetic containment site');session.add(site);session.flush();sid=site.id
        app=Application(council_code='stockport',site_id=sid,reference='SYN/PORCH',proposal='Demolition of existing porches to 56 dwellings and erection of replacement porches',decision='Granted',decision_issued_date=(dt.date.today()-dt.timedelta(days=30)).isoformat(),estimated_unit_count=56,summary_url='https://example.invalid/source')
        app.scheme_intelligence=SchemeIntelligence(total_units_final=56,development_type='houses');session.add(app);session.commit()
        count=count_assessment_for_facts(build_operative_planning_facts([app]))
        columns=count.report_columns();data=csv_bytes([columns],list(columns));row=next(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        assert row['Count Display']=='Unit count unverified' and row['Count Precision']=='UNKNOWN'
        assert row['Count Lower']==row['Count Upper']=='' and '56' not in data.decode()
    actor=access.current_actor()
    def admitted(**kwargs):
        access.registry.check(actor);access._current.set(actor);return actor
    @contextmanager
    def scope():
        with access.actor_scope(actor):yield actor
    @contextmanager
    def db():
        with access.actor_scope(actor),Session(engine) as session:yield session,session.get(Settings,1)
    monkeypatch.setattr(ui_access,'admitted_actor',admitted);monkeypatch.setattr(ui_access,'page_scope',scope)
    monkeypatch.setattr(common,'get_db',db);monkeypatch.setattr(common,'bootstrap',lambda:access.require_admitted());monkeypatch.setattr(common,'credits_sidebar',lambda *_:None)
    root=Path(__file__).resolve().parents[1]
    at=AppTest.from_file(str(root/'app/ui/streamlit_app.py'));at.session_state['active_buyer_key']='nesten_homes';at.run(timeout=30)
    def text():return '\n'.join(str(e.value) for kind in ('markdown','caption','info','subheader','title') for e in at.get(kind))
    assert not at.exception
    assert 'Unit count unverified' in text() and '56 homes' not in text()
    at.switch_page('pages/1_Scheme_Detail.py');at.query_params.update({'site_id':str(sid)});at.run(timeout=30)
    assert not at.exception,[(e.message,e.stack_trace) for e in at.exception]
    assert '56 homes' not in text()
    assert 'Unit count unverified' in text() or 'Conflicting unit evidence' in text()
    # Render real family-card related expansion with exactly the contained count;
    # actual multi-subject feed/representative consequences are separately diffed.
    from app.reporting.buyer_family_feed import build_buyer_opportunity_families
    from app.reporting.family_presentation import present_family_result
    from dataclasses import replace
    from tests.test_family_dashboard_render import render
    with Session(engine) as session:
        view=present_family_result(build_buyer_opportunity_families(session,'nesten_homes',limit=10),{}).families[0]
    related=replace(view.best,label='Related synthetic scope')
    rendered,card=render(replace(view,related=(related,)))
    assert 'Unit count unverified' in rendered and '56 homes' not in rendered
    assert any('Related acquisition subjects' in e.label for e in card.expander)
    assert all(e.label for e in card.expander)
    engine.dispose()
