"""No production IO. Native libpq/SQLAlchemy against loopback wire fixtures.

Wire fixture is not a PostgreSQL permission/credential acceptance test. It
exercises real startup/TLS/failure transport through the actual factory.
"""
import json,socket,ssl,struct,threading,time
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import psycopg,pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from verification.ingestion_storage.connection_diagnostics import safe_failure
from verification.ingestion_storage.operational_controller import DatabaseBudget
from verification.ingestion_storage.operational_runner import Runner,restricted_url
from verification.ingestion_storage.storage_controller import production_transport
from verification.ingestion_storage.tls_trust import verified_trust,owned_resources

def certs(root,hostname='127.0.0.1'):
    import ipaddress
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'synthetic loopback')])
    san=x509.IPAddress(ipaddress.ip_address(hostname)) if hostname[0].isdigit() else x509.DNSName(hostname)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))
          .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True,path_length=None),True)
          .add_extension(x509.SubjectAlternativeName([san]),False).sign(key,hashes.SHA256()))
    root.mkdir();pem=root/'certificate.pem';private=root/'synthetic-private.pem'
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    private.chmod(0o600)
    return pem,private

def exact(c,n):
    b=b''
    while len(b)<n:
        x=c.recv(n-len(b))
        if not x:raise EOFError()
        b+=x
    return b

@contextmanager
def wire_server(message,state='28000',*,tls=None,delay=False):
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',5432));listener.listen(1);listener.settimeout(5)
    done=threading.Event();errors=[]
    def serve():
        c=None
        try:
            c,_=listener.accept();c.settimeout(5)
            while True:
                size=struct.unpack('!I',exact(c,4))[0];packet=exact(c,size-4)
                if size==8 and packet==struct.pack('!I',80877104):c.sendall(b'N');continue
                if size==8 and packet==struct.pack('!I',80877103):
                    if tls is None:c.sendall(b'N');continue
                    c.sendall(b'S');context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(*map(str,tls));c=context.wrap_socket(c,server_side=True);continue
                break
            if delay:done.wait(4)
            else:
                payload=b'SFATAL\0C'+state.encode()+b'\0M'+message.encode()+b'\0\0'
                c.sendall(b'E'+struct.pack('!I',len(payload)+4)+payload)
        except (EOFError,ssl.SSLError,ConnectionError):pass # TLS negatives intentionally abort
        except BaseException as e:errors.append(type(e).__name__)
        finally:
            if c:c.close()
            listener.close()
    t=threading.Thread(target=serve);t.start()
    try:yield
    finally:done.set();t.join(6);assert not t.is_alive() and not errors

@pytest.mark.parametrize('kind,message,state,expected',[
    ('auth','password authentication failed for user "synthetic-secret"','28P01','AUTHENTICATION_REJECTED'),
    ('routing','Tenant or user not found','XX000','ROUTING_IDENTITY_REJECTED'),
    ('permission','permission denied for database "synthetic"','42501','PERMISSION_DENIED'),
    ('unknown','arbitrary private diagnostic','XX000','UNKNOWN'),
    ('timeout','unused','XX000','CONNECTION_TIMEOUT'),
])
def test_native_factory_startup_failures(kind,message,state,expected):
    before=owned_resources();observed=[];b=DatabaseBudget(emit=lambda e,p:observed.append((e,p)))
    e=b.engine('postgresql://ingestion_worker_login:synthetic@127.0.0.1:5432/ingestion_provisioning_test')
    with wire_server(message,state,delay=kind=='timeout'):
        with pytest.raises(Exception):e.connect()
    receipt=b.close([])
    diagnostic=receipt['connection_diagnostics'][0]
    assert diagnostic['reason_code']==expected
    assert diagnostic['failed_native_connection_finished'] is (kind!='timeout')
    assert receipt['socket_closure']=='NO_NEW_OWNED_SOCKETS'
    assert receipt['cleanup']=='CLOSED' and receipt['connection_attempts']==1 and receipt['driver_statements']==0
    exported=json.dumps(observed)+json.dumps(receipt)
    assert 'synthetic-secret' not in exported and 'arbitrary private diagnostic' not in exported
    after=owned_resources();assert not (after['socket_fds']-before['socket_fds'])

@pytest.mark.parametrize('kind,expected',[('wrong_host','TLS_HOSTNAME_MISMATCH'),('untrusted','TLS_CHAIN_REJECTED')])
def test_native_factory_verify_full_rejects_certificates(tmp_path,kind,expected):
    certificate=certs(tmp_path/'server','wrong.invalid' if kind=='wrong_host' else '127.0.0.1')
    trust=certificate[0] if kind=='wrong_host' else certs(tmp_path/'other')[0]
    b=DatabaseBudget();e=b.engine('postgresql://ingestion_worker_login:synthetic@127.0.0.1:5432/ingestion_provisioning_test',ssl={'sslmode':'verify-full','sslrootcert':str(trust)})
    with wire_server('unused',tls=certificate):
        with pytest.raises(Exception):e.connect()
    r=b.close([]);assert r['cleanup']=='CLOSED'
    assert r['connection_diagnostics'][0]['reason_code']==expected

@pytest.mark.parametrize('password',['A_-safe-token','space :/@%+?#[]\\ quote\" café','%40%2525'])
@pytest.mark.parametrize('role',['ingestion_worker_login','ingestion_effect_login'])
def test_storage_and_operational_native_kwargs_roundtrip(monkeypatch,password,role):
    seen=[]
    def intercept(cls,*args,**kwargs):seen.append(kwargs);raise psycopg.OperationalError('synthetic interception')
    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(intercept))
    monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:intercept(psycopg.Connection,*a,**kw))
    ca,_=verified_trust();trust={'sslmode':'verify-full','sslrootcert':str(ca)}
    raw='postgresql://postgres.zcikcfgpblzuzpanpdqd:synthetic@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'
    storage=production_transport(raw,'192.0.2.1',ca)
    with pytest.raises(psycopg.Error):storage(role,password)
    b=DatabaseBudget();e=b.engine(restricted_url(role,password),ssl=trust,hostaddr='192.0.2.1')
    with pytest.raises(Exception):e.connect()
    b.close([])
    left,right=seen
    for key in ('host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout','prepare_threshold','autocommit'):assert left[key]==right[key]
    assert right['password']==password and right['user']==role+'.zcikcfgpblzuzpanpdqd'
    assert right['options']=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000'

def test_mapping_uses_identical_generated_and_mapped_value(monkeypatch):
    from verification.ingestion_storage.operational_owner import Owner,SECRETS
    generated=[];encrypted=[];mapped={}
    def password(n):assert n==48;v='synthetic-'+str(len(generated));generated.append(v);return v
    monkeypatch.setattr('verification.ingestion_storage.operational_owner.secrets.token_urlsafe',password)
    o=Owner(lambda:None,lambda *_:None,lambda:None,expiry=datetime.now(timezone.utc)+timedelta(minutes=1),bindings={})
    class C:
        def encrypt_password(self,p,r,algorithm):encrypted.append((p.decode(),r.decode(),algorithm));return b'SYNTHETIC-NONVERIFIER'
    @contextmanager
    def connection():yield SimpleNamespace(pgconn=C())
    o.connection=connection;o.q=lambda *a,**k:None;o.script=lambda *a:None
    github=SimpleNamespace(names=lambda:{'DATABASE_URL'},put_secret=lambda n,v:mapped.update({n:v}))
    o.map_and_activate(github,url_factory=restricted_url)
    from sqlalchemy.engine import make_url
    for p,r,algorithm in encrypted:
        assert p in generated and algorithm==b'scram-sha-256'
        assert mapped[SECRETS[r]]==o.urls[r] and make_url(mapped[SECRETS[r]]).password==p
    assert len(set(generated))==2

def test_classifier_unknown_conflict_and_structured_precedence():
    for text in ['private unknown', 'password authentication failed for user x; Tenant or user not found','x'*16385]:
        r=safe_failure(psycopg.OperationalError(text),'DRIVER_CONNECT');assert r['reason_code']=='UNKNOWN' and text not in json.dumps(r)
    r=safe_failure(psycopg.errors.InsufficientPrivilege('private'),'SERVER_IDENTITY')
    assert r['reason_code']=='PERMISSION_DENIED' and r['classification_source']=='SQLSTATE'

@pytest.mark.parametrize('fault',['none','socket','child','memory','connection','uncertain_secret','access'])
def test_shared_closure_requires_each_independent_proof(monkeypatch,fault):
    r=Runner.__new__(Runner);r.baseline={'socket_fds':set(),'children':set()};r.receipts={};r.closed=True
    r.owner=SimpleNamespace(accounting=lambda:dict(connections_opened=2,connections_closed=1 if fault=='connection' else 2,uncertain_effect=False))
    r.github=SimpleNamespace(mutation_uncertain=fault=='uncertain_secret')
    class Memory:
        def close(self):
            if fault=='memory':raise ValueError('private')
            return dict(owned_groups_removed=True,owned_survivors=0)
    r.memory=Memory()
    monkeypatch.setattr('verification.ingestion_storage.operational_runner.owned_resources',lambda:dict(socket_fds={('9','synthetic')} if fault=='socket' else set(),children={'123'} if fault=='child' else set()))
    evidence=r.closure('UNRECONCILED' if fault=='access' else 'DISABLED_VERIFIED')
    assert evidence['overall']==('CLOSED' if fault=='none' else 'UNCERTAIN')
    assert 'private' not in json.dumps(evidence)

def closure_runner():
    r=Runner.__new__(Runner);r.baseline=owned_resources();r.receipts={};r.closed=True;r.memory=None
    r.owner=SimpleNamespace(accounting=lambda:dict(connections_opened=1,connections_closed=1,failed_native_connections=1,failed_native_finished=0,uncertain_effect=False))
    r.github=SimpleNamespace(mutation_uncertain=False)
    return r

def test_failed_administrative_attempt_requires_positive_socket_proof():
    r=closure_runner();left,right=socket.socketpair()
    try:
        proof=r.closure('DISABLED_VERIFIED')
        assert proof['overall']=='UNCERTAIN' and not proof['connections']['failed_administrative_closed']
        assert proof['process']['new_socket_count']==2
    finally:left.close();right.close()
    proof=r.closure('DISABLED_VERIFIED')
    assert proof['overall']=='CLOSED' and proof['connections']['failed_administrative_closed']

def test_live_owned_child_blocks_closure():
    import subprocess,sys
    r=closure_runner();child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    try:
        proof=r.closure('DISABLED_VERIFIED')
        assert proof['overall']=='UNCERTAIN' and proof['process']['live_child_count']>=1
    finally:child.kill();child.wait(timeout=3)
    assert r.closure('DISABLED_VERIFIED')['overall']=='CLOSED'

def test_unknown_socket_inspection_does_not_certify_failed_admin_attempt(monkeypatch):
    r=closure_runner()
    def unavailable():raise OSError('private diagnostic')
    monkeypatch.setattr('verification.ingestion_storage.operational_runner.owned_resources',unavailable)
    proof=r.closure('DISABLED_VERIFIED')
    assert proof['overall']=='UNCERTAIN' and proof['connections']['status']=='UNCERTAIN'

@pytest.mark.parametrize('uncertain',[False,True])
def test_actual_failure_handler_keeps_result_failed_and_separates_closure(tmp_path,uncertain):
    from verification.ingestion_storage.operational_runner import Journal
    r=closure_runner();r.journal=Journal(tmp_path/'failed');r.emit=r.journal.emit;r.operation_phase='RESTRICTED_CONNECTION_QUALIFICATION'
    r.started=time.monotonic();r.phase='admin';r.phase_started=r.started;r.admin_seconds=0;r.runtime_seconds=0
    r.source_attempts=0;r.capture=None;r.source_resources={'status':'NOT_STARTED'}
    r.owner.authorities=[];r.owner.urls={'ingestion_worker_login':'synthetic'};r.owner.effect_uncertain=uncertain;r.owner.invalidation='NOT_REQUIRED_NO_AUTHORITY'
    r.owner.invalidate_failure=lambda:'NOT_REQUIRED_NO_AUTHORITY'
    r.owner.teardown=lambda github:None;r.owner.diagnostics=lambda:{'roles':[]}
    r.github.mutation_uncertain=uncertain;r.github.requests=0;r.github.names=lambda:['DATABASE_URL']
    r.owner.accounting=lambda:dict(connections_opened=1,connections_closed=1,failed_native_connections=1,failed_native_finished=0,uncertain_effect=uncertain)
    result=r.failed(psycopg.OperationalError('Tenant or user not found'))
    assert result['status']=='STOP_RECONCILE_NO_RETRY'
    assert result['cleanup']==('UNCERTAIN' if uncertain else 'CLOSED')
    assert result['closure_components']['process']['status']=='CLOSED'
    assert result['access']==('UNRECONCILED' if uncertain else 'DISABLED_VERIFIED')
    assert result['failure']['reason_code']=='ROUTING_IDENTITY_REJECTED'
