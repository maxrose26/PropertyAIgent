"""Pure owner-local binding assembly; no network, key, Vault or phase execution."""
import argparse,hashlib,json,os,re,sys,time,shlex,stat
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from . import intake_owner as owner,intake_owner_operations as extra
from .operational_publication import canonical

ROOT=Path('/home/maxrose26/stage4-owner/b-successor-release-20261103')
MINT_RESULT=Path('/home/maxrose26/.local/share/propertyaigent/b-publication-app/mint-evidence-expired-unused-successor-01/result.json')
AUTHORITY='ed07a6fb15ff6b0c8308f0ef28bf1b2e3eedc98159a538b87d7b1891d45bbe74'
STATIC_SHA='436a0490bcd5cb8e9473a43f238850090051983713472498a7316654f9f93470'
FRESH_PHRASE='FRESH_B_RELEASE_OBSERVATIONS_CONFIRMED_NOW'

def require(v):
 if not v:raise ValueError('LOCAL_BINDING_REFUSED')

def read(path):
 require(not path.is_symlink() and path.is_file() and path.stat().st_size<=32768)
 return json.loads(path.read_bytes())

def static():
 raw=(ROOT/'STATIC-RELEASE.json').read_bytes();require(hashlib.sha256(raw).hexdigest()==STATIC_SHA)
 s=json.loads(raw);require(hashlib.sha256((ROOT/'B-COMMAND.txt').read_bytes()).hexdigest()==s['B_command_sha256']);return s

def build(s,r,observed,*,now=None):
 now=time.time() if now is None else now
 require(r.get('status')=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and r.get('mint_outcome')=='MINTED' and r.get('retry') is False and r.get('authority_sha256')==AUTHORITY)
 require(r.get('owner_process',{}).get('client_closed') is True and r['owner_process'].get('exit_code')==0 and r['owner_process'].get('reason') is None)
 require(type(r.get('expiry')) in (int,float) and re.fullmatch('[a-f0-9]{64}',r.get('receipt_sha256','')))
 expiry=r['expiry'];require(datetime.fromisoformat(r['expires_at'].replace('Z','+00:00')).timestamp()==expiry)
 local=datetime.fromtimestamp(now,ZoneInfo('Europe/London'));require(local.date().isoformat()==s['execution_day'])
 b=json.loads(json.dumps(s['binding_fields']));b.update(valid_until=expiry,publication_valid_until=expiry,publication_mint=dict(authority_sha256=AUTHORITY,receipt_sha256=r['receipt_sha256'],expires_at=expiry))
 b['inherited_boundary']=dict(service_id='crn-d9sv93vavr4c73f98rb0',env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,observed_at=observed)
 policy=json.loads(json.dumps(s['policy_fields']));midnight=datetime(2026,11,4,tzinfo=ZoneInfo('Europe/London')).timestamp();policy['expires_at']=min(expiry,midnight)
 b['period_policy_sha256']=hashlib.sha256(canonical(policy)).hexdigest()
 # Preview uses explicit within-window time only for offline validation. Real
 # freeze passes actual wall time and must fit all unchanged opening guards.
 owner.validate_binding(b,opening=True,now=now);extra.validate_policy(b,policy,now=now)
 return b,policy

def build_v2(s,r,bound_at):
 # Receipt verification remains unchanged, without applying the legacy ageing gate.
 require(s.get('version')=='FINITE_TIMING_V2_STATIC')
 require(r.get('status')=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and r.get('mint_outcome')=='MINTED' and r.get('retry') is False and r.get('authority_sha256')==AUTHORITY)
 c=r.get('owner_process',{});require(c.get('client_closed') is True and c.get('exit_code')==0 and c.get('reason') is None)
 require(type(r.get('expiry')) in (int,float) and re.fullmatch('[a-f0-9]{64}',r.get('receipt_sha256','')) and datetime.fromisoformat(r['expires_at'].replace('Z','+00:00')).timestamp()==r['expiry'])
 from datetime import timedelta
 day=datetime.fromtimestamp(bound_at,ZoneInfo('Europe/London'))
 check(day.date().isoformat()==s.get('execution_day'),'TIMING_RELEASE_UNBOUND')
 midnight=datetime.combine(day.date()+timedelta(days=1),datetime.min.time(),ZoneInfo('Europe/London')).timestamp()
 deadline=bound_at+2100
 check(deadline<=r['expiry'] and deadline<=midnight,'FULL_35_MINUTE_MARGIN_REQUIRED')
 b=json.loads(json.dumps(s['binding_fields']));b.pop('inherited_boundary',None)
 b.update(publication_mint_journal_path=s['mint_journal_path'],valid_until=deadline,publication_valid_until=r['expiry'],publication_mint=dict(authority_sha256=AUTHORITY,receipt_sha256=r['receipt_sha256'],expires_at=r['expiry']),timing_policy=dict(version='SEPARATE_EXPIRY_V2_RESERVE',bound_at=bound_at,execution_day=s['execution_day']),retained_deployment=s['artifact']['deployment'],release_root=str(ROOT),submission_intent_path=str(ROOT/'submission.intent.json'))
 policy=json.loads(json.dumps(s['policy_fields']));b['runtime_deadline']=deadline-185;policy['expires_at']=b['runtime_deadline'];b['period_policy_sha256']=hashlib.sha256(canonical(policy)).hexdigest()
 owner.validate_binding(b,opening=True,now=bound_at);extra.validate_policy(b,policy,now=bound_at)
 return b,policy

TIMING_ROOT=Path('/home/maxrose26/stage4-owner/b-timing-amendment-20261103-owner/release')
TIMING_STATIC_SHA='680fe28d32e12ae7d8b4b173c802693284c492d22d707befe307fb8116ceb3da'
def use_timing_release():
 global ROOT,MINT_RESULT,STATIC_SHA,LAUNCHERS
 ROOT=TIMING_ROOT;STATIC_SHA=TIMING_STATIC_SHA;LAUNCHERS=TIMING_ROOT.parent
 raw=(ROOT/'STATIC-RELEASE.json').read_bytes();check(hashlib.sha256(raw).hexdigest()==STATIC_SHA,'TIMING_RELEASE_UNBOUND')
 s=json.loads(raw)
 check(s.get('version')=='FINITE_TIMING_V2_STATIC' and type(s.get('execution_day')) is str and re.fullmatch(r'\d{4}-\d\d-\d\d',s['execution_day']) and s.get('mint_result_path'),'TIMING_RELEASE_UNBOUND')
 MINT_RESULT=Path(s['mint_result_path'])


def record_observation(operation):
 b,_,_=frozen_binding(opening=False);owner.validate_binding(b,opening=True)
 check('timing_policy' in b and operation in ('HANDOFF','SUBMISSION'),'OPERATION_OBSERVATION_REQUIRED')
 # Every record is exclusive; renewing a read never renews D or mutation authority.
 name=operation.lower()+'-observation.json'
 check(not (ROOT/name).exists() and not (ROOT/name).is_symlink(),'OBSERVATION_ALREADY_RECORDED')
 if operation=='SUBMISSION':
  bh=hashlib.sha256((ROOT/'owner-binding.json').read_bytes()).hexdigest()
  check(owner_receipt('handoff',b,bh) is not None,'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
 print('Read-only '+operation+' checks NOW: exact suspended service/artifact/revision, no current jobs/builds, other activity stopped, no linked groups or secret files, expected harmless settings. Differences refuse. No values or credentials.',file=sys.stderr)
 phrase='CONFIRM_FRESH_'+operation+'_OBSERVATION_NOW'
 check(input(phrase+': ').strip()==phrase,'FRESH_CONFIRMATION_REQUIRED')
 x=dict(version='FINITE_OPERATION_OBSERVATION_V1',operation=operation,binding_sha256=hashlib.sha256(canonical(b)).hexdigest(),service_id=b['render_profile']['service_id'],observed_at=time.time(),env_groups=[],secret_files=[],inherited_credential_names=[],reviewed=True,no_current_work=True,other_activity_stopped=True,deployment_id=b['retained_deployment'],revision=b['execution_binding']['revision'],suspended=True)
 from .intake_owner_io import operation_observation
 operation_observation(b,x,operation);save(name,x)
 return dict(status='IMMUTABLE_OPERATION_OBSERVATION_SAVED',operation=operation,deadline=b['valid_until'],provider_calls=0)


def save(name,value):
 raw=canonical(value);fd=os.open(ROOT/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 return hashlib.sha256(raw).hexdigest()


# Local prerequisite/readback checks only. No phase is executed here.
PRIVATE=Path('/home/maxrose26/.local/share/propertyaigent/b-publication-app')
LAUNCHERS=Path('/home/maxrose26/stage4-owner/b-phase-order-correction-20261103-owner')
AUTHORITY_PATH='/home/maxrose26/stage4-owner/b-github-get-readonly-20261103/authority-client-id-corrected.json'
AUTHORITY_RAW='28a039e7dae4358055113fd830ad3ca2e3d742c6060d43c5b46f1c394e079096'
PREPARATION_CODES=frozenset(('BINDING_MISSING_RUN_FREEZE','FROZEN_PROOF_REQUIRED','FROZEN_BINDING_MISMATCH',
 'FROZEN_OBSERVATION_EXPIRED','FREEZE_INCOMPLETE','RELEASE_WINDOW_CLOSED','PREPARATION_UNKNOWN',
 'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY','PHASE_ORDER_REFUSED','LOCAL_RECEIPT_UNBOUND','NEXT_SUBMISSION_REVIEW_REQUIRED',
 'MINT_RESULT_REQUIRED','MINT_REVIEW_REQUIRED','FREEZE_ALREADY_EXISTS_NO_RETRY','FRESH_CONFIRMATION_REQUIRED','PHASE_ARGUMENTS_REFUSED','RELEASE_CLOSED_EXPLICIT_REBIND_REQUIRED','TIMING_RELEASE_UNBOUND','FULL_35_MINUTE_MARGIN_REQUIRED','USE_BIND_FOR_SEPARATE_EXPIRY','OPERATION_OBSERVATION_REQUIRED','OBSERVATION_ALREADY_RECORDED'))
class PreparationError(Exception):
 def __init__(self,code):self.code=code if code in PREPARATION_CODES else 'PREPARATION_UNKNOWN';super().__init__(self.code)
def check(value,code):
 if not value:raise PreparationError(code)
def private_json(path,code):
 try:
  check(not path.is_symlink() and path.is_file(),code);st=path.stat()
  check(stat.S_IMODE(st.st_mode)==0o600 and st.st_uid==os.getuid() and st.st_nlink==1 and st.st_size<=32768,code)
  return json.loads(path.read_bytes())
 except PreparationError:raise
 except BaseException:raise PreparationError(code) from None

def frozen_binding(*,now=None,opening=True):
 now=time.time() if now is None else now
 closure=ROOT/'EXPIRED-UNUSED-SUCCESSOR-CLOSURE.json'
 check(not closure.exists() and not closure.is_symlink(),'RELEASE_CLOSED_EXPLICIT_REBIND_REQUIRED')
 bpath=ROOT/'owner-binding.json';b=private_json(bpath,'BINDING_MISSING_RUN_FREEZE')
 frozen=private_json(ROOT/'FROZEN.json','FROZEN_PROOF_REQUIRED');policy=private_json(ROOT/'period-policy.json','FREEZE_INCOMPLETE')
 bh=hashlib.sha256(bpath.read_bytes()).hexdigest();ph=hashlib.sha256((ROOT/'period-policy.json').read_bytes()).hexdigest()
 check(frozen.get('binding_path')==str(bpath) and frozen.get('binding_sha256')==bh and
       frozen.get('policy_path')==str(ROOT/'period-policy.json') and frozen.get('policy_sha256')==ph and
       b.get('period_policy_sha256')==ph,'FROZEN_BINDING_MISMATCH')
 if 'timing_policy' in b:
  result=private_json(MINT_RESULT,'MINT_RESULT_REQUIRED');expected,expected_policy=build_v2(static(),result,b['timing_policy']['bound_at'])
  check(frozen.get('access_deadline')==b['valid_until'] and frozen.get('bound_at')==b['timing_policy']['bound_at'] and b==expected and policy==expected_policy and frozen.get('mint_result_sha256')==hashlib.sha256(MINT_RESULT.read_bytes()).hexdigest() and frozen.get('receipt_sha256')==result['receipt_sha256'] and frozen.get('expiry')==result['expiry'],'FROZEN_BINDING_MISMATCH')
  try:owner.validate_binding(b,opening=opening,now=now)
  except BaseException:raise PreparationError('RELEASE_WINDOW_CLOSED') from None
  return b,bpath,bh
 observed=b.get('inherited_boundary',{}).get('observed_at')
 check(type(observed) in (int,float) and frozen.get('isolation_observed_at')==observed and
       frozen.get('handoff_latest')==observed+300,'FROZEN_BINDING_MISMATCH')
 check(0<=now-observed<=300,'FROZEN_OBSERVATION_EXPIRED')
 review=private_json(ROOT/'ACTUAL-MINT-REVIEW.json','FREEZE_INCOMPLETE');r=private_json(MINT_RESULT,'MINT_RESULT_REQUIRED')
 check(frozen.get('mint_result_sha256')==review.get('mint_result_sha256')==hashlib.sha256(MINT_RESULT.read_bytes()).hexdigest() and
       frozen.get('receipt_sha256')==review.get('receipt_sha256')==r.get('receipt_sha256') and
       frozen.get('expiry')==review.get('expiry')==r.get('expiry'),'FROZEN_BINDING_MISMATCH')
 try:
  expected,expected_policy=build(static(),r,observed,now=observed)
  check(b==expected and policy==expected_policy,'FROZEN_BINDING_MISMATCH')
  if opening:owner.validate_binding(b,opening=True,now=now)
  else:check(now<b['valid_until'],'RELEASE_WINDOW_CLOSED')
 except PreparationError:raise
 except BaseException:raise PreparationError('RELEASE_WINDOW_CLOSED') from None
 return b,bpath,bh

def owner_receipt(phase,b,bh):
 directory=ROOT/(phase+'-evidence')
 if not directory.exists() and not directory.is_symlink():return None
 status=private_json(directory/'status.json','PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
 check(status.get('phase')==phase and status.get('binding_sha256')==bh,'LOCAL_RECEIPT_UNBOUND')
 check(status.get('client_closed') is True and status.get('exit_code')==0 and status.get('reason') is None and
       status.get('remote_closure')=='NORMAL_PHASE_EXIT_SEE_RESULT','PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
 value=private_json(directory/'output.txt','PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
 if phase=='period':
  good=value.get('outcome')=='COMMIT_ACKNOWLEDGED' and value.get('period')==b['period'] and value.get('policy_sha256')==b['period_policy_sha256'] and value.get('temporary_issuer')=='REMOVED' and value.get('original_memberships')=='PRESERVED' and value.get('readback')=='EXACT_ON_SAME_CONNECTION' and value.get('connections')==1
 elif phase=='activate':good=value.get('outcome')=='COMMIT_ACKNOWLEDGED' and value.get('runtime_roles')==sorted(owner.ROLES) and value.get('credentials')=='ENCRYPTED_LOCAL_ONLY' and value.get('valid_until')==b['valid_until']
 elif phase=='qualify':good=value.get('status')=='TWO_SINGLE_ATTEMPT_RESTRICTED_AUTHENTICATIONS_CLOSED' and sorted(value.get('roles',[]),key=lambda x:x['role'])==[dict(role=n,attempts=1,closed=True) for n in sorted(owner.ROLES)]
 elif phase=='submission-check':good=value.get('status')=='SUSPENDED_SINGLE_SUBMISSION_READY' and value.get('period')==b['period'] and value.get('latest_submission_exclusive')==b['valid_until']-1500
 else:good=value.get('status')=='RENDER_HANDOFF_ACKNOWLEDGED' and value.get('service_id')=='crn-d9sv93vavr4c73f98rb0'
 if good and 'timing_policy' in b and phase in ('handoff','submission-check'):
  obs=private_json(ROOT/('handoff-observation.json' if phase=='handoff' else 'submission-observation.json'),'OPERATION_OBSERVATION_REQUIRED')
  good=value.get('observation_sha256')==hashlib.sha256(canonical(obs)).hexdigest()
 check(good,'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY');return value

def next_command(*,now=None,expect=None):
 b,path,bh=frozen_binding(now=now,opening=False)
 seal=PRIVATE/'seal-evidence-01';marker=PRIVATE/'seal-01-consumed.json'
 if not seal.exists() and not seal.is_symlink():
  check(not any(p.exists() or p.is_symlink() for p in [marker,PRIVATE/'publication-01.vault',PRIVATE/'publication-01.vault.next']),'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
  phase='seal';args=['/bin/bash',str(LAUNCHERS/'RUN-SUCCESSOR-INACTIVE.sh'),'--phase',phase,'--successor-expired-unused','--authority',AUTHORITY_PATH,'--authority-sha256',AUTHORITY_RAW]
 else:
  v=private_json(seal/'result.json','PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY');c=v.get('owner_process',{})
  check(v.get('status')=='PRIVATE_PUBLICATION_TOKEN_ARMED' and v.get('receipt_sha256')==b['publication_mint']['receipt_sha256'] and c.get('client_closed') is True and c.get('exit_code')==0 and c.get('reason') is None,'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
  mark=private_json(marker,'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
  check(mark.get('binding_sha256')==hashlib.sha256(canonical(b)).hexdigest() and mark.get('receipt_sha256')==v['receipt_sha256'],'LOCAL_RECEIPT_UNBOUND')
  phase=None
  ordered=['period','activate','qualify','handoff']
  for i,name in enumerate(ordered):
   if owner_receipt(name,b,bh) is None:
    phase=name
    check(not any((ROOT/(later+'-evidence')).exists() or (ROOT/(later+'-evidence')).is_symlink() for later in ordered[i+1:]),'PHASE_ORDER_REFUSED')
    if name in ('period','activate'):
     target=Path(b['period_vault_path'] if name=='period' else static()['access_vault'])
     check(not target.exists() and not target.is_symlink() and not Path(str(target)+'.next').exists() and not Path(str(target)+'.next').is_symlink(),'PRIOR_PHASE_REQUIRES_REVIEW_NO_RETRY')
    break
  if phase is None and 'timing_policy' in b:
   if owner_receipt('submission-check',b,bh) is not None:raise PreparationError('NEXT_SUBMISSION_REVIEW_REQUIRED')
   phase='submission-check'
  check(phase is not None,'NEXT_SUBMISSION_REVIEW_REQUIRED')
  args=['/bin/bash',str(LAUNCHERS/'RUN-OWNER-INACTIVE.sh'),'--phase',phase,'--binding',str(path),'--binding-sha256',bh,'--vault',b['period_vault_path'] if phase=='period' else str(static()['access_vault']),'--evidence',str(ROOT/(phase+'-evidence'))]
  if 'timing_policy' in b and phase in ('handoff','submission-check'):
   operation='HANDOFF' if phase=='handoff' else 'SUBMISSION'
   observation_path=ROOT/(operation.lower()+'-observation.json')
   if not observation_path.exists():
    phase='observe-'+operation.lower();args=['/bin/bash',str(LAUNCHERS/'RUN-BINDING-INACTIVE.sh'),phase]
   else:
    from .intake_owner_io import operation_observation
    operation_observation(b,private_json(observation_path,'OPERATION_OBSERVATION_REQUIRED'),operation)
    args+=['--expected',str(observation_path),'--expected-sha256',hashlib.sha256(observation_path.read_bytes()).hexdigest()]
  if phase=='period':args+=['--expected',str(ROOT/'period-policy.json'),'--expected-sha256',b['period_policy_sha256']]
 try:
  if phase in ('seal','period','activate') or 'timing_policy' in b:owner.validate_binding(b,opening=True,now=time.time() if now is None else now)
 except BaseException:raise PreparationError('RELEASE_WINDOW_CLOSED') from None
 if 'timing_policy' in b and phase=='seal':args+=['--timing-v2']
 if expect is not None:check(expect==phase,'PHASE_ORDER_REFUSED')
 return phase,shlex.join(args)

def main(argv=None):
 try:
  p=argparse.ArgumentParser();p.add_argument('mode',choices=['check','preview','freeze','ready','bind','observe-handoff','observe-submission']);p.add_argument('--expect-phase',choices=['seal','period','activate','qualify','handoff','submission-check','observe-handoff','observe-submission']);p.add_argument('--verify-argv',nargs=argparse.REMAINDER);p.add_argument('--timing-v2',action='store_true');a=p.parse_args(argv)
  if a.timing_v2:use_timing_release()
  if a.mode.startswith('observe-'):
   require(sys.stdin.isatty() and sys.stderr.isatty());print(json.dumps(record_observation(a.mode[8:].upper()),sort_keys=True));return 0
  if a.mode=='ready':
   phase,command=next_command(expect=a.expect_phase)
   if a.verify_argv is not None:check(a.verify_argv==shlex.split(command)[2:],'PHASE_ARGUMENTS_REFUSED')
   print(json.dumps(dict(status='NEXT_PHASE_VERIFIED',phase=phase,**({} if a.expect_phase else dict(command=command)),provider_calls=0)));return 0
  s=static()
  if a.mode=='freeze' and s.get('version')=='FINITE_TIMING_V2_STATIC':raise PreparationError('USE_BIND_FOR_SEPARATE_EXPIRY')
  if a.mode=='check':
   # Synthetic public receipt only, no real token/credentials/requests.
   t=datetime(2026,11,3,12,tzinfo=timezone.utc).timestamp();r=dict(status='MINT_RECEIPT_VALIDATED_NOT_ARMED',mint_outcome='MINTED',retry=False,authority_sha256=AUTHORITY,receipt_sha256='1'*64,expiry=t+1800,expires_at=datetime.fromtimestamp(t+1800,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),owner_process=dict(client_closed=True,exit_code=0,reason=None))
   build(s,r,t,now=t);print('{"status":"STATIC_ASSEMBLY_CHECK_PASS","provider_calls":0}');return 0
  require(sys.stdin.isatty() and sys.stderr.isatty());r=private_json(MINT_RESULT,'MINT_RESULT_REQUIRED');digest=hashlib.sha256(MINT_RESULT.read_bytes()).hexdigest()
  if a.mode=='bind':
   check(s.get('version')=='FINITE_TIMING_V2_STATIC','TIMING_RELEASE_UNBOUND')
   review=private_json(ROOT/'ACTUAL-MINT-REVIEW.json','MINT_REVIEW_REQUIRED');check(review.get('mint_result_sha256')==digest and review.get('receipt_sha256')==r['receipt_sha256'] and review.get('expiry')==r['expiry'],'FROZEN_BINDING_MISMATCH')
   check(not any((ROOT/n).exists() or (ROOT/n).is_symlink() for n in ('owner-binding.json','period-policy.json','FROZEN.json')),'FREEZE_ALREADY_EXISTS_NO_RETRY')
   check(input('BIND_EXACT_35_MINUTE_RELEASE: ').strip()=='BIND_EXACT_35_MINUTE_RELEASE','FRESH_CONFIRMATION_REQUIRED')
   bound_at=time.time();b,policy=build_v2(s,r,bound_at)
   bh=save('owner-binding.json',b);ph=save('period-policy.json',policy)
   save('FROZEN.json',dict(binding_path=str(ROOT/'owner-binding.json'),binding_sha256=bh,policy_path=str(ROOT/'period-policy.json'),policy_sha256=ph,mint_result_sha256=digest,receipt_sha256=r['receipt_sha256'],expiry=r['expiry'],access_deadline=b['valid_until'],bound_at=bound_at))
   print(json.dumps(dict(status='FIXED_35_MINUTE_RELEASE_BOUND',deadline=b['valid_until'],token_expiry=r['expiry'],binding_sha256=bh,policy_sha256=ph,latest_submit_exclusive=b['valid_until']-1500)));return 0
  if a.mode=='preview':
   if s.get('version')=='FINITE_TIMING_V2_STATIC':
    require(r.get('status')=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and r.get('authority_sha256')==AUTHORITY)
    record=dict(mint_result_sha256=digest,receipt_sha256=r['receipt_sha256'],expiry=r['expiry'],latest_bind_inclusive=r['expiry']-2100,access_seconds=2100,submission_minimum_remaining_exclusive=1500)
    save('ACTUAL-MINT-REVIEW.json',record);print(json.dumps(record,sort_keys=True));return 0
   # Exactly the actual receipt/expiry is reviewed during ageing; no fresh
   # observation or executable binding is fabricated or consumed by preview.
   t=r['expiry']-1800;b,policy=build(s,r,t,now=t)
   record=dict(mint_result_sha256=digest,receipt_sha256=r['receipt_sha256'],expiry=r['expiry'],policy=policy,policy_sha256=hashlib.sha256(canonical(policy)).hexdigest(),earliest_seal=r['expiry']-2100,latest_seal_exclusive=r['expiry']-1445,latest_submit_exclusive=r['expiry']-1145)
   save('ACTUAL-MINT-REVIEW.json',record);print(json.dumps({k:v for k,v in record.items() if k!='policy'},sort_keys=True));return 0
  reviewed=private_json(ROOT/'ACTUAL-MINT-REVIEW.json','MINT_REVIEW_REQUIRED');check(reviewed['mint_result_sha256']==digest,'FROZEN_BINDING_MISMATCH')
  now=time.time();check(r['expiry']-2100<=now<r['expiry']-1445,'RELEASE_WINDOW_CLOSED')
  check(not any((ROOT/n).exists() or (ROOT/n).is_symlink() for n in ['owner-binding.json','period-policy.json','FROZEN.json']),'FREEZE_ALREADY_EXISTS_NO_RETRY')
  print('Only after the actual-expiry finite release is approved, just now verify: no active jobs/builds or other activity; no env groups/secret files; expected direct names and harmless settings/browser-profile equality; exact retained artifact; supported suspended custom-command and failure closure controls. Do not change values or proceed on a difference.',file=sys.stderr)
  check(input(FRESH_PHRASE+': ').strip()==FRESH_PHRASE,'FRESH_CONFIRMATION_REQUIRED')
  observed=time.time();b,policy=build(s,r,observed,now=observed)
  require(hashlib.sha256(canonical(policy)).hexdigest()==reviewed['policy_sha256'])
  bh=save('owner-binding.json',b);ph=save('period-policy.json',policy)
  result=dict(binding_path=str(ROOT/'owner-binding.json'),binding_sha256=bh,policy_path=str(ROOT/'period-policy.json'),policy_sha256=ph,mint_result_sha256=digest,receipt_sha256=r['receipt_sha256'],expiry=r['expiry'],isolation_observed_at=observed,handoff_latest=observed+300)
  save('FROZEN.json',result);print(json.dumps(result,sort_keys=True));return 0
 except PreparationError as exc:
  print(json.dumps(dict(status='STOP_LOCAL_PREREQUISITE_REVIEW',reason=exc.code,provider_calls=0,retry=False)));return 2
 except BaseException:
  print('{"status":"STOP_LOCAL_BINDING_REVIEW","provider_calls":0,"retry":false}');return 2

if __name__=='__main__':raise SystemExit(main())
