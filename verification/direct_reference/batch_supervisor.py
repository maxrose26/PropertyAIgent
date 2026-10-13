"""Reusable per-record process envelope; callers supply a reviewed worker entry.

No workflow or production activation here. The disposable entry is the only CLI
in this slice. Missing/invalid worker output remains uncertain, never no-write.
"""
import json
import os
from pathlib import Path
import tempfile
from .batch import blank,encode,validate_record,MAX_RECORD
from verification.stage26b_l1.actions_runner import supervise

def isolated(row,limits,command_factory,environment):
    with tempfile.TemporaryDirectory(prefix='stage4-batch-') as home:
        out=Path(home)/'record.json'
        env=dict(PATH='/usr/bin:/bin',HOME=home,TMPDIR=home,LANG='C.UTF-8',
            PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1')
        env.update(environment)
        # Production registration must provide its explicit minimal environment;
        # never inherit the ambient environment or credentials.
        command=command_factory(row,limits,out)
        status,expired=supervise(command,env=env,deadline=limits['worker_seconds'])
        if expired or status!=0 or not out.is_file() or out.stat().st_size>MAX_RECORD:
            a=blank(row);a.update(transaction='UNKNOWN',b2_outcome='UNKNOWN',error='INTERRUPTED',cleanup='UNKNOWN',disposition='UNCERTAIN');return a
        try:
            a=json.loads(out.read_bytes());validate_record(a,row)
            return a
        except Exception:
            a=blank(row);a.update(transaction='UNKNOWN',b2_outcome='UNKNOWN',error='AUDIT_REJECTED',cleanup='UNKNOWN',disposition='UNCERTAIN');return a

def resource_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))

def disposable_main():
    import argparse
    import contextlib
    from sqlalchemy import create_engine
    from .batch import manifest
    from .batch_transaction import run_transaction
    from .fixtures import Session,summary
    p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True)
    p.add_argument('--limits',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if os.environ.get('B20_DISPOSABLE')!='YES_SYNTHETIC_ONLY' or any(k in os.environ for k in ('DATABASE_URL','OLDHAM_DATABASE_URL')):raise ValueError('DISPOSABLE_ONLY')
    port=int(os.environ['B20_POSTGRES_PORT'])
    if not 1024<=port<=65535:raise ValueError('PORT')
    row=manifest()[a.index]['identity'] if 0<=a.index<len(manifest()) else None
    if row is None:raise ValueError('INDEX')
    resource_limits();engine=None
    with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        try:
            engine=create_engine(f'postgresql+psycopg://b20_disposable:b20-disposable-only@127.0.0.1:{port}/b20_disposable',pool_size=1,max_overflow=0,hide_parameters=True,connect_args={'connect_timeout':5,'options':'-c statement_timeout=10000 -c lock_timeout=8000 -c idle_in_transaction_session_timeout=40000'})
            result=run_transaction(engine,row,lambda:Session(summary(row['reference'],status='Decided',decision='Granted',date='Fri 25 Sep 2026')),json.loads(a.limits))
        finally:
            if engine is not None:engine.dispose()
    with a.output.open('xb') as f:f.write(encode(result,MAX_RECORD))
    return 0

if __name__=='__main__':raise SystemExit(disposable_main())
