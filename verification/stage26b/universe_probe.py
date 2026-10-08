"""Real offline SQLite feed/universe differential; synthetic dates/context, no production forecast."""
import dataclasses
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,sys.argv[1])
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.models import Base,Council,Site,Application,SchemeIntelligence
from verification.stage1_test_context import synthetic_context,seed_fixture
from app.reporting.opportunity_universe import build_current_opportunity_universe,compute_opportunity_fingerprint
from app.reporting.buyer_family_feed import load_buyer_family_inputs,evaluate_buyer_families
from app.policy.buyer_profiles import BUYER_PROFILES
from app.reporting.mandate_explanation import present_mandate_explanation
cases=json.loads(Path(sys.argv[2]).read_text())
engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine);seed_fixture(engine)
queries=[]
def track(conn,cursor,statement,parameters,context,executemany):
    queries.append(statement.split()[0])
with tempfile.TemporaryDirectory() as directory,synthetic_context(directory),Session(engine) as session:
    session.add(Council(code='stockport',name='Synthetic',base_url='https://example.invalid',date_field_mode='received',doc_system='idox'))
    for c in cases:
        session.add(Site(id=c['site_id'],council_code='stockport',canonical_address='synthetic-'+str(c['site_id']),display_address='Synthetic case '+str(c['site_id'])))
        # Force a recent-permission detector in BOTH trees. This tests corrected
        # eligibility consequences, not the historical planning-status projection.
        app=Application(id=c['application_id'],site_id=c['site_id'],council_code='stockport',reference=c['reference'],proposal=c['proposal_from_current_source'],
            status='Decided',decision='Granted',decision_issued_date=(dt.date.today()-dt.timedelta(days=30)).isoformat(),application_received='2025-01-01',estimated_unit_count=c['stored_total'])
        app.scheme_intelligence=SchemeIntelligence(total_units_final=c['stored_total'],development_type=c['stored_development_type'],housing_typology=c['stored_housing_typology'],**{k:v for k,v in c['stored_ah'].items() if hasattr(SchemeIntelligence,k)})
        session.add(app)
    # Held-out same-site parent+legitimate child+ineligible ancillary child.
    session.add(Site(id=900,council_code='stockport',canonical_address='synthetic-family',display_address='Synthetic family'))
    for n,proposal,units in [(9000,'Outline erection of 500 dwellings',500),(9001,'Reserved matters Phase 1 erection of 80 homes pursuant to outline permission OUT/9000',80),(9002,'Reserved matters Phase 2 pedestrian crossings/bridges pursuant to outline permission OUT/9000',372)]:
        app=Application(id=n,site_id=900,council_code='stockport',reference='OUT/9000' if n==9000 else f'RM/{n}',proposal=proposal,decision='Granted',decision_issued_date=(dt.date.today()-dt.timedelta(days=30)).isoformat(),application_received='2025-01-01',estimated_unit_count=units)
        app.scheme_intelligence=SchemeIntelligence(total_units_final=units,development_type='houses');session.add(app)
    session.commit();session.expire_all()
    event.listen(engine,'before_cursor_execute',track)
    records=build_current_opportunity_universe(session)
    universe_queries=len(queries);queries.clear()
    inputs=load_buyer_family_inputs(session)
    load_queries=len(queries);queries.clear()
    out={'scope':'9 date-normalised synthetic recent-permission wrappers plus held-out parent/2-child family; actual detectors, matcher, feed, family grouping and full fingerprint builder. Not production replay.',
         'universe':{},'buyers':{},'query_counts':{'universe':universe_queries,'family_load':load_queries}}
    for r in records:
        out['universe'][r.opportunity_id]={'fingerprint_fields':r.fingerprint_fields,'fingerprint':compute_opportunity_fingerprint(r.fingerprint_fields),'unit_count':r.matching_facts.unit_count}
    for key,profile in BUYER_PROFILES.items():
        result=evaluate_buyer_families(session,key,inputs,100,profile=profile,include_excluded=True)
        families=[]
        for family in [*result['families'],*result.get('excluded_families',[])]:
            members=[]
            for m in family.members:
                fit=m.source['buyer_fit']
                count=m.source.get('count_assessment')
                members.append({'subject':m.subject_key,'fit':dataclasses.asdict(fit),'explanation':dataclasses.asdict(present_mandate_explanation(fit)),
                    'count':count.fingerprint() if count else None})
            families.append({'family':family.family_key,'representative':family.representative.subject_key,'excluded':family.is_terminally_excluded,'members':members})
        out['buyers'][key]=families
        out['query_counts'][key]=len(queries);queries.clear()
    event.remove(engine,'before_cursor_execute',track)
engine.dispose()
print(json.dumps(out,sort_keys=True,default=str))
