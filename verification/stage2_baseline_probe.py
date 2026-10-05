"""Offline synthetic reproduction against an arbitrary checkout at cwd.
This is a historical-behaviour probe, not a statement of real planning facts.
"""
import datetime as dt
import json
import os
import sys
from unittest.mock import patch
sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base, Council, Site, Application, LocalPlan, LocalPlanSite, VisualEvidence
from app.enrichment.epc_lookup import check_build_status
from app.pipeline.lapse_tracking import compute_lapse_status, LAPSE_STATUS_LABELS
from app.reporting.dashboard import _approaching_lapse_cards
from app.reporting.allocation_discovery import build_allocation_card
from app.visuals.site_view import build_allocation_visual_summaries, build_allocation_image_status
from app.ui.common import _filter_visible_applications
from pathlib import Path

engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
with Session(engine) as session:
    session.add(Council(code='testcouncil',name='Synthetic',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
    site=Site(council_code='testcouncil',canonical_address='synthetic',display_address='Synthetic historical failure shape')
    session.add(site);session.flush()
    grant=Application(council_code='testcouncil',site_id=site.id,reference='SYN/GRANT',proposal='Erection of 40 dwellings',
        decision='Granted',decision_issued_date=(dt.date.today()-dt.timedelta(days=3*365-25)).strftime('%a %d %b %Y'),unit_confirmation_status='undetermined')
    session.add(grant);session.commit()
    with patch('app.enrichment.epc_lookup.search_epcs',return_value=[{'registrationDate':'2020-01-01'}]*10):
        epc=check_build_status('offline','TEST',10,dt.date(2026,1,1))
    admin=Application(council_code='testcouncil',site_id=site.id,reference='SYN/ADMIN',application_category='condition_discharge_or_details',application_received=dt.date.today().strftime('%a %d %b %Y'))
    states={}
    for raw in ('unknown','complete'):
        site.build_status=raw
        states[raw]=compute_lapse_status([grant,admin],site)['build_status']
    site.build_status=None
    lapse=compute_lapse_status([grant],site)
    plan=LocalPlan(council_code='testcouncil',plan_name='Synthetic joint plan',status='adopted')
    session.add(plan);session.flush()
    alloc=LocalPlanSite(council_code='testcouncil',local_plan_id=plan.id,site_name='Synthetic allocation',plan_name=plan.plan_name,plan_status='adopted')
    session.add(alloc);session.flush()
    visual=VisualEvidence(allocation_id=alloc.id,source_page=1,image_type='allocation_map',review_status='needs_review',status='current',is_primary=True,extraction_confidence=.9)
    session.add(visual);session.commit()
    card=build_allocation_card(alloc,plan=plan,council_name='Synthetic',council_codes_on_plan=['testcouncil','othercouncil'],matched_site=None,linked_applications=[],visual_summary={},visual_fallback=None,council_five_year_supply=None)
    page=Path('app/ui/pages/1_Scheme_Detail.py').read_text()
    print(json.dumps(dict(
        D01_epc_status=epc.status,D01_count=epc.epc_count,D02_build_states=states,
        D03_review_label=LAPSE_STATUS_LABELS[lapse['status']],D03_basis=lapse.get('deadline_basis'),
        W01_surfaced=len(_approaching_lapse_cards(session,20)),W01_visible_applications=len(_filter_visible_applications([grant],10)),W01_limited_destination='limited_profile' in page,
        D04_joint_membership=card['is_multi_authority'],D04_cross_boundary_councils=card['cross_boundary_councils'],
        D05_summary=build_allocation_visual_summaries(session,[alloc.id])[alloc.id]['status'],D05_status=build_allocation_image_status(session,[alloc.id])[alloc.id],
    ),indent=2))
