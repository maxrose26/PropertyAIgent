"""Loopback-only effects for the ACTUAL standing runtime command. No owner/admin."""
import json,os,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace,MappingProxyType
from datetime import date
p=json.loads(Path(sys.argv[1]).read_text())
if p.get('disposable')!='LOOPBACK_ONLY' or os.environ.get('INGESTION_ACCEPTANCE_DISPOSABLE')!='PG17_ONLY':raise SystemExit('DISPOSABLE_ONLY')
from verification.ingestion_storage import oldham_standing_runtime as runtime
from verification.ingestion_storage.operational_memory import OperationalMemory
from app.ingestion import owner_acceptance
from tests.e2e_connection_support import make_test_acceptance
# Imported fixture dependencies may use a harmless SQLite default; it is absent
# from the admitted runtime environment, and no application engine is constructed.
os.environ.pop('DATABASE_URL',None)

def acceptance(claim):
    x=make_test_acceptance(claim['inputs']['source'],'oldham',date(2026,10,15),date(2026,10,21))
    owner_acceptance.ACCEPTANCES=MappingProxyType({**owner_acceptance._load(),x.key:x})


def gh(c,**kw):return subprocess.run([p['gh'],*c[1:]],env=p['gh_env'],**kw)

def wait(seconds):
    assert seconds==60
    time.sleep(2) # explicitly accelerated fixture only; production remains60s

memory=OperationalMemory() if p['native'] else None
sys.argv=sys.argv[2:]
effects=SimpleNamespace(fixed_disposable=True,memory=memory,gh_runner=gh,acceptance=acceptance,sleep=wait)
raise SystemExit(runtime.main(sys.argv,effects=effects))
