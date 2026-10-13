import copy,hashlib,json
from pathlib import Path
from unittest.mock import patch
import pytest,yaml
from verification.direct_reference import refresh as r,closure_production as c,batch_production as p,batch as b
from tests.test_stage4_batch_registration import env,SHA

def test_closed_expansion_and_cohorts():
 rows=r.extended_admission();assert len(rows)==512 and len(r.load_manifest())==202
 assert {k:sum(x['council']==k for x in rows) for k in ('bolton','bury','oldham','stockport','tameside','wigan')}==dict(bolton=74,bury=35,oldham=72,stockport=162,tameside=50,wigan=119)
 assert all(r.admitted_row(x['application_id'])==x for x in rows)
 groups=c.reconcile();assert list(map(len,groups))==[17,19]
 assert {x['identity']['application_id'] for x in groups[1]}-{78} <= {x['application_id'] for x in rows}
 assert all(x['identity']['council']!='trafford' for g in groups for x in g)

@pytest.mark.parametrize('mutation',['digest','count','id','council','reference','source_identifier','source_url','collision','extra','unsafe_reference'])
def test_extension_rejects_tampering(mutation,monkeypatch):
 path=Path(r.__file__).with_name('extended-admission.json');raw=path.read_bytes();value=json.loads(raw)
 if mutation=='count':value['rows'].pop()
 elif mutation=='collision':value['rows'][1]['reference']=value['rows'][0]['reference']
 elif mutation=='unsafe_reference':value['rows'][0]['reference']='reference\nprivate@example.invalid'
 elif mutation=='extra':value['rows'][0]['private']='forbidden'
 elif mutation!='digest':
  key={'id':'application_id'}.get(mutation,mutation)
  value['rows'][0][key]={'id':42,'council':'trafford','reference':'','source_identifier':'mismatch','source_url':'https://other.invalid/'}[mutation]
 changed=(json.dumps(value)+'\n').encode()
 original=Path.read_bytes
 monkeypatch.setattr(Path,'read_bytes',lambda self:changed if self==path else original(self))
 if mutation!='digest':monkeypatch.setattr(r,'EXTENDED_SHA256',hashlib.sha256(changed).hexdigest())
 with pytest.raises(Exception):r.extended_admission()

@pytest.mark.parametrize('ctx',c.CONTEXTS)
def test_live_only_exact_registration(ctx):
 w=yaml.load(Path(ctx.workflow).read_text(),Loader=yaml.BaseLoader)
 assert set(w['on'])=={'workflow_dispatch'} and set(w['jobs'])=={'live'} and w['permissions']=={'contents':'read'}
 job=w['jobs']['live'];assert job['environment']=='stage4-production-canary' and job['timeout-minutes']=='10'
 assert job['runs-on']=='ubuntu-24.04'
 assert set(w['on']['workflow_dispatch']['inputs'])=={'reviewed_sha','manifest_sha256','authority'}
 assert ctx.authority in w['on']['workflow_dispatch']['inputs']['authority']['options']
 steps=job['steps'];assert len([s for s in steps if 'secrets.' in str(s)])==1
 assert next(s for s in steps if 'secrets.' in str(s))['env']['BATCH_DATABASE_URL']=='${{ secrets.DATABASE_URL }}'
 assert next(s for s in steps if s.get('uses')=='actions/checkout@v4')['with']['persist-credentials']=='false'
 assert ctx.manifest.digest in steps[0]['run'] and ctx.authority in steps[0]['run']
 assert 'GITHUB_RUN_NUMBER' in steps[0]['run'] and 'GITHUB_RUN_ATTEMPT' in steps[0]['run']
 e=env();e['GITHUB_WORKFLOW_REF']='maxrose26/PropertyAIgent/'+ctx.workflow+'@refs/heads/master'
 assert c.context(e)==ctx and ctx.allow_status_only
 with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']):assert len(p.admit(SHA,ctx.manifest.digest,ctx.authority,e,context=ctx))==ctx.manifest.count
 for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_REF','refs/heads/other')]:
  bad=copy.deepcopy(e);bad[key]=value
  with patch.object(p.subprocess,'check_output',side_effect=[SHA,'']),pytest.raises(ValueError):p.admit(SHA,ctx.manifest.digest,ctx.authority,bad,context=ctx)
 with pytest.raises(ValueError):p.admit(SHA,'0'*64,ctx.authority,e,context=ctx)
 with pytest.raises(ValueError):p.admit(SHA,ctx.manifest.digest,'NOT_AUTHORISED',e,context=ctx)

def test_no_arbitrary_selection_resume_or_writer():
 s=Path(c.__file__).read_text()
 assert 'batch_production.main(c)' in s
 for forbidden in ('create_engine','requests_session','.commit(','.execute(','--resume','--url','--reference','--application'):
  assert forbidden not in s
 with pytest.raises(ValueError):c.context({'GITHUB_WORKFLOW_REF':'alternate'})
