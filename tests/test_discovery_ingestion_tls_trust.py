"""Offline certificate checks + disposable loopback PostgreSQL TLS emulator.

No production DNS/address/secret or SQL. Literal host used only for SAN checking;
psycopg hostaddr is fixed127.0.0.1 and the fixture returns a synthetic FATAL.
"""
import hashlib,json,socket,ssl,struct,threading
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import MagicMock
import pytest,psycopg
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from verification.ingestion_storage import tls_trust as trust
HOST='aws-0-eu-west-2.pooler.supabase.com'


def test_reviewed_provider_ca_integrity_validity_and_tamper_rejection(tmp_path,monkeypatch):
 path,audit=trust.verified_trust();assert audit['pem_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
 assert audit['not_after']=='2031-04-26T10:56:53+00:00'
 with pytest.raises(ValueError,match='VALIDITY'):trust.verified_trust(datetime(2031,3,1,tzinfo=timezone.utc))
 altered=tmp_path/'root.crt';altered.write_bytes(path.read_bytes()+b'\n');monkeypatch.setattr(trust,'ROOT',altered)
 with pytest.raises(ValueError,match='HASH'):trust.verified_trust()


@pytest.fixture
def tls_server(tmp_path):
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
 root_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'DISPOSABLE TEST CA')])
 root=x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).sign(key,hashes.SHA256())
 leafkey=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 leaf=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,HOST)])).issuer_name(root_name).public_key(leafkey.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]),False).sign(key,hashes.SHA256())
 ca=tmp_path/'test-ca.crt';ca.write_bytes(root.public_bytes(serialization.Encoding.PEM));pem=tmp_path/'leaf.crt';pem.write_bytes(leaf.public_bytes(serialization.Encoding.PEM));pk=tmp_path/'leaf.key';pk.write_bytes(leafkey.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(pem,pk)
 baseline=trust.owned_resources()
 listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(4);port=listener.getsockname()[1]
 receipt={'tls':False,'startup_received':False,'server_closed':False}
 def server():
  try:
   with listener:
    conn,_=listener.accept()
    with conn:
     conn.settimeout(3)
     assert conn.recv(8)==struct.pack('!II',8,80877103);conn.sendall(b'S')
     try:
      with context.wrap_socket(conn,server_side=True) as secure:
       receipt['tls']=True;receipt['startup_received']=bool(secure.recv(4096))
       payload=b'SFATAL\x00C28000\x00MDISPOSABLE_TLS_ACCEPTED_NO_DATABASE\x00\x00'
       secure.sendall(b'E'+struct.pack('!I',len(payload)+4)+payload)
     except (ssl.SSLError,ConnectionError):pass
  finally:listener.close();receipt['server_closed']=True
 thread=threading.Thread(target=server);thread.start()
 yield ca,port,receipt,thread,baseline
 listener.close();thread.join(timeout=5);assert not thread.is_alive()


@pytest.mark.parametrize('case',['trusted','untrusted','wrong_hostname'])
def test_real_libpq_preserves_chain_and_hostname_checks_and_finishes_failed_handle(tls_server,case,record_property):
 ca,port,receipt,thread,baseline=tls_server;root=str(ca) if case!='untrusted' else str(trust.ROOT);host=HOST if case!='wrong_hostname' else 'wrong.invalid'
 with pytest.raises(psycopg.OperationalError) as error:
  psycopg.connect(host=host,hostaddr='127.0.0.1',port=port,dbname='DISPOSABLE',user='DISPOSABLE',sslmode='verify-full',sslrootcert=root,connect_timeout=2,prepare_threshold=None,gssencmode='disable')
 evidence=trust.failure_evidence(error.value)
 assert evidence['failed_native_connection_finished']
 with pytest.raises(psycopg.OperationalError,match='closed'):error.value.pgconn.socket
 thread.join(timeout=5);assert not thread.is_alive() and receipt['server_closed']
 after=trust.owned_resources();assert not after['socket_fds']-baseline['socket_fds'];assert after['children']==baseline['children']
 if case=='trusted':assert receipt['tls'] and receipt['startup_received'] and 'DISPOSABLE_TLS_ACCEPTED_NO_DATABASE' in str(error.value)
 elif case=='untrusted':assert evidence['reason_code']=='TLS_CHAIN_VERIFICATION_FAILED_DETAIL_UNAVAILABLE' and not receipt['tls']
 else:assert evidence['reason_code']=='TLS_HOSTNAME_MISMATCH' and not receipt['startup_received']
 record_property('loopback_case',case);record_property('failed_pgconn_finished',True);record_property('owned_tcp_sockets_after',0)


def test_successor_resolves_once_without_address_failover(monkeypatch):
 from verification.ingestion_storage import tls_successor as successor
 from sqlalchemy.engine import make_url
 resolver=MagicMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.2',5432)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',5432))]);factory=MagicMock()
 monkeypatch.setattr(successor.socket,'getaddrinfo',resolver);monkeypatch.setattr(successor,'create_engine',factory)
 successor.single_address_engine(make_url('postgresql+psycopg://user:unused@'+HOST+':5432/postgres'),connect_args={'sslmode':'verify-full','sslrootcert':str(trust.ROOT)})
 assert resolver.call_count==1 and factory.call_args.kwargs['connect_args']['hostaddr']=='127.0.0.1'
 assert factory.call_args.args[0].host==HOST and factory.call_args.kwargs['connect_args']['sslmode']=='verify-full'


def test_redaction_and_no_fabricated_closed_receipt():
 r=trust.failure_evidence(RuntimeError('password=SECRET certificate verify failed'));assert not r['failed_native_connection_finished'] and 'SECRET' not in json.dumps(r)


def test_successor_cannot_reuse_consumed_authority():
 from verification.ingestion_storage import preflight,tls_successor as successor
 sha='a'*40
 env={'GITHUB_SHA':sha,'GITHUB_WORKFLOW_SHA':sha,'GITHUB_REF':'refs/heads/master','GITHUB_REPOSITORY':'maxrose26/PropertyAIgent','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_RUN_NUMBER':'1','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW_REF':'maxrose26/PropertyAIgent/'+successor.WORKFLOW+'@refs/heads/master'}
 assert successor.admitted(sha,successor.AUTHORITY,env)
 assert not successor.admitted(sha,preflight.AUTHORITY,env)
 assert not successor.admitted(sha,successor.AUTHORITY,{**env,'GITHUB_RUN_ATTEMPT':'2'})
 assert not successor.admitted(sha,successor.AUTHORITY,{**env,'GITHUB_RUN_NUMBER':'2'})
 assert not Path(successor.WORKFLOW).exists()


@pytest.mark.parametrize('leak',[False,True])
def test_finished_failure_requires_independent_socket_census(tmp_path,monkeypatch,leak):
 from verification.ingestion_storage import preflight
 snapshots=iter([{'socket_fds':set(),'children':set()},{'socket_fds':{('99','socket:[999]')} if leak else set(),'children':set()}])
 monkeypatch.setattr(trust,'owned_resources',lambda:next(snapshots))
 monkeypatch.setattr(trust,'failure_evidence',lambda exc:{'reason_code':'TLS_CHAIN_VERIFICATION_FAILED_DETAIL_UNAVAILABLE','failed_native_connection_finished':True})
 engine=MagicMock();engine.connect.side_effect=RuntimeError('disposable')
 r=preflight.run('postgresql://postgres.zcikcfgpblzuzpanpdqd:x@'+HOST+':5432/postgres',tmp_path/'out',engine_factory=lambda *a,**k:engine)
 assert r['cleanup']==('UNCERTAIN' if leak else 'CLOSED')
 assert r['connections']==0 and r['driver_statements']==0 and r['pool_disposed']
