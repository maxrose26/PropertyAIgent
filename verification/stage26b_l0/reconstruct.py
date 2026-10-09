"""L0 retained-snapshot reconstruction. Explicit external files; no production/network.

Reuses the accepted privacy-minimised replay loader and actual application functions.
Omitted applicant/company/title evidence is recorded as uncaptured, never absent.
Evaluation date is retained 8 October; later metadata is a separate observation.
"""
import sys,json,datetime as dt,tempfile,dataclasses,hashlib,time,socket,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import argparse, types
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--snapshot',type=Path,required=True)
parser.add_argument('--metadata',type=Path,required=True)
parser.add_argument('--accepted-replay',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--evaluation-date',choices=['2026-10-08','2026-10-09'],default='2026-10-09')
args=parser.parse_args()
"""Linux offline test entrypoint: deny network syscalls before importing tests."""
import ctypes
import errno
import os
import socket
import sys

lib=ctypes.CDLL('libseccomp.so.2')
lib.seccomp_init.argtypes=[ctypes.c_uint32]
lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p]
lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
assert ctx
for name in ('socket','socketpair','connect','sendto','sendmsg','sendmmsg'):
    number=lib.seccomp_syscall_resolve_name(name.encode())
    assert number>=0
    assert lib.seccomp_rule_add(ctx,0x50000|errno.EPERM,number,0)==0
assert lib.seccomp_load(ctx)==0
lib.seccomp_release(ctx)
try:
    socket.socket()
except PermissionError:
    pass
else:
    raise RuntimeError('Offline network guard failed')

from sqlalchemy import create_engine,event,DateTime,Date,Boolean,Integer,Float,Text,String
from sqlalchemy.orm import Session
from app.db import models as m
from contextlib import contextmanager
from app.security import access
@contextmanager
def retained_admitted_context(directory):
 issuer='http://127.0.0.1:19999';path=Path(directory)/'offline-preview-policy.json'
 ids=[b['id'] for b in data['buyers']];assert {b['workspace_id'] for b in data['buyers']}=={1}
 policy=dict(version=1,enabled=True,environment='local',issuer=issuer,client_id='offline-preview',web_processes=1,web_replicas=1,owner_subject='offline-preview',principals=[dict(issuer=issuer,subject='offline-preview',role='operator',enabled=True,workspace_id=1,buyer_ids=ids)],paid_actions=dict.fromkeys(['contacts.enrich','plan.summary','allocation.summary','shortlist.intelligence','shortlist.research','search.parse','report.narrative','evaluation.run'],False))
 path.write_text(json.dumps(policy));old_path=os.environ.get('PROPERTYAIGENT_ACCESS_POLICY');old_registry=access.registry;os.environ['PROPERTYAIGENT_ACCESS_POLICY']=str(path)
 registry=access.LeaseRegistry();registry.boot=int(time.time())-1;registry.middleware_ready=True;access.registry=registry
 actor=registry.issue(dict(iss=issuer,sub='offline-preview',aud='offline-preview',iat=int(time.time()),exp=int(time.time())+3600,email_verified=True),'offline-preview-cookie')
 try:
  with access.actor_scope(actor):yield actor
 finally:
  access.registry=old_registry
  if old_path is None:os.environ.pop('PROPERTYAIGENT_ACCESS_POLICY',None)
  else:os.environ['PROPERTYAIGENT_ACCESS_POLICY']=old_path

from app.reporting.opportunity_universe import build_current_opportunity_universe,compute_opportunity_fingerprint
from app.reporting.buyer_family_feed import load_buyer_family_inputs,evaluate_buyer_families
from app.reporting.mandate_explanation import present_mandate_explanation
import app.reporting.acquisition_position as ap
import app.reporting.allocation_development_coverage as cov
from app.extraction.ownership_control_evidence import CertificateDetectionResult,FormApplicantIdentityResult,S106PartyEvidenceHit
from app.policy.buyer_profile_store import get_buyer_profile_dataclass,compute_buyer_mandate_fingerprint
snapfile=args.snapshot
assert hashlib.sha256(snapfile.read_bytes()).hexdigest()=='7838168f65178e0ea7e7b32d2d93e66c3ec41086b4ff5a98af36c66075eabbc4', 'Unreviewed retained snapshot'
assert hashlib.sha256(args.metadata.read_bytes()).hexdigest()=='bc4411fbf7cefdf06c1332cfa442d282d6b882fc87216951f2a2b65c9e70a3b1', 'Unreviewed retained metadata'
snap=json.loads(snapfile.read_text());data=snap['data'];facts={r['id']:r for r in data['document_facts']}
metadata=json.loads(args.metadata.read_text())
assert hashlib.sha256(args.accepted_replay.read_bytes()).hexdigest()=='5c84cfe7335597d530121359fcf44abe294bbd885966100af7a8001670575381', 'Unreviewed accepted replay'
accepted=json.loads(args.accepted_replay.read_text())
assert accepted['snapshot_sha256']==hashlib.sha256(snapfile.read_bytes()).hexdigest()
assert accepted['date']=='2026-10-08' and accepted['code']=='b11'
# Freeze only clock-consuming application modules, not process/system date.
class RetainedDate(dt.date):
    @classmethod
    def today(cls):return cls.fromisoformat(args.evaluation_date)
import app.reporting.dashboard as dashboard
import app.pipeline.lapse_tracking as lapse
proxy=types.SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')})
proxy.date=RetainedDate
dashboard.dt=proxy;lapse.dt=proxy
assert snap['read_only']=='on' and not snap['output_overflow']
assert not any(r.get(k) for r in facts.values() for k in ('overflow','unsupported_identity_unicode','unsupported_case_context','unsupported_party_unicode'))
assert not any(r.get('unsupported_token_case') for r in data['scheme_intelligence'])
engine=create_engine('sqlite:///:memory:');m.Base.metadata.create_all(engine);columns={t:set() for t in data if t!='document_facts'}
ignored={
'buyers':{'display_name','buyer_type'},'buyer_mandates':{'primary_requirement','notes'},'workspaces':{'name'},
'control_relationships':{'entity_name_raw','evidence_basis','evidence_snippet','title_number'},
'applications':{'applicant_name_raw'},'documents':{'extracted_text'},
}
with engine.begin() as c:
 for table,rows in data.items():
  if table=='document_facts':continue
  t=m.Base.metadata.tables[table]
  for raw in rows:
   row={k:v for k,v in raw.items() if k in t.c};columns[table].update(row)
   if table=='documents':row['extracted_text']='[projected text presence]' if facts.get(row['id'],{}).get('text_present') else None
   if table=='buyers':row.update(display_name=row['buyer_key'],buyer_type='[display-only omitted]')
   if table=='buyer_mandates':row.update(primary_requirement='[display-only omitted]',notes=None)
   for col in t.c:
    if col.name in row:
     v=row[col.name]
     if v is not None and isinstance(col.type,DateTime):row[col.name]=dt.datetime.fromisoformat(v)
     elif v is not None and isinstance(col.type,Date):row[col.name]=dt.date.fromisoformat(v)
    elif not col.nullable and col.default is None and not col.primary_key:
     if isinstance(col.type,(String,Text)):row[col.name]='[excluded display-only metadata]'
     elif isinstance(col.type,Boolean):row[col.name]=False
     elif isinstance(col.type,(Integer,Float)):row[col.name]=0
     elif isinstance(col.type,DateTime):row[col.name]=dt.datetime(2026,10,8)
   c.execute(t.insert().values(**row))
# Only replace privacy-minimised extraction outputs, never matcher/count/subject/family/fingerprint code.
def cert(d):
 f=facts[d.id]
 return CertificateDetectionResult(d.id,d.application_id,f['certificate'],None,None) if f['certificate'] else None
def identity(d,a):
 f=facts[d.id];name=f['identity_token'];return FormApplicantIdentityResult(d.id,d.application_id,name,'unresolved','projected_identity' if name else 'unresolved',None)
def parties(d):
 return [S106PartyEvidenceHit(d.id,d.application_id,r['role'],'projected_evidence',r['token'],'[not exported]') for r in facts[d.id]['parties']]
ap.detect_ownership_certificate=cert;ap.resolve_certificate_a_applicant_identity=identity;ap.extract_s106_defined_parties=parties;ap.extract_s106_title_numbers=lambda d:[]
ap._company_entity_type_for=lambda session,name,known:(known or 'unknown',None)
ap._applicant_position_for_application=lambda session,a:ap.ApplicantPositionFact(a.id,None,None,None,None,None,None,(),False)
def phases(pairs):
 return [cov.PhasingEvidenceHit(d.id,d.doc_type,a.id,a.reference,phrase,'[derived factual phrase]') for d,a in pairs for phrase in facts.get(d.id,{}).get('phasing',[])]
cov.search_phasing_evidence=phases
# Reject undeclared mapped-field reads; display-only substitutions explicitly permitted.
missing_fields=set();read_fields=set();original=m.Base.__getattribute__
def audited(self,name):
 cls=type(self);table=getattr(cls,'__tablename__',None)
 if table in columns and name in cls.__table__.c:
  read_fields.add((table,name))
  if name not in columns[table] and name not in ignored.get(table,set()):
   missing_fields.add((table,name))
   if not os.environ.get('PREVIEW_DISCOVERY_ONLY'):raise RuntimeError('Missing production input '+table+'.'+name)
 return original(self,name)
m.Base.__getattribute__=audited
# Offline safety: SQLite query_only, no connection to any network/database/model.
with engine.connect() as c:c.exec_driver_sql('PRAGMA query_only=ON')
queries=[]
def track(conn,cursor,sql,args,context,many):
 kind=sql.lstrip().split()[0].upper();queries.append(kind)
 if kind not in ('SELECT','PRAGMA'):raise RuntimeError('Unexpected offline statement '+kind)
event.listen(engine,'before_cursor_execute',track)
def reject(*args,**kwargs):raise RuntimeError('Write/commit/network prohibited during replay')
event.listen(Session,'before_flush',reject);event.listen(Session,'before_commit',reject)
socket.create_connection=reject;socket.socket.connect=reject
os.environ.pop('DATABASE_URL',None)
safety_checks=[]
def denied(label, action):
 try:action()
 except RuntimeError:safety_checks.append(label)
 else:raise AssertionError('Safety boundary failed '+label)
with Session(engine) as safety_session:
 denied('commit blocked',safety_session.commit)
 probe=m.Site(council_code='offline',canonical_address='offline-only-denial',display_address='offline-only-denial');safety_session.add(probe)
 denied('ORM flush blocked',safety_session.flush);safety_session.rollback()
 for verb in ('INSERT INTO sites(id) VALUES(999999)','UPDATE sites SET id=id','DELETE FROM sites'):
  denied(verb.split()[0]+' blocked',lambda verb=verb:safety_session.execute(__import__('sqlalchemy').text(verb)))
 denied('undeclared mapped-field read blocked',lambda:getattr(safety_session.get(m.Site,data['sites'][0]['id']),'status_summary'))
denied('network creation blocked',lambda:socket.create_connection(('127.0.0.1',1)))
queries.clear();missing_fields.clear()
from verification.stage26b_l0.dependencies import DIRECT, CONTEXT, DISCOVERY, edge, summarise, risk_cohort, priority_key
from app.reporting.scheme_reconciliation import build_operative_planning_facts, resolve_planning_role, SUBSTANTIVE_ROLES
from app.reporting.allocation_development_coverage import build_allocation_development_coverage
from app.reporting.subject_relationships import scan_parent_citations

raw_apps={r['id']:r for r in data['applications']}
meta_apps={r['id']:r for r in metadata['applications']}
assert set(raw_apps)==set(meta_apps)
for id, row in raw_apps.items():
    for field in ('site_id','reference','status','decision','decision_issued_date'):
        assert row.get(field)==meta_apps[id].get(field), 'Retained metadata identity/fact mismatch'

start=time.monotonic();edges={};subjects={};unresolved=[];allocation_map=[]
planning_consumers=['dashboard','profile','related_subject','scheme_csv','buyer_assessment','spec028_explanation','family_presentation','opportunity_fingerprint']
count_consumers=['deterministic_reconciliation','dashboard','profile','scheme_csv','buyer_assessment','spec028_explanation','family_presentation','opportunity_fingerprint']

def add(subject, app_id, kind, fields, consumers, reason, role='context', documents=()):
    if app_id not in raw_apps:
        unresolved.append(dict(subject_key=subject['subject_key'],field=','.join(fields),reason='Source ID not captured'))
        return
    row=raw_apps[app_id]
    e=edge(subject_key=subject['subject_key'],site_id=row['site_id'],application=row,
           dependency_type=kind,fields=fields,consumers=consumers,reason=reason,
           truth='DISCOVERY_CANDIDATE' if kind==DISCOVERY else 'RETAINED_HISTORICAL_FACT',
           operative_role=role,documents=documents,verification_observation=meta_apps[app_id])
    # Each fact/consumer edge has one type; direct status and context from same app are distinct.
    e['verification_scope']='application_planning_status_only; does not certify other supported fields'
    e['generated_intelligence_dependency']='UNRESOLVED: per-record generated provenance not captured'
    e['consumer_mapping_qualification']='observed source attribution; downstream list is conservative candidate impact, not proven causality'
    e['material_change_potential']={
        'planning_presentation':bool(set(fields)&{'planning_status','decision','decision_issued_date','opportunity_signal'}),
        'scheme_intelligence':'dependency review needed; do not automatically invalidate',
        'allocation_narrative_eligibility':'only where accepted allocation-context edge exists',
        'deterministic_reconciliation':kind!=DISCOVERY,
        'buyer_assessment':kind!=DISCOVERY,
        'spec028_explanation':kind!=DISCOVERY,
        'family_presentation':kind!=DISCOVERY,
        'fingerprint_value':kind!=DISCOVERY,
        'future_ai_summary':'potential only, not implemented or generation authority'}
    key=(e['subject_key'],app_id,kind,tuple(e['supported_fields']),tuple(e['consumers']))
    edges[key]=e

with tempfile.TemporaryDirectory() as directory,retained_admitted_context(directory),Session(engine) as session:
    inputs=load_buyer_family_inputs(session);contexts={}
    from app.reporting.acquisition_subjects import parse_opportunity_id
    universe_index={}
    for record in build_current_opportunity_universe(session):
        parsed=parse_opportunity_id(record.opportunity_id)
        universe_index.setdefault((parsed.domain,parsed.anchor_id,parsed.scope_key),[]).append(record.opportunity_id)
    actual={}
    for buyer in data['buyers']:
        key=buyer['buyer_key'];result=evaluate_buyer_families(session,key,inputs,10000,include_excluded=True,contexts=contexts)
        families=[*result['families'],*result['excluded_families']]
        expected=accepted['buyers'][key]['families']
        # Fidelity gate: actual current app functions reproduce retained identities/fits/order exactly.
        if args.evaluation_date=='2026-10-08':
            assert [(list(f.family_key),f.representative.subject_key,[m.subject_key for m in f.members]) for f in families]==[
            (f['family'],f['representative'],[m['subject'] for m in f['members']]) for f in expected]
        expected_members={v['subject']:v for f in expected for v in f['members']}
        for f in families:
            for member in f.members:
                old=expected_members.get(member.subject_key)
                card=member.source
                if args.evaluation_date=='2026-10-08':
                    assert dataclasses.asdict(card['buyer_fit'])==old['fit'], 'Retained assessment parity failed'
                subject=subjects.setdefault(member.subject_key,dict(subject_key=member.subject_key,
                    site_id=int(card['params']['site_id']) if card['params'].get('site_id') else None,
                    allocation_id=int(card['params']['allocation_id']) if card['params'].get('allocation_id') else None,
                    scope=card.get('phase_code'),buyers={},status_sources=[],
                    non_application_inputs=(['sites.council_code','sites.build_status','sites.build_status_checked_at','sites.epc_dwellings_found'] if card['params'].get('site_id') else
                       ['local_plan_sites.minimum_dwellings','local_plan_sites.maximum_capacity','local_plan_sites.indicative_capacity',
                        'local_plan_sites.council_code','local_plan_sites.allocation_status','local_plans.status'])))
                subject['buyers'][key]=dict(family=list(f.family_key),representative=f.representative.subject_key==member.subject_key,
                    family_visible=not f.is_terminally_excluded)
                if len(subject['buyers'])>1:continue  # buyer-independent source facts, consumers recorded on subject
                sid=subject['site_id']
                ids=universe_index.get((member.domain,member.anchor_id,card.get('phase_code')),[])
                subject['universe_opportunity_ids']=sorted(ids)
                subject['identity_qualification']='exact_existing_universe_join' if len(ids)==1 else 'UNRESOLVED: no unique existing universe record'
                if len(ids)!=1:unresolved.append(dict(subject_key=member.subject_key,field='universe_identity',reason=subject['identity_qualification']))
                if sid is not None:
                    apps=session.query(m.Application).filter(m.Application.site_id==sid).order_by(m.Application.id).all()
                    for label, ref, freshness in card.get('planning_freshness',()):
                        matching=[a for a in apps if a.reference==ref] if ref else []
                        if len(matching)==1 and freshness.planning_state!='unknown_unverified':
                            a=matching[0];subject['status_sources'].append(a.id)
                            add(subject,a.id,DIRECT,['planning_status','decision','decision_issued_date'],planning_consumers,
                                'Actual B2.1 exact-status-source adapter position: '+label,'status_supporting')
                        else:unresolved.append(dict(subject_key=member.subject_key,field='planning_status',reason=freshness.qualification))
                    assessment=card.get('count_assessment')
                    if assessment:
                        for source in assessment.sources:
                            determined=assessment.precision in {'EXACT','APPROXIMATE','RANGE'}
                            add(subject,source.application_id,DIRECT if determined else CONTEXT,
                                ['qualified_residential_scale' if determined else 'count_conflict_or_scope_input'],count_consumers,
                                'Actual CountAssessment source; precision='+assessment.precision,
                                'count_supporting' if determined else 'unresolved_count_context')
                        for source in assessment.superseded:
                            add(subject,source.application_id,CONTEXT,['superseded_count_evidence'],['deterministic_reconciliation'],
                                'CountAssessment explicitly superseded source')
                    ref=card.get('application_reference') or card.get('reference')
                    # Source attribution of existing AH/type facts only; no AH semantic correction.
                    from app.reporting.scheme_reconciliation import planning_facts_for_scope, resolve_operative_filter_facts
                    from app.policy.buyer_matching import _operative_source_scheme_intelligence, _corroborated_development_type
                    operative=build_operative_planning_facts(apps)
                    if card.get('phase_code') and assessment is not None:
                        operative=planning_facts_for_scope(operative,assessment.scope_type,assessment.scope_label)
                    facts=card['matching_facts'];by_id={a.id:a for a in apps}
                    source_si=_operative_source_scheme_intelligence(operative,by_id)
                    if source_si is not None and facts.development_type_raw is not None:
                        add(subject,source_si.application_id,DIRECT,['development_type','specialist_development'],count_consumers,
                            'Existing matcher source SchemeIntelligence selected from count supporters','scheme_intelligence_supporting')
                    elif facts.development_type_raw is not None:
                        reference=operative.consented_position.reference
                        corroborated=_corroborated_development_type(assessment,by_id,operative_application_id=reference.source.application_id if reference.source else None)
                        if corroborated:
                            for source in assessment.sources:
                                add(subject,source.application_id,DIRECT,['development_type_corroboration'],count_consumers,
                                    'Existing approximate-count unanimous development-type corroboration','corroborating_supporter')
                        else:unresolved.append(dict(subject_key=member.subject_key,field='development_type',reason='No exact source attribution captured'))
                    ah=resolve_operative_filter_facts(operative,application_reference=ref).affordable_assessment
                    if facts.affordable_unit_count is not None or facts.affordable_percentage is not None or facts.whole_site_affordable_state!='UNKNOWN':
                        ah_ref=ah.count.application_reference
                        ah_sources=[a for a in apps if a.reference==ah_ref]
                        if len(ah_sources)==1:
                            add(subject,ah_sources[0].id,DIRECT,['existing_affordable_assessment'],count_consumers,
                                'Existing AH assessment reference; no tenure/security/denominator repair','affordable_supporting')
                        else:unresolved.append(dict(subject_key=member.subject_key,field='affordable_assessment',reason='AH reference attribution unresolved'))
                    trigger=[a for a in apps if a.reference==ref] if ref else []
                    if len(trigger)==1:
                        add(subject,trigger[0].id,DIRECT,['opportunity_signal'],['subject_eligibility','dashboard','family_presentation','opportunity_fingerprint'],
                            'Existing detector card exact signal reference; not a substitute for planning_status source','signal_producing')
                    for a in apps:
                        add(subject,a.id,CONTEXT,['operative_selection_and_scope','control_and_phasing_inputs'],
                            ['deterministic_reconciliation','buyer_assessment','spec028_explanation','family_presentation'],
                            'Actual feed/reconciliation and buyer context load all same-site applications; not all are operative')
                    # Explicit citations are candidates only; no new containment or family algorithm.
                    refs={c.reference for a in apps for c in scan_parent_citations(a.proposal).qualifying}
                    for a in apps:
                        if a.reference in refs and a.id not in subject['status_sources']:
                            add(subject,a.id,DISCOVERY,['related_reference_candidate'],['future_change_discovery'],
                                'Existing formatted parent-citation scan + exact same-site reference; no accepted status transfer','related_candidate')
                else:
                    aid=subject['allocation_id'];allocation=session.get(m.LocalPlanSite,aid)
                    coverage=build_allocation_development_coverage(session,[allocation])[aid]
                    links=[]
                    for s in coverage['site_summaries']:
                        disputed=s.relationship_review_status=='needs_confirmation'
                        for a in s.applications:
                            add(subject,a.id,CONTEXT,['allocation_linked_activity_or_disputed_relationship'],
                                ['allocation_coverage','buyer_assessment','allocation_narrative_eligibility'],
                                'Actual allocation coverage site linkage; review='+s.relationship_review_status,
                                'disputed_context' if disputed else 'allocation_context')
                        rep=s.representative_application
                        if rep and not disputed:
                            add(subject,rep.id,DIRECT,['allocation_representative_status','allocation_representative_decision','allocation_representative_decision_issued_date'],
                                ['allocation_narrative_eligibility'],
                                'Actual allocation coverage representative, used by build_allocation_context; not allocation policy status','allocation_representative')
                        links.append(dict(site_id=s.site_id,review_status=s.relationship_review_status,
                                          representative_application_id=rep.id if rep and not disputed else None))
                    allocation_map.append(dict(allocation_id=aid,subject_key=member.subject_key,links=links,
                        summary_record_capture='UNRESOLVED: retained snapshot does not identify stored summary rows'))
                    unresolved.append(dict(subject_key=member.subject_key,field='stored_allocation_narrative',reason='No per-summary IDs/version/context rows in retained snapshot'))
                # Preserve omissions behind privacy projection, rather than assert full control completeness.
                unresolved.append(dict(subject_key=member.subject_key,field='applicant_company_title_and_full_document_provenance',
                    reason='Prior replay deliberately projected/stubbed these inputs; exact source dependency capture unavailable'))
    actual={b['buyer_key']:dict(subjects=sum(b['buyer_key'] in s['buyers'] for s in subjects.values()),
                                visible_subjects=sum(s['buyers'].get(b['buyer_key'],{}).get('family_visible',False) for s in subjects.values()))
            for b in data['buyers']}

ordered=sorted(edges.values(),key=lambda e:(e['subject_key'],e['application_id'],e['dependency_type'],e['supported_fields']))
# Cohort queue is a proposed reference list, never execution authority. Discovery remains separate.
by_app={}
for e in ordered:
    by_app.setdefault(e['application_id'],[]).append(e)
cohorts=[]
from app.pipeline.material_change import _classify_planning_state
for id, dependencies in by_app.items():
    a=raw_apps[id];state=_classify_planning_state(a.get('decision'),a.get('status'))
    substantive=resolve_planning_role(types.SimpleNamespace(**a)) in SUBSTANTIVE_ROLES
    status_edges=[e for e in dependencies if e['dependency_type']==DIRECT and 'planning_status' in e['supported_fields']]
    direct=[e for e in dependencies if e['dependency_type']==DIRECT]
    c=risk_cohort(contradiction=(id==42 and a['reference']=='FUL/355686/26'),
                  decision_sensitive=state in {'not_yet_decided','recommendation_made'},
                  buyer_facing=any(any(v['family_visible'] for v in subjects[e['subject_key']]['buyers'].values()) for e in direct),
                  substantive=substantive,context_gap=not direct,missing_verification=meta_apps[id].get('status_verified_at') is None)
    cohorts.append(dict(application_id=id,reference=a['reference'],council=a['council_code'],
        status_verified_at=meta_apps[id].get('status_verified_at'),direct_subjects=sorted({e['subject_key'] for e in direct}),
        scope='direct_factual_candidate' if direct else 'context_or_discovery_review_only_not_refresh_authority',
        status_supporting=bool(status_edges),**c))
cohorts.sort(key=priority_key)
manifest=dict(version='stage26b-l0-dependencies-v1',evidence_scope='RETAINED_SNAPSHOT_NOT_CURRENT_PRODUCTION_CENSUS',
    evaluation_date=args.evaluation_date,snapshot_utc=snap['utc'],metadata_utc=metadata['utc'],
    code_baseline='1606784115422bf8161f4793a5e9e5aafbe4e1f9',
    application_tree_unchanged_since='a65ee9795fe58449ba826098480c75b7753d5767',
    clock_qualification='Subject-selection date frozen to evaluation_date; freshness adapter uses process UTC now. Source, buyers and relationships remain retained 8 October' ,
    input_hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in {'snapshot':args.snapshot,'metadata':args.metadata,'accepted_replay':args.accepted_replay}.items()},
    summary={**summarise(ordered),'subject_ledger_total':len(subjects),'subjects_without_application_edges':len(subjects)-len({e['subject_key'] for e in ordered})},buyer_coverage=actual,
    subjects=sorted(subjects.values(),key=lambda s:s['subject_key']),dependencies=ordered,
    unresolved=sorted(unresolved,key=lambda u:(u['subject_key'],u['field'])),
    allocations=sorted(allocation_map,key=lambda a:a['allocation_id']),risk_cohorts=cohorts,
    legacy_narratives=dict(total=249,eligible=0,withheld=249,reason='v6-v8 != required v9',
                          per_record_dependency_map='UNRESOLVED: individual summary identities absent',automatic_regeneration_candidates=0),
    audit=dict(query_count=len(queries),statement_kinds=sorted(set(queries)),network_blocked=True,model_calls=0,
               writes_blocked=True,missing_mapped_fields=sorted(missing_fields),
               runtime_seconds=round(time.monotonic()-start,3),safety_checks_passed=safety_checks))
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(manifest,sort_keys=True,indent=2,default=str)+'\n')
print(json.dumps(dict(summary=manifest['summary'],buyer_coverage=actual,audit=manifest['audit'])))
