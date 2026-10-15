"""Approved fixed944 current identity read. No source or admission imports."""
from pathlib import Path
import os,json,hashlib,re,subprocess,time
from . import r0_identity_comparison as existing
ROOT=Path(__file__).resolve().parents[2]
PACK=ROOT/'docs/design/stage4-r0-execution/completion-mandate-20261015'
MANIFEST=PACK/'comparison-944.json'
MANIFEST_SHA='34d6fe5ee4941b258afe88c2c6ffa196fb3d0bc052b73cb0667bb4e49acb8d5d'
WORKFLOW='.github/workflows/stage4-catchup-completion-comparison944-once.yml'
AUTHORITY='AUTHORISE_STAGE4_CATCHUP_COMPLETION_COMPARISON944_ONCE'

def identities():
    if hashlib.sha256(MANIFEST.read_bytes()).hexdigest()!=MANIFEST_SHA:raise ValueError('MANIFEST_REJECTED')
    rows=json.loads(MANIFEST.read_bytes())['identities']
    keys={(r['council_code'],r['reference']) for r in rows}
    if len(rows)!=944 or len(keys)!=944 or keys&{('bolton','01768/26'),('bolton','01769/26'),('bolton','01827/26')}:raise ValueError('COHORT_REJECTED')
    return rows

def admit(env,sha,manifest,authority):
    expected=dict(GITHUB_ACTIONS='true',RUNNER_ENVIRONMENT='github-hosted',GITHUB_REPOSITORY='maxrose26/PropertyAIgent',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/master',GITHUB_SHA=sha,GITHUB_WORKFLOW_SHA=sha,GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{WORKFLOW}@refs/heads/master',GITHUB_RUN_NUMBER='1',GITHUB_RUN_ATTEMPT='1')
    if not re.fullmatch('[0-9a-f]{40}',sha) or manifest!=MANIFEST_SHA or authority!=AUTHORITY or any(env.get(k)!=v for k,v in expected.items()):raise ValueError('COMPARISON_BINDING_REJECTED')
    if (ROOT/WORKFLOW).read_bytes()!=(PACK/'registered-comparison944.yml.txt').read_bytes():raise ValueError('WORKFLOW_CONTENT_REJECTED')
    if not re.fullmatch('[0-9]{10}',env.get('JOB_STARTED_EPOCH','')) or not 0<=time.time()-int(env['JOB_STARTED_EPOCH'])<=180:raise ValueError('SETUP_BOUND')
    identities()

def run(raw):
    # Reuse the SAME reviewed pure route validator/engine/query behaviour.
    # Explicit row injection is validated below; old fixed80 remains immutable.
    return existing.run_exact(raw,identities(),output_bound=1000000)

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha',required=True);p.add_argument('--manifest-sha',required=True);p.add_argument('--authority',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    admit(os.environ,a.reviewed_sha,a.manifest_sha,a.authority)
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.reviewed_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip() or a.output.exists():raise ValueError('CHECKOUT_OUTPUT_REJECTED')
    from .completion_read_supervisor import supervise
    execution=dict(sha=a.reviewed_sha,manifest_sha256=MANIFEST_SHA,run_id=os.environ['GITHUB_RUN_ID'],run_number=1,attempt=1,capability='IDENTITY_READ_ONLY')
    result=supervise(a.output,credential=os.environ.pop('COMPARISON_DATABASE_URL',''),execution=execution)
    if result.get('result',{}).get('result')!='COMPLETED' or result['cleanup']!='CLOSED' or result['stop_reason']:raise SystemExit(1)
if __name__=='__main__':main()
