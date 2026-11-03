"""Offline proof against exact retained runtime predicate; no source/API/DB requests."""
import ast,hashlib,types
from pathlib import Path
import pytest
from verification.ingestion_storage import intake_owner as op,intake_owner_operations as extra,finite_release_binding as flow
from tests.test_timing_amendment import v2
from verification.ingestion_storage.intake_budget import LIMITS

RUNTIME=Path('verification/ingestion_storage/daily_intake_runtime.py')
RUNTIME_SHA='2c5bd037763eadb431ca9ce98ca8a336648238f6c941c86696991ed9fd5796e4'

def retained_refuses(P,now,elapsed):
 raw=RUNTIME.read_bytes();assert hashlib.sha256(raw).hexdigest()==RUNTIME_SHA
 tree=ast.parse(raw);node=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and any(isinstance(x,ast.Constant) and x.value=='INTAKE_PERIOD_TOO_SHORT_FOR_RUN' for s in n.body for x in ast.walk(s)))
 self=types.SimpleNamespace(policy={'expires_at':P},run=types.SimpleNamespace(totals=lambda:dict(elapsed_seconds=elapsed)))
 return eval(compile(ast.Expression(node.test),str(RUNTIME),'eval'),{'self':self,'time':types.SimpleNamespace(time=lambda:now),'LIMITS':LIMITS})

@pytest.mark.parametrize('queue,elapsed',[(0,0),(355,0),(356,0),(357,0),(500,0),(1000,0),(355,200),(356,700),(357,200)])
def test_actual_start_and_continuation_predicate_preserves_external_reserve(v2,queue,elapsed):
 f=v2;D=f['b']['valid_until'];P=f['p']['expires_at'];assert P==D-185
 # Submit with1501seconds remaining, then modeled queue delay and runtime elapsed.
 now=D-1501+queue+elapsed
 refused=retained_refuses(P,now,elapsed)
 if not refused:assert D-now >= LIMITS['wall_seconds']-elapsed+5+3*60
 else:assert D-now < LIMITS['wall_seconds']-elapsed+185
 assert refused==(queue>356)


def test_original_counterexample_is_refused_without_artifact_change(v2):
 f=v2;D=f['b']['valid_until'];now=D-1000
 assert retained_refuses(D,now,0) is False  # accepted old policy expiry=D had the gap
 assert retained_refuses(f['p']['expires_at'],now,0) is True


def test_reserve_cutoff_and_policy_cannot_be_arbitrarily_shifted(v2):
 import copy,hashlib
 from verification.ingestion_storage.operational_publication import canonical
 f=v2;b=f['b'];assert b['runtime_deadline']==b['valid_until']-185 and b['publication_valid_until']>b['valid_until']
 for difference in [-1,1,185]:
  bad=copy.deepcopy(b);bad['runtime_deadline']+=difference
  with pytest.raises(op.Denied,match='FINITE_EXECUTION_RESERVE_BINDING'):op.validate_binding(bad)
 for difference in [-1,1,185]:
  bad=copy.deepcopy(f['p']);bad['expires_at']+=difference;bound=copy.deepcopy(b);bound['period_policy_sha256']=hashlib.sha256(canonical(bad)).hexdigest()
  with pytest.raises(op.Denied,match='PERIOD_FIXED_DEADLINE'):extra.validate_policy(bound,bad)


def test_gate_runs_before_council_contract_and_issuance():
 tree=ast.parse(RUNTIME.read_bytes());klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Runtime');execute=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
 loop=next(n for n in ast.walk(execute) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='row')
 gate=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and 'INTAKE_PERIOD_TOO_SHORT_FOR_RUN' in ast.unparse(n))
 assert all('self.issue(' not in ast.unparse(n) and 'self.contract(' not in ast.unparse(n) for n in loop.body[:gate])
