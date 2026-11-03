"""Actual disposable PG17: accepted f792 bytes AND corrected reserve binding.
All credentials, bootstrap grants, clock-skew injection and rows are synthetic.
No source, production route or provider is used. No skips/fallback environment.
"""
import copy,hashlib,importlib,importlib.util,json,sys,time,types
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import psycopg
import pytest
from psycopg import sql
from tests.test_intake_owner_operations_pg import period_world,call,Fault
from tests.test_intake_owner_finite import installed,world,accepted,support,save_to
from tests.test_intake_owner_operations import inputs
from verification.ingestion_storage import intake_owner as actual_op,intake_owner_operations as actual_extra
from verification.ingestion_storage.operational_publication import canonical

FROZEN=Path('tests/fixtures/timing_f792_accepted')
FROZEN_SHA=json.loads((FROZEN/'SHA256.json').read_bytes())

@pytest.fixture(params=['accepted-f792','reserve-corrected'])
def version(request):
 if request.param=='reserve-corrected':return request.param,actual_op,actual_extra
 for n,h in FROZEN_SHA.items():assert hashlib.sha256((FROZEN/n).read_bytes()).hexdigest()==h
 name='verification.ingestion_storage.frozen_f792'
 if name not in sys.modules:
  package=types.ModuleType(name);package.__path__=[str(FROZEN.resolve()),str(Path('verification/ingestion_storage').resolve())];sys.modules[name]=package
 return request.param,importlib.import_module(name+'.intake_owner'),importlib.import_module(name+'.intake_owner_operations')


def bound(version,tmp_path,*,T=None):
 mode,op,extra=version;T=time.time() if T is None else T;b,p=inputs(tmp_path);D=T+2100;E=T+3600
 b.update(valid_until=D,publication_valid_until=E,publication_mint=dict(authority_sha256='a'*64,receipt_sha256='b'*64,expires_at=E),timing_policy=dict(version='SEPARATE_EXPIRY_V1' if mode=='accepted-f792' else 'SEPARATE_EXPIRY_V2_RESERVE',bound_at=T,execution_day=datetime.fromtimestamp(T,ZoneInfo('Europe/London')).date().isoformat()))
 if mode=='reserve-corrected':b['runtime_deadline']=D-185
 p['expires_at']=b.get('runtime_deadline',D);b['period_policy_sha256']=hashlib.sha256(canonical(p)).hexdigest()
 return b,p


def issue(version,c,b,p,saved):
 extra=version[2];state=dict(version='FINITE_INTAKE_PERIOD_V1',state='ARMED_NO_RETRY',binding=b,policy=p)
 return state,lambda:extra.issue_period(c,b,p,state,lambda x:saved.append(copy.deepcopy(x)))


def snapshot(boot):return (actual_op.ledger_sha(boot),boot.execute(actual_op.MEMBERS).fetchall(),actual_op.settings(boot),actual_op.control(boot))


def test_pg17_exact_period_deadlines_and_temporary_privilege_cleanup(period_world,version,tmp_path,record_property):
 boot=period_world['boot'];b,p=bound(version,tmp_path);prior=snapshot(boot);saved=[]
 with support.actor() as c:
  assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()==(False,)
  state,run=issue(version,c,b,p,saved);result=run()
 entry=actual_op.control(boot)['intake_periods'][b['period']]
 assert entry['expires_at']==p['expires_at'] and p['expires_at']<=b['valid_until']<b['publication_valid_until']
 assert boot.execute(actual_op.MEMBERS).fetchall()==prior[1] and actual_op.settings(boot)==prior[2]
 assert actual_op.ledger_sha(boot,prior[3])==prior[0] and result['temporary_issuer']=='REMOVED' and saved[-1]['state']=='COMMIT_ACKNOWLEDGED'
 record_property('pg_version',period_world['server_version']);record_property('actor_superuser',False);record_property('source_mode',version[0])


def test_pg17_role_validity_is_D_not_E_and_independent_close(period_world,version,tmp_path):
 boot=period_world['boot'];op=version[1];b,p=bound(version,tmp_path);before=snapshot(boot);box=[]
 with support.actor() as c:result=op.activate(c,b,save_to(box))
 rows=boot.execute('SELECT rolname,extract(epoch FROM rolvaliduntil) FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname',(list(op.ROLES),)).fetchall()
 assert rows and all(abs(float(r[1])-b['valid_until'])<0.00001 and float(r[1])<b['publication_valid_until'] for r in rows)
 assert box[0]['binding']==b and result['outcome']=='COMMIT_ACKNOWLEDGED'
 with support.actor() as c:closed=op.close(c,box[0],save_to(box))
 assert closed['runtime_access']=='DISABLED' and closed['sessions']=='ABSENT' and snapshot(boot)==before


@pytest.mark.parametrize('delta',[-1,1,185])
def test_pg17_wrong_exact_period_deadline_refuses_without_effect(period_world,version,tmp_path,delta):
 boot=period_world['boot'];b,p=bound(version,tmp_path);p['expires_at']+=delta;b['period_policy_sha256']=hashlib.sha256(canonical(p)).hexdigest();prior=snapshot(boot)
 with support.actor() as c:
  _,run=issue(version,c,b,p,[])
  with pytest.raises(Exception):run()
 assert snapshot(boot)==prior


@pytest.mark.parametrize('kind',['short_E','cross_midnight'])
def test_pg17_insufficient_token_or_day_margin_no_effect(period_world,version,tmp_path,kind):
 boot=period_world['boot'];b,p=bound(version,tmp_path);prior=snapshot(boot)
 if kind=='short_E':b['publication_valid_until']=b['valid_until']-1;b['publication_mint']['expires_at']=b['publication_valid_until']
 else:
  from datetime import timedelta
  now=datetime.now(ZoneInfo('Europe/London'));T=datetime.combine(now.date()+timedelta(days=1),datetime.min.time(),ZoneInfo('Europe/London')).timestamp()-2099;b,p=bound(version,tmp_path,T=T)
 with support.actor() as c:
  _,run=issue(version,c,b,p,[])
  with pytest.raises(Exception):run()
 assert snapshot(boot)==prior


@pytest.mark.parametrize('operation',['period','activation'])
def test_pg17_actual_server_clock_refuses_setup_boundary_before_grant(period_world,version,tmp_path,monkeypatch,operation):
 boot=period_world['boot'];server=float(boot.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0]);b,p=bound(version,tmp_path,T=server-600.1);prior=snapshot(boot)
 # Only the OWNER clock is skewed. The SQL clock_timestamp query remains real.
 monkeypatch.setattr(time,'time',lambda:server-1.0)
 with support.actor() as c:
  with pytest.raises(Exception):
   if operation=='period':issue(version,c,b,p,[])[1]()
   else:version[1].activate(c,b,lambda _:None)
 assert snapshot(boot)==prior


@pytest.mark.parametrize('fault',['sql','privilege','temporary','lost_commit'])
def test_pg17_deadline_transaction_rollback_cleanup_and_uncertain_commit(period_world,version,tmp_path,fault):
 boot=period_world['boot'];b,p=bound(version,tmp_path);prior=snapshot(boot);saved=[]
 with support.actor() as c:
  journal,run=issue(version,Fault(c,fault),b,p,saved)
  with pytest.raises(Exception):run()
 assert boot.execute(actual_op.MEMBERS).fetchall()==prior[1] and actual_op.settings(boot)==prior[2]
 if fault=='lost_commit':
  assert actual_op.control(boot)['intake_periods'][b['period']]['expires_at']==p['expires_at'] and journal['state']=='COMMIT_INTENT_NO_RETRY'
  # No second connection/issuance. A consumed journal refuses immediately.
  with pytest.raises(Exception):version[2].issue_period(c,b,p,journal,lambda _:None)
 else:assert snapshot(boot)==prior


def test_pg17_lost_activation_commit_retains_independent_closure(period_world,version,tmp_path):
 boot=period_world['boot'];b,p=bound(version,tmp_path);prior=snapshot(boot);box=[]
 with support.actor() as c:
  with pytest.raises(psycopg.OperationalError):version[1].activate(Fault(c,'lost_commit'),b,save_to(box))
 assert box and box[0]['state']=='ARMED_BEFORE_ACTIVATION'
 with support.actor() as c:result=version[1].close(c,box[0],save_to(box))
 assert result['runtime_access']=='DISABLED' and result['sessions']=='ABSENT' and snapshot(boot)==prior
