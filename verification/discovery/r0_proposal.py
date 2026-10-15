"""Unregistered R0 caller. No database, registration or scheduling authority."""
from datetime import date, timedelta
import argparse, hashlib, json, os, re, signal, subprocess, sys, tempfile, time
from pathlib import Path
from . import finite_acceptance as f

WORKFLOW='.github/workflows/stage4-r0-source-date-once.yml'
AUTHORITY='AUTHORISE_NINE_COUNCIL_R0_SOURCE_DATE_OBSERVATION_ONCE'
START='2026-09-29'
CUT='2026-10-16' # exclusive local calendar cut; proposal, not approved freeze
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

def admit(env,sha,manifest_hash):
    if (not re.fullmatch('[0-9a-f]{40}',sha) or manifest_hash!=PLAN_HASH
        or env.get('GITHUB_ACTIONS')!='true' or env.get('RUNNER_ENVIRONMENT')!='github-hosted'
        or env.get('GITHUB_REPOSITORY')!='maxrose26/PropertyAIgent'
        or env.get('GITHUB_REF')!='refs/heads/master' or env.get('GITHUB_SHA')!=sha
        or env.get('GITHUB_WORKFLOW_SHA')!=sha
        or env.get('GITHUB_WORKFLOW_REF')!=f'maxrose26/PropertyAIgent/{WORKFLOW}@refs/heads/master'
        or env.get('GITHUB_RUN_NUMBER')!='1' or env.get('GITHUB_RUN_ATTEMPT')!='1'
        or env.get('R0_AUTHORITY')!=AUTHORITY):raise ValueError('R0_ADMISSION_REJECTED')
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
    refs=independent.get('references');segments=independent.get('segments')
    if (not isinstance(refs,list) or not all(isinstance(x,str) and x for x in refs)
        or len(set(refs))!=len(refs) or type(segments) is not int or not 1<=segments<=6
        or (not refs and independent.get('explicit_zero') is not True)):return 'UNKNOWN'
    actual=source.get('listing_records' if row['council'] in f.ARCUS else 'records',[])
    primary=[r.get('reference') for r in actual]
    if set(primary)!=set(refs):return 'INCOMPLETE'
    return 'COMPLETE'

def supervise_round(plan,output,*,runner=subprocess.Popen,deadline=ROUND_SECONDS):
    """Hard parent wait, owned group termination, bounded child files.

    Child source workers retain their own existing process supervision. Hosted
    VM teardown is final containment, not a hostile-detachment sandbox claim.
    """
    if deadline!=ROUND_SECONDS or output.exists():raise ValueError('ROUND_BOUNDARY')
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='r0-round-') as td:
        inp=Path(td)/'plan.json'; out=Path(td)/'result.json';inp.write_text(json.dumps(plan))
        env=dict(PATH='/usr/bin:/bin',HOME=td,TMPDIR=td,PYTHONDONTWRITEBYTECODE='1',GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH',str(Path.home()/'.cache/ms-playwright')))
        child=runner([sys.executable,'-m','verification.discovery.r0_proposal','--worker',str(inp),'--output',str(out)],
            env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        import psutil
        expired=False; started=time.monotonic(); seen={}; peak=0
        parent=psutil.Process(child.pid)
        try:
            while child.poll() is None:
                rss=0
                try:owned=[parent]+parent.children(recursive=True)
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
            result=json.loads(out.read_bytes());result['accounting_complete']=True
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
    if actual!=a.reviewed_sha:raise ValueError('CHECKOUT_MISMATCH')
    a.output.mkdir(exist_ok=False)
    for i,plan in enumerate(PLAN['rounds']):
        result=supervise_round(plan,a.output/f'round-{i+1}.json')
        if result.get('enumeration_completeness')!='COMPLETE':break

if __name__=='__main__':main()
