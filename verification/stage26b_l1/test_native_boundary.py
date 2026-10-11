"""Native host rehearsal; deliberately does not skip an unsupported process host."""
import pytest
from verification.stage26b_l1.process_boundary import supervise,ProcessFailure
import sys,time,os

def test_independent_hung_child_terminated(tmp_path):
    started=time.monotonic()
    with pytest.raises(ProcessFailure,match='TIMEOUT'):
        supervise([sys.executable,'-I','-c','import time;time.sleep(999)'],cwd=tmp_path,seconds=.2)
    assert time.monotonic()-started<5

def test_output_overflow_terminates_child(tmp_path):
    with pytest.raises(ProcessFailure,match='OUTPUT_OVERFLOW'):
        supervise([sys.executable,'-I','-c','import os,time;os.write(1,b"x"*2000);time.sleep(999)'],cwd=tmp_path,seconds=2,output_limit=1000)

def test_child_does_not_inherit_secret(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','synthetic-secret')
    result=supervise([sys.executable,'-I','-c','import json,os;print(json.dumps({"absent":"DATABASE_URL" not in os.environ}))'],cwd=tmp_path,seconds=2)
    assert result=={'absent':True}

def test_malformed_child_artifact(tmp_path):
    with pytest.raises(ProcessFailure,match='MALFORMED_ARTIFACT'):
        supervise([sys.executable,'-I','-c','print("not JSON")'],cwd=tmp_path,seconds=2)
