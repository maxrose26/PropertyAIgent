"""Exact-commit local Linux comparison, not WSL or release approval.

Requires an existing Python environment with test dependencies. No installation,
production inputs, credentials, bootstrap, refresh or model calls. Linux seccomp
denies networking before importing tests; fixtures use disposable SQLite only.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--baseline',default='908c7f625e965ee34d9aa3ac14ba8351a1f0a95e')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    def git(*cmd):
        return subprocess.check_output(['git',*cmd],cwd=repo)
    for sha in (args.candidate,args.baseline):
        if len(sha)!=40 or git('rev-parse',sha+'^{commit}').decode().strip()!=sha:
            raise ValueError('Require an exact commit')
    if git('rev-parse','HEAD').decode().strip()!=args.candidate or git('status','--porcelain').strip():
        raise ValueError('Candidate must be clean and checked out exactly')
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'home').mkdir()
    (out/'candidate.txt').write_text(args.candidate+'\n')
    (out/'baseline.txt').write_text(args.baseline+'\n')
    (out/'working-tree-before.txt').write_bytes(git('status','--porcelain'))
    env={'PATH':str(Path(sys.executable).parent)+':/usr/bin:/bin','HOME':str(out/'home'),
         'DATABASE_URL':'sqlite:///:memory:','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
    (out/'runtime.txt').write_text(sys.version+'\n')
    (out/'dependencies.txt').write_bytes(subprocess.check_output([sys.executable,'-m','pip','freeze'],env=env))
    (out/'isolation.txt').write_text('Local Linux, NOT WSL. Clean environment and temporary HOME. '
        'seccomp denial of network syscalls verified before test imports. Disposable SQLite memory/file fixtures only. '
        'No PostgreSQL server installed; PostgreSQL DDL compilation only, no PostgreSQL runtime claim.\n')
    checks=['tests/test_agent_ready_fact_foundation.py','tests/test_affordable_housing_scope.py',
        'tests/test_buyer_matching.py','tests/test_buyer_mandate_v2_phase_b2.py','tests/test_agent_evaluation_persistence.py']
    results={}
    with tempfile.TemporaryDirectory(prefix='ah-exact-') as temp:
        roots={}
        for label,sha in (('candidate',args.candidate),('baseline',args.baseline)):
            target=Path(temp)/label
            target.mkdir()
            with tarfile.open(fileobj=io.BytesIO(git('archive',sha))) as archive:
                archive.extractall(target,filter='data')
            if list(target.rglob('.env')):
                raise ValueError('Environment file in source snapshot')
            roots[label]=target
        runner=roots['candidate']/'verification/ah-offline-pytest.py'
        groups=[('candidate','candidate',checks),('baseline','baseline',checks),
            ('new-tests','candidate',['tests/test_ah_downstream_consumption.py','tests/test_ah_buyer_trust.py']),
            ('spec020','candidate',['tests/test_ah_qualified_discovery.py','verification/test_ah_assessment.py','verification/test_ah_count_threshold.py']),
            ('filter','candidate',['verification/test_ah_filter.py']),
            ('provenance','candidate',['tests/test_ah_source_claims.py']),
            ('baseline-provenance','baseline',['tests/test_ah_source_claims.py']),
            ('pg-boundary','candidate',['tests/test_ah_postgres_boundary.py'])]
        for label,root,files in groups:
            with (out/(label+'.log')).open('w') as log:
                result=subprocess.run([sys.executable,str(runner),'-q','-p','no:cacheprovider',*files,
                    '--junitxml='+str(out/(label+'.xml'))],cwd=roots[root],env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=300)
            results[label]=result.returncode
            (out/(label+'-exit.txt')).write_text(str(result.returncode)+'\n')
            print(label,result.returncode,flush=True)
        subprocess.run([sys.executable,str(roots['candidate']/'verification/ah-result-summary.py'),str(out)],check=True,env=env)
    (out/'working-tree-after.txt').write_bytes(git('status','--porcelain'))
    (out/'runner.sha256').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'  ah-local-compare.py\n')
    archive_path=out.with_suffix('.tar.gz')
    with tarfile.open(archive_path,'w:gz') as archive:
        for path in sorted(out.iterdir()):
            if path.is_file():
                archive.add(path,arcname=out.name+'/'+path.name)
    print('Archive:',archive_path)
    return int(any(results.values()))


if __name__=='__main__':
    raise SystemExit(main())
