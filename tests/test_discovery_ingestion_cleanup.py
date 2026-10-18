import json,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from verification.ingestion_storage.operational_cleanup import Cleanup,Journal,Stop,SECRETS,SECRET_PATH

def test_journal_once_bound_and_chain(tmp_path):
    from verification.ingestion_storage.operational_cleanup import digest
    j=Journal(tmp_path/'once');j.emit('consumed',{'scope':'cleanup_only'})
    with pytest.raises(FileExistsError):Journal(j.root)
    row=json.loads(j.file.read_bytes());sha=row.pop('sha256')
    assert digest(row)==sha and row['sequence']==0 and row['previous_sha256']=='0'*64
    result=j.save({'cleanup':'UNCERTAIN'});assert result['exported_bytes']<524288

def test_uncertain_delete_stops_without_next_request(tmp_path):
    calls=[]
    def lost(command,**kwargs):calls.append(command);raise subprocess.TimeoutExpired(command,1)
    worker=Cleanup(lambda:None,Journal(tmp_path/'lost'),github_runner=lost)
    with pytest.raises(Stop,match='GITHUB_ACK_UNCERTAIN'):worker.api('DELETE',SECRET_PATH+'/'+SECRETS[0])
    assert worker.deletes==1 and len(calls)==1 and worker.secret_deletions==[]

def test_limits_and_complete_names_are_fail_closed(tmp_path):
    worker=Cleanup(lambda:None,Journal(tmp_path/'bounds'),github_runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'{"total_count":2,"secrets":[{"name":"DATABASE_URL"}]}',stderr=b''))
    with pytest.raises(Stop,match='INCOMPLETE_SECRET_NAMES'):worker.names()
    with pytest.raises(Stop,match='EXACT_DELETE_BOUND'):worker.api('DELETE',SECRET_PATH+'/DATABASE_URL')
    worker.commands=32
    with pytest.raises(Stop,match='COMMAND_BOUND'):worker.q(None,'blocked','SELECT 1')
    worker.connections=2
    with pytest.raises(Stop,match='CONNECTION_BOUND'):
        with worker.connection():pass
    assert worker.deletes==0

def test_returned_value_cap_stops_before_next_effect(tmp_path):
    class PG:
        ntuples=1;nfields=1
        def get_value(self,*a):return b'x'*(1048576+1)
    c=SimpleNamespace(execute=lambda *a:SimpleNamespace(pgresult=PG()))
    worker=Cleanup(lambda:None,Journal(tmp_path/'bytes'))
    with pytest.raises(Stop,match='RETURNED_DATA_VALUE_BOUND'):worker.q(c,'read','SELECT retained_state')
    assert worker.commands==1 and worker.returned==1048577

def test_no_new_authorities_credentials_or_effect_routes():
    import inspect
    from verification.ingestion_storage import operational_cleanup as module
    source=inspect.getsource(module)
    assert 'secret\',\'set' not in source and 'CREATE ROLE ' not in source
    assert 'pg_terminate_backend' not in source and 'ingestion_worker_step(' not in source
    assert 'source_reader' not in source and 'verify-full' in source

