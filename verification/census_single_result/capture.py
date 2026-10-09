"""Offline single-result census design. No DB connector or execution command."""
import argparse
import hashlib
import json
import re
from pathlib import Path

VERSION = 'census-single-result-v1'
GM = "'bolton','bury','manchester','oldham','rochdale','salford','stockport','tameside','trafford','wigan'"
LIMITS = {'sites':1000,'applications':3000,'scheme_intelligence':1500,'buyers':20,
 'buyer_mandates':20,'local_plan_sites':2000,'local_plans':100,'local_plan_councils':300,
 'allocation_site_relationships':5000,'control_relationships':5000,'councils':50,
 'workspaces':20,'documents':10000,'allocation_intelligence_summaries':300,
 'companies':1000,'applicant_intelligences':1000}
# Planning proposal/location are already-approved public factual input, not document bodies.
FIELDS = {
 'sites':'id,council_code,canonical_address,display_address,postcode,build_status,build_status_checked_at,epc_dwellings_found,excluded',
 'applications':'id,site_id,council_code,reference,alternative_reference,address,proposal,application_type,application_category,status,decision,decision_issued_date,application_received,application_validated,expected_decision_date,estimated_unit_count,unit_confirmation_status,site_link_method,site_link_confidence,status_verified_at,summary_url',
 'scheme_intelligence':'id,application_id,total_units,total_units_final,affordable_units,affordable_units_final,private_units,private_units_final,affordable_percentage,affordable_percentage_final,affordable_tenure_split,affordable_tenure_split_final,development_type,housing_typology,specialist_housing_type,housing_confidence,affordable_data_status,application_context_status,affordable_classification_confidence,unit_total_check,unit_total_difference,unit_reconciliation_status,data_quality_status,formal_decision_outstanding,affordable_housing_status,core_intelligence_complete',
 'buyers':'id,workspace_id,buyer_key,status',
 'buyer_mandates':'id,buyer_id,mandate_key,status,target_unit_min,target_unit_max,scale_metric,accepted_planning_states,treats_no_activity_as_positive,large_allocation_is_self_qualifying,specialist_development_is_exclusion,wholly_affordable_is_exclusion,below_minimum_scale_is_exclusion,geography_scope,geography_councils,acquisition_types,development_state_appetite,control_appetite,matching_fingerprint',
 'local_plan_sites':'id,council_code,local_plan_id,site_name,policy_reference,minimum_dwellings,maximum_capacity,indicative_capacity,intended_use,matched_site_id,plan_status,allocation_status,raw_allocation_status,category,green_belt_status,review_status,duplicate_classification,progression_signal,match_confidence,site_area_hectares,latitude,longitude,plan_name,source_document_url,source_page,updated_at',
 'local_plans':'id,council_code,plan_name,status,five_year_supply_years,last_checked',
 'local_plan_councils':'id,local_plan_id,council_code,role,is_lead_authority',
 'allocation_site_relationships':'id,allocation_id,site_id,review_status',
 'control_relationships':'id,site_id,application_id,role,entity_type,company_id,confidence,evidence_category,evidence_document_id,review_status',
 'councils':'code,name,base_url,date_field_mode,doc_system',
 'workspaces':'id,status',
 'documents':'id,application_id,doc_type,text_extracted,content_hash',
 'allocation_intelligence_summaries':'id,allocation_id,prompt_version,context_fingerprint,generated_at,status',
 'companies':'id',
 'applicant_intelligences':'id,company_id,identity_type,primary_type,primary_type_confidence,is_spv,generated_at,context_fingerprint,prompt_version,status',
}
KEYS = {t:('code' if t=='councils' else 'id') for t in FIELDS}
FK = [('applications','site_id','sites'),('scheme_intelligence','application_id','applications'),
 ('buyers','workspace_id','workspaces'),('buyer_mandates','buyer_id','buyers'),
 ('local_plan_sites','local_plan_id','local_plans'),('local_plan_sites','matched_site_id','sites'),
 ('local_plan_councils','local_plan_id','local_plans'),
 ('allocation_site_relationships','allocation_id','local_plan_sites'),
 ('allocation_site_relationships','site_id','sites'),('control_relationships','site_id','sites'),
 ('control_relationships','application_id','applications'),('control_relationships','company_id','companies'),
 ('control_relationships','evidence_document_id','documents'),('documents','application_id','applications'),
 ('allocation_intelligence_summaries','allocation_id','local_plan_sites'),
 ('applicant_intelligences','company_id','companies')]

def design(mode='full'):
    if mode not in ('full','canary'): raise ValueError('Unsupported mode')
    bounds = dict(LIMITS)
    if mode=='canary': bounds = {t:min(n,200) for t,n in bounds.items()}
    # Retained IDs select a test cohort, never confer planning-source authority.
    site_filter = 'x.id IN (25,28,254,58,96,62)' if mode=='canary' else 'TRUE'
    alloc_filter = ('(x.matched_site_id IN (25,28,254,58,96,62) OR x.id IN '
       '(SELECT r.allocation_id FROM public.allocation_site_relationships r WHERE r.site_id IN (25,28,254,58,96,62)) '
       'OR x.id=(SELECT min(z.allocation_id) FROM public.allocation_intelligence_summaries z '
       'JOIN public.local_plan_sites p ON p.id=z.allocation_id WHERE p.council_code IN ('+GM+')))' if mode=='canary' else 'TRUE')
    where = {
     'local_plan_sites':f'x.council_code IN ({GM}) AND {alloc_filter}',
     'sites':f'x.council_code IN ({GM}) AND ({site_filter}) AND (NOT coalesce(x.excluded,false) OR x.id IN (SELECT a.matched_site_id FROM s_local_plan_sites a) OR x.id IN (SELECT r.site_id FROM public.allocation_site_relationships r WHERE r.allocation_id IN (SELECT a.id FROM s_local_plan_sites a)))',
     'applications':'x.site_id IN (SELECT id FROM s_sites)',
     'scheme_intelligence':'x.application_id IN (SELECT id FROM s_applications)',
     'buyers':"x.workspace_id=1 AND x.status='active'",
     'buyer_mandates':"x.buyer_id IN (SELECT id FROM s_buyers) AND x.status='active'",
     'local_plans':'x.id IN (SELECT local_plan_id FROM s_local_plan_sites)',
     'local_plan_councils':'x.local_plan_id IN (SELECT id FROM s_local_plans)',
     'allocation_site_relationships':'x.allocation_id IN (SELECT id FROM s_local_plan_sites)',
     'control_relationships':'(x.site_id IN (SELECT id FROM s_sites) OR x.application_id IN (SELECT id FROM s_applications))',
     'councils':'x.code IN (SELECT council_code FROM s_sites UNION SELECT council_code FROM s_local_plan_sites)',
     'workspaces':'x.id IN (SELECT workspace_id FROM s_buyers)',
     'documents':'x.application_id IN (SELECT id FROM s_applications)',
     'allocation_intelligence_summaries':'x.allocation_id IN (SELECT id FROM s_local_plan_sites)',
     'companies':'x.id IN (SELECT company_id FROM s_control_relationships)',
     'applicant_intelligences':'x.company_id IN (SELECT id FROM s_companies)',
    }
    order=['local_plan_sites','sites','applications','scheme_intelligence','buyers','buyer_mandates',
      'local_plans','local_plan_councils','allocation_site_relationships','control_relationships',
      'councils','workspaces','documents','allocation_intelligence_summaries','companies','applicant_intelligences']
    ctes=[]; manifest=[]
    for t in order:
        columns=['x.'+f for f in FIELDS[t].split(',')]
        if t=='applications': columns.append("(x.applicant_name_raw IS NOT NULL AND x.applicant_name_raw<>'') AS applicant_present")
        if t=='control_relationships': columns.append("(x.title_number IS NOT NULL AND x.title_number<>'') AS title_present")
        if t=='allocation_intelligence_summaries': columns += ["(coalesce(x.headline,'')<>'') AS headline_present","(coalesce(x.overview,'')<>'') AS overview_present"]
        select=f"SELECT {','.join(columns)} FROM public.{t} x WHERE {where[t]} ORDER BY x.{KEYS[t]} LIMIT {bounds[t]+1}"
        ctes.append(f's_{t} AS MATERIALIZED ({select})')
        manifest.append(dict(section=t,table='public.'+t,columns=columns,predicate=where[t],key=KEYS[t],limit_plus_one=bounds[t]+1,timeout_seconds=5,
          index_evidence='ORM primary key (councils.code / other id); deployed index and FK access paths UNVERIFIED',assembly_key=[t,KEYS[t]]))
    branches=[]
    for t in order:
        branches.append(f"SELECT '{t}'::text AS record_type,'DATA'::text AS row_kind,a.{KEYS[t]}::text AS record_id,to_jsonb(a) AS payload FROM s_{t} a")
        branches.append(f"SELECT '{t}'::text,'CONTROL'::text,NULL::text,jsonb_build_object('count',count(a.{KEYS[t]}),'limit',{bounds[t]},'overflow',count(a.{KEYS[t]})>{bounds[t]}) FROM s_{t} a")
    ctes.append('rows AS MATERIALIZED ('+'\nUNION ALL\n'.join(branches)+')')
    ctes.append("safety AS MATERIALIZED (SELECT current_setting('transaction_read_only') AS read_only,current_setting('transaction_isolation') AS isolation,current_setting('statement_timeout') AS statement_timeout,current_setting('lock_timeout') AS lock_timeout,pg_current_snapshot()::text AS snapshot,statement_timestamp() AS captured_at,pg_backend_pid() AS backend_pid)")
    ctes.append("budget AS MATERIALIZED (SELECT coalesce(sum(octet_length(payload::text)+octet_length(record_type)+coalesce(octet_length(record_id),0)+64),0) AS logical_bytes,count(record_type) AS rows FROM rows)")
    final="SELECT record_type,row_kind,record_id,payload FROM rows\nUNION ALL\nSELECT '__capture','CONTROL',NULL::text,to_jsonb(s)||jsonb_build_object('version','"+VERSION+"','mode','"+mode+"','logical_bytes',b.logical_bytes,'row_count',b.rows,'byte_limit',10000000,'row_limit',"+str(sum(v+1 for v in bounds.values())+len(bounds))+",'overflow',b.logical_bytes>10000000) FROM safety s CROSS JOIN budget b\nORDER BY record_type,row_kind,record_id"
    sql='WITH '+',\n'.join(ctes)+'\n'+final+';\n'
    wrapper="BEGIN;\nSET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;\nSET LOCAL statement_timeout='5s';\nSET LOCAL lock_timeout='2s';\n"+sql+'ROLLBACK;\n'
    return sql,wrapper,dict(version=VERSION,mode=mode,sections=manifest,bounds=bounds,byte_limit=10000000,runtime_limit=60,
      statements=6,qualifications=['document-derived control/phasing excluded','fuzzy identity resolution excluded','canonical narrative hash parity unresolved','capture COMPLETE is not dependency-census COMPLETE'],sql_sha256=hashlib.sha256(sql.encode()).hexdigest())

def assemble(rows, *, encoded_bytes, elapsed_seconds):
    if encoded_bytes>10000000 or elapsed_seconds>60: raise ValueError('Capture byte/runtime overflow')
    capture=[r for r in rows if r['record_type']=='__capture']
    if len(capture)!=1 or capture[0]['row_kind']!='CONTROL': raise ValueError('Missing/duplicate capture control')
    c=capture[0]['payload']
    if c.get('version')!=VERSION or c.get('mode') not in ('canary','full'): raise ValueError('Unknown manifest')
    if c.get('read_only')!='on' or c.get('isolation')!='repeatable read': raise ValueError('Unsafe transaction')
    if c.get('statement_timeout')!='5s' or c.get('lock_timeout')!='2s' or not c.get('snapshot') or not c.get('captured_at') or not c.get('backend_pid'): raise ValueError('Missing safety evidence')
    if c.get('overflow') is not False or c.get('logical_bytes',10000001)>10000000: raise ValueError('Overflow')
    _,_,manifest=design(c['mode']);bounds=manifest['bounds']
    sections={t:[] for t in FIELDS};controls={}
    for r in rows:
        t=r['record_type']
        if t=='__capture': continue
        if t not in sections: raise ValueError('Unknown section')
        if r['row_kind']=='CONTROL':
            if t in controls: raise ValueError('Duplicate control')
            controls[t]=r['payload']
        elif r['row_kind']=='DATA':
            if str(r['payload'].get(KEYS[t]))!=r['record_id']: raise ValueError('Key mismatch')
            allowed=set(FIELDS[t].split(','))|({'applicant_present'} if t=='applications' else {'title_present'} if t=='control_relationships' else {'headline_present','overview_present'} if t=='allocation_intelligence_summaries' else set())
            if set(r['payload'])!=allowed: raise ValueError('Projection mismatch')
            sections[t].append(r['payload'])
        else: raise ValueError('Unknown row kind')
    if set(controls)!=set(FIELDS): raise ValueError('Missing section')
    if c.get('row_count')!=len(rows)-1: raise ValueError('Total row mismatch')
    indexes={}
    for t,records in sections.items():
        ctr=controls[t];keys=[r[KEYS[t]] for r in records]
        if len(keys)!=len(set(keys)): raise ValueError('Duplicate key')
        if ctr.get('count')!=len(keys) or ctr.get('limit')!=bounds[t] or ctr.get('overflow') is not False or len(keys)>bounds[t]: raise ValueError('Count/overflow mismatch')
        indexes[t]=set(keys)
    unresolved=[]
    for table,field,parent in FK:
        for r in sections[table]:
            if r[field] is not None and r[field] not in indexes[parent]:
                # Cross-scope context is never silently treated as no relationship.
                unresolved.append(dict(table=table,id=r[KEYS[table]],field=field,parent=parent,value=r[field],qualification='UNRESOLVED_OUTSIDE_CAPTURE_SCOPE'))
    for t in ('buyers','buyer_mandates'):
        if any(u['table']==t for u in unresolved): raise ValueError('Unresolved buyer isolation relationship')
    if any(b['workspace_id']!=1 or b['status']!='active' for b in sections['buyers']): raise ValueError('Buyer isolation mismatch')
    if any(m['status']!='active' for m in sections['buyer_mandates']): raise ValueError('Inactive mandate')
    return dict(retrieval_state='COMPLETE',dependency_census_state='QUALIFIED',data=sections,unresolved=unresolved,
      qualifications=manifest['qualifications'],capture=c)

def preserve_dependencies(edges):
    kinds={'DIRECT_FACTUAL_DEPENDENCY','CONTEXT_DEPENDENCY','DISCOVERY_RELATIONSHIP'}
    if any(e.get('dependency_type') not in kinds for e in edges): raise ValueError('Unknown dependency type')
    return {kind:[e for e in edges if e['dependency_type']==kind] for kind in sorted(kinds)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    for mode in ('canary','full'):
        sql,wrapper,manifest=design(mode)
        (a.output/(mode+'.sql')).write_text(wrapper)
        (a.output/(mode+'-manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
