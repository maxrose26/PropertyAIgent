import copy
import pytest
from verification.ingestion_storage.tameside_candidate import validate_job,EXPIRY

def case():
 now=EXPIRY-3000
 p={'execution_binding':{'revision':'a'*40},'hostaddr':'18.169.28.97','route':'POOLER','expires_at':now+1800}
 e={'RENDER_SERVICE_ID':'crn-d9sv93vavr4c73f98rb0','RENDER_GIT_COMMIT':'a'*40,'INGESTION_WORKER_DATABASE_URL':'fixture-worker','INGESTION_EFFECT_DATABASE_URL':'fixture-effect'}
 return now,p,e

def test_fixed_restricted_job():
 now,p,e=case();assert validate_job(p,hostaddr=p['hostaddr'],access_deadline=now+1985,now=now,environ=e)

@pytest.mark.parametrize('change',['service','build','address','short','long','expired','infinite','owner','missing','reserve'])
def test_refuse_before_runtime(change):
 now,p,e=case();address=p['hostaddr'];deadline=now+1985
 if change=='service':e['RENDER_SERVICE_ID']='owner-service'
 if change=='build':e['RENDER_GIT_COMMIT']='b'*40
 if change=='address':address='192.0.2.1'
 if change=='short':deadline=now+960
 if change=='long':deadline=now+2101
 if change=='expired':p['expires_at']=now-1
 if change=='infinite':deadline=float('inf')
 if change=='owner':e['DATABASE_URL']='MUST_NOT_ESCAPE'
 if change=='missing':del e['INGESTION_EFFECT_DATABASE_URL']
 if change=='reserve':p['expires_at']=deadline
 with pytest.raises(ValueError):validate_job(p,hostaddr=address,access_deadline=deadline,now=now,environ=e)
