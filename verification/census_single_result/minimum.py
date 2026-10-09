"""Offline minimum structural freshness census; no verifier or current buyer replay."""
import argparse
import csv
import io
import json
from pathlib import Path
import capture as v1

VERSION = 'census-minimum-v2'
COHORT = (25,28,254,58,179,281)
FIELDS = {
 'sites':'id,council_code,excluded',
 'applications':'id,site_id,council_code,reference,proposal,application_category,status,decision,decision_issued_date,status_verified_at,summary_url,site_link_method',
 'buyers':'id,workspace_id,status',
 'buyer_mandates':'id,buyer_id,status,matching_fingerprint',
 'local_plan_sites':'id,council_code,local_plan_id,matched_site_id,plan_status,allocation_status,review_status',
 'local_plans':'id,council_code,status',
 'local_plan_councils':'id,local_plan_id,council_code',
 'allocation_site_relationships':'id,allocation_id,site_id,review_status',
 'councils':'code',
 'workspaces':'id,status',
 'allocation_intelligence_summaries':'id,allocation_id,prompt_version,context_fingerprint,generated_at,status',
}
KEYS = {t:v1.KEYS[t] for t in FIELDS}
FK = [item for item in v1.FK if item[0] in FIELDS and item[2] in FIELDS]
LIMITS = {t:v1.LIMITS[t] for t in FIELDS}
QUALIFICATIONS = [
 'Structural candidate superset, not current buyer-facing subject census',
 'Active buyers/mandates do not establish subject relevance or C2 priority',
 'Direct/context/discovery attribution requires accepted evidence; not inferred from site membership',
 'No CountAssessment, control or document-derived phasing replay',
 'Stored context fingerprint/version captured; canonical narrative eligibility not recomputed',
 'retrieval COMPLETE never certifies dependency census COMPLETE',
]

def design(mode='full'):
    if mode not in ('full','canary'): raise ValueError('Unsupported mode')
    bounds=dict(LIMITS)
    if mode=='canary':
        bounds={t:min(n,20) for t,n in bounds.items()}
        bounds.update(applications=100,allocation_site_relationships=50)
    cohort=','.join(map(str,COHORT))
    site_pred=f'x.id IN ({cohort})' if mode=='canary' else 'TRUE'
    alloc_pred=(f'(x.matched_site_id IN ({cohort}) OR x.id IN '
      f'(SELECT r.allocation_id FROM public.allocation_site_relationships r WHERE r.site_id IN ({cohort})) '
      'OR x.id=(SELECT min(z.allocation_id) FROM public.allocation_intelligence_summaries z '
      f'JOIN public.local_plan_sites p ON p.id=z.allocation_id WHERE p.council_code IN ({v1.GM})))' if mode=='canary' else 'TRUE')
    where={
      'local_plan_sites':f'x.council_code IN ({v1.GM}) AND {alloc_pred}',
      'sites':f'x.council_code IN ({v1.GM}) AND ({site_pred}) AND (NOT coalesce(x.excluded,false) OR x.id IN (SELECT a.matched_site_id FROM s_local_plan_sites a) OR x.id IN (SELECT r.site_id FROM public.allocation_site_relationships r WHERE r.allocation_id IN (SELECT a.id FROM s_local_plan_sites a)))',
      'applications':'x.site_id IN (SELECT id FROM s_sites)',
      'buyers':"x.workspace_id=1 AND x.status='active'",
      'buyer_mandates':"x.buyer_id IN (SELECT id FROM s_buyers) AND x.status='active'",
      'local_plans':'x.id IN (SELECT local_plan_id FROM s_local_plan_sites)',
      'local_plan_councils':'x.local_plan_id IN (SELECT id FROM s_local_plans)',
      'allocation_site_relationships':'x.allocation_id IN (SELECT id FROM s_local_plan_sites)',
      'councils':'x.code IN (SELECT council_code FROM s_sites UNION SELECT council_code FROM s_local_plan_sites)',
      'workspaces':'x.id IN (SELECT workspace_id FROM s_buyers)',
      'allocation_intelligence_summaries':'x.allocation_id IN (SELECT id FROM s_local_plan_sites)',
    }
    order=['local_plan_sites','sites','applications','buyers','buyer_mandates','local_plans',
      'local_plan_councils','allocation_site_relationships','councils','workspaces','allocation_intelligence_summaries']
    sql,wrapper,manifest=v1.render_query(mode,bounds,FIELDS,KEYS,where,order,VERSION)
    manifest['qualifications']=QUALIFICATIONS
    manifest['cohort']=list(COHORT) if mode=='canary' else None
    manifest['purpose']='Qualified structural planning-reference selection; no acquisition replay or ranking'
    return sql,wrapper,manifest

def assemble(rows, *, encoded_bytes,elapsed_seconds):
    return v1.validate_rows(rows,encoded_bytes=encoded_bytes,elapsed_seconds=elapsed_seconds,
      fields=FIELDS,keys=KEYS,fk=FK,manifest_fn=design,version=VERSION)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--assemble',type=Path)
    p.add_argument('--elapsed-seconds',type=float)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.assemble:
        raw=a.assemble.read_bytes()
        if len(raw)>10000000 or a.elapsed_seconds is None or not 0<=a.elapsed_seconds<=60:
            raise ValueError('Input byte/runtime evidence unavailable or overflowing')
        if a.assemble.suffix.lower()=='.csv':
            rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            for r in rows:r['payload']=json.loads(r['payload']);r['record_id']=r['record_id'] or None
        else:rows=json.loads(raw)
        result=assemble(rows,encoded_bytes=len(raw),elapsed_seconds=a.elapsed_seconds)
        path=a.output/'qualified-capture.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(path)
    else:
        for mode in ('canary','full'):
            _,wrapper,manifest=design(mode)
            (a.output/(mode+'.sql')).write_text(wrapper)
            (a.output/(mode+'-manifest.json')).write_text(json.dumps(manifest,indent=2)+'\n')
