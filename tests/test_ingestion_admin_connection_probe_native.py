"""Hosted-only: the probe with the REAL native cgroup memory object inside the exclusive systemd operational scope.

Deliberately no PostgreSQL cluster here: the operational scope must contain exactly this process, so a server started inside it would (correctly) make OperationalMemory
refuse with EXCLUSIVE_OPERATIONAL_SCOPE. The connection is a stub; the server-side statement proof lives in test_ingestion_admin_connection_probe.py."""
import json,os,socket,sys,time
import psycopg,pytest
from tests.test_ingestion_admin_connection_probe import run_probe,secret_safe,url

pytestmark=pytest.mark.skipif(os.environ.get('INGESTION_OPERATIONAL_NATIVE')!='1',reason='requires the hosted systemd operational scope')


class StubCursor:
    pgresult=None
    def fetchall(self):return [('postgres',)]


class StubConnection:
    closed=False
    def execute(self,statement):
        assert statement=='SELECT current_user';return StubCursor()
    def close(self):self.closed=True


@pytest.mark.parametrize('case',['qualified','refused','preparation'])
def test_native_memory_and_process_closure_for_the_probe(tmp_path,case):
    from verification.ingestion_storage.operational_memory import OperationalMemory
    native=OperationalMemory()
    if case=='refused':
        def refuse():
            with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            return psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='postgres',connect_timeout=3)
        result,j,lines,_,_=run_probe(tmp_path,refuse,memory=native)
    elif case=='preparation':result,j,lines,_,_=run_probe(tmp_path,StubConnection,raw=url(user='postgres'),memory=native)
    else:result,j,lines,_,_=run_probe(tmp_path,StubConnection,memory=native)
    process=result['closure_components']['process']
    assert process['status']=='CLOSED' and process['live_child_count']==0 and process['new_socket_count']==0 and result['cleanup']=='CLOSED' and result['outcome']['closure']=='VERIFIED'
    assert process['memory']['owned_groups_removed'] is True and process['memory']['owned_survivors']==0
    assert (result['status']=='ADMIN_CONNECTION_QUALIFIED')==(case=='qualified')
    assert result['outcome']['administrative_connection']=={'qualified':'QUALIFIED','refused':'FAILED_CLASSIFIED','preparation':'NOT_ATTEMPTED'}[case]
    secret_safe(j,lines,result)
