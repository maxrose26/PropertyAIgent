"""Credential-free registered R0 caller. Execution needs exact confirmation."""
from datetime import date, timedelta, datetime, timezone
import argparse, hashlib, json, os, re, signal, subprocess, sys, tempfile, time
from pathlib import Path
from zoneinfo import ZoneInfo
from . import finite_acceptance as f

WORKFLOW='.github/workflows/stage4-r0-source-date-once.yml'
AUTHORITY='AUTHORISE_NINE_COUNCIL_R0_SOURCE_DATE_OBSERVATION_ONCE'
START='2026-09-29'
CUT='2026-10-15' # exclusive local calendar cut; latest completed day scope
ROUND_SECONDS=1900

def proposal():
    # First trailing 28 days includes pre-suspension overlap; older partitions
    # are explicit if a future reviewed cut makes suspension longer than 28 days.
    cut=date.fromisoformat(CUT); start=date.fromisoformat(START)
    cursor=min(start,cut-timedelta(days=28)); rounds=[]
    while cursor<cut:
        end=min(cursor+timedelta(days=27),cut-timedelta(days=1))
        rounds.append(f.manifest(cursor.isoformat(),end.isoformat(),'SUSPENSION_CATCHUP'))
        cursor=end+timedelta(days=1)
    return dict(version=1,start=START,cut_exclusive=CUT,timezone='Europe/London',
        overlap_days=28,rounds=rounds,publication_coverage='UNKNOWN',latency='UNKNOWN',
        persistence=False,watermark_advance=False)

PLAN=proposal()
PLAN_HASH=f.digest(PLAN)

def admit(env,sha,manifest_hash,*,now=None):
    if (not re.fullmatch('[0-9a-f]{40}',sha) or manifest_hash!=PLAN_HASH
        or env.get('GITHUB_ACTIONS')!='true' or env.get('RUNNER_ENVIRONMENT')!='github-hosted'
        or env.get('GITHUB_REPOSITORY')!='maxrose26/PropertyAIgent'
        or env.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
        or env.get('GITHUB_REF')!='refs/heads/master' or env.get('GITHUB_SHA')!=sha
        or env.get('GITHUB_WORKFLOW_SHA')!=sha
        or env.get('GITHUB_WORKFLOW_REF')!=f'maxrose26/PropertyAIgent/{WORKFLOW}@refs/heads/master'
        or env.get('GITHUB_RUN_NUMBER')!='1' or env.get('GITHUB_RUN_ATTEMPT')!='1'
        or env.get('R0_AUTHORITY')!=AUTHORITY):raise ValueError('R0_ADMISSION_REJECTED')
    if (now or datetime.now(timezone.utc))<datetime.combine(date.fromisoformat(CUT),datetime.min.time(),tzinfo=ZoneInfo('Europe/London')).astimezone(timezone.utc):raise ValueError('CUT_NOT_REACHED')
    if any(k in env for k in ('DATABASE_URL','COMMITTEE_DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY')):
        raise ValueError('CREDENTIAL_CONTEXT_REJECTED')

def qualify(row,source,independent):
    """In-round new-window qualification, after separately sealed enumeration.

    Count reconciliation alone cannot qualify coverage. The independent assessor
    attests source-date semantics/criteria/terminal evidence, before primary reveal.
    This is NOT a public-availability completeness proof.
    """
    if f.classify(row,source)!='COMPLETE':return 'UNKNOWN'
    required={'council':row['council'],'interval':[row['start'],row['end']],
              'semantics':row['semantics'],'complete':True,'sealed_before_primary_reveal':True,
              'criteria_verified':True,'terminal_verified':True}
    if any(independent.get(k)!=v for k,v in required.items()):return 'UNKNOWN'
    if not re.fullmatch('[0-9a-f]{64}',independent.get('evidence_sha256','')):return 'UNKNOWN'
    try:
        def stamp(value):
            parsed=datetime.fromisoformat(value)
            if parsed.utcoffset() is None:raise ValueError('timestamp timezone')
            return parsed
        observed=source['primary_observation']
        primary_start,primary_end=stamp(observed['started_at']),stamp(observed['ended_at'])
        independent_start,independent_end=stamp(independent['observed_started_at']),stamp(independent['observed_ended_at'])
        sealed,revealed=stamp(independent['sealed_at']),stamp(independent['primary_revealed_at'])
        if not primary_start<=primary_end<=revealed or not independent_start<=independent_end<=sealed<=revealed:return 'UNKNOWN'
        assessor,session,primary_session=(independent[k] for k in ('assessor','assessor_session','primary_session'))
        if not all(isinstance(x,str) and 1<=len(x)<=100 for x in (assessor,session,primary_session)) or session==primary_session:return 'UNKNOWN'
    except (KeyError,TypeError,ValueError):return 'UNKNOWN'
    refs=independent.get('references');segments=independent.get('segments')
    if (not isinstance(refs,list) or not all(isinstance(x,str) and x for x in refs)
        or len(set(refs))!=len(refs) or type(segments) is not int or not 1<=segments<=6
        or (not refs and independent.get('explicit_zero') is not True)):return 'UNKNOWN'
    actual=source.get('listing_records' if row['council'] in f.ARCUS else 'records',[])
    primary=[r.get('reference') for r in actual]
    # A discrepancy blocks acceptance, but changing public source state is a
    # possible cause. Preserve the sets/timestamps for review, never self-label
    # this as a parser defect or silently add the missing reference.
    if set(primary)!=set(refs):return 'UNKNOWN'
    return 'COMPLETE'

def reference_difference(primary,independent):
    """Comparison ledger only; call with previously qualified literal references."""
    a,b=set(primary),set(independent)
    return dict(outcome='MATCH' if a==b else 'UNRESOLVED_REFERENCE_DIFFERENCE',
        primary_only=sorted(a-b),independent_only=sorted(b-a),
        cause='NOT_APPLICABLE' if a==b else 'UNKNOWN_SOURCE_CHANGE_OR_ENUMERATION')


def supervise_round(plan,output,*,runner=subprocess.Popen,deadline=ROUND_SECONDS,
                    worker_module='verification.discovery.r0_proposal'):
    """Hard parent wait, owned group termination, bounded child files.

    Child source workers retain their own existing process supervision. Hosted
    VM teardown is final containment, not a hostile-detachment sandbox claim.
    """
    if (deadline!=ROUND_SECONDS or output.exists() or worker_module not in {
            'verification.discovery.r0_proposal', 'verification.discovery.r0_recovery_proposal'}):
        raise ValueError('ROUND_BOUNDARY')
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='r0-round-') as td:
        inp=Path(td)/'plan.json'; out=Path(td)/'result.json';inp.write_text(json.dumps(plan))
        env=dict(PATH='/usr/bin:/bin',HOME=td,TMPDIR=td,PYTHONDONTWRITEBYTECODE='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH',str(Path.home()/'.cache/ms-playwright')))
        child=runner([sys.executable,'-m',worker_module,'--worker',str(inp),'--output',str(out)],
            env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        import psutil
        expired=False; started=time.monotonic(); seen={}; peak=0
        try:parent=psutil.Process(child.pid)
        except psutil.NoSuchProcess:parent=None
        try:
            while child.poll() is None:
                rss=0
                try:owned=[] if parent is None else [parent]+parent.children(recursive=True)
                except psutil.NoSuchProcess:break
                for process in owned:
                    try:
                        seen[process.pid]=process.create_time();rss+=process.memory_info().rss
                    except psutil.NoSuchProcess:pass
                peak=max(peak,rss)
                if time.monotonic()-started>=deadline or rss>1536*1024*1024:
                    expired=True;break
                time.sleep(.1)
        finally:
            if child.returncode is None:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            code=child.wait(timeout=5)
            killed=[]
            for pid,born in seen.items():
                try:
                    process=psutil.Process(pid)
                    if process.create_time()==born and process.status()!=psutil.STATUS_ZOMBIE:
                        process.kill();killed.append(process)
                except psutil.NoSuchProcess:pass
            psutil.wait_procs(killed,timeout=3)
        survivors=[]
        for pid,born in seen.items():
            try:
                process=psutil.Process(pid)
                if process.create_time()==born and process.status()!=psutil.STATUS_ZOMBIE:survivors.append(pid)
            except psutil.NoSuchProcess:pass
        result=dict(completeness='UNKNOWN',enumeration_completeness='UNKNOWN',
            accounting_complete=False,stop_reason='OUTER_DEADLINE' if expired else 'WORKER_FAILURE',persistence=False)
        if not expired and not survivors and code==0 and out.is_file() and out.stat().st_size<=f.LIMITS['output_bytes']:
            result=json.loads(out.read_bytes())
        result['outer_supervisor']=dict(expired=expired,exit_code=code,elapsed_seconds=round(time.monotonic()-started,3),
            peak_owned_rss=peak,live_owned_survivors=len(survivors),cleanup='CLOSED' if not survivors else 'FAILED',final_containment='DISPOSABLE_HOSTED_VM',restarted=False)
        output.write_text(json.dumps(result,sort_keys=True))
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reviewed-sha');p.add_argument('--manifest-sha');a=p.parse_args()
    if a.worker:
        # Hard file-size/output limit in addition to parent's wait and child bounds.
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE,(f.LIMITS['output_bytes'],f.LIMITS['output_bytes']))
        plan=json.loads(a.worker.read_bytes())
        result=f.execute(plan,f.digest(plan));a.output.write_text(json.dumps(result,sort_keys=True));return
    admit(os.environ,a.reviewed_sha,a.manifest_sha)
    actual=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if actual!=a.reviewed_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CHECKOUT_MISMATCH')
    a.output.mkdir(exist_ok=False)
    metadata=dict(sha=a.reviewed_sha,manifest_sha256=PLAN_HASH,run_id=os.environ['GITHUB_RUN_ID'],
        run_number=1,attempt=1,started_at=datetime.now(timezone.utc).isoformat(),persistence=False,
        publication_coverage='UNKNOWN',latency='UNKNOWN',
        config_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            Path(__file__),Path(f.__file__),Path(__file__).with_name('arcus_ui_config.py'),
            Path(__file__).with_name('idox_window.py')]})
    (a.output/'execution.json').write_text(json.dumps(metadata,sort_keys=True))
    for i,plan in enumerate(PLAN['rounds']):
        result=supervise_round(plan,a.output/f'round-{i+1}.json')
        if result.get('enumeration_completeness')!='COMPLETE':break
    metadata['ended_at']=datetime.now(timezone.utc).isoformat()
    (a.output/'execution.json').write_text(json.dumps(metadata,sort_keys=True))

if __name__=='__main__':main()
