"""Exact, registration-bound direct routing for the two restricted logins: route table, principal binding with no fallback, bounded IPv4-only resolution of the restricted host, and REAL TLS
certificate / hostname verification against the direct hostname (loopback wire server; offline compatibility only - it does not prove the production endpoint)."""
import json
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy.engine import make_url
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.connection_diagnostics import PreparationFailure
from verification.ingestion_storage.operational_controller import DatabaseBudget,Denied,runtime_principal
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_preparation import Progress,prepare_connection,dns_command
from verification.ingestion_storage.tls_trust import verified_trust
from tests.test_ingestion_connection_actionable import certs,wire_server

HOST=rr.ROUTES['DIRECT']['host'];POOLER=rr.ROUTES['POOLER']['host'];REF=rr.REF
WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'


def trust():
    ca,_=verified_trust();return {'sslmode':'verify-full','sslrootcert':str(ca)}


def test_the_route_table_is_exact():
    assert HOST=='db.zcikcfgpblzuzpanpdqd.supabase.co' and POOLER=='aws-0-eu-west-2.pooler.supabase.com' and REF=='zcikcfgpblzuzpanpdqd'
    assert rr.username('DIRECT',WORKER)==WORKER and rr.username('POOLER',WORKER)==WORKER+'.'+REF
    for route in ('DIRECT','POOLER'):
        for role in (WORKER,EFFECT):
            u=make_url(rr.url(route,role,'p@ss:word/%'))
            assert (u.host,u.port,u.database,u.username,u.password)==(rr.ROUTES[route]['host'],5432,'postgres',rr.username(route,role),'p@ss:word/%') and rr.identify(u)==(route,role)
    for bad in ('postgres','ingestion_storage_owner','ingestion_recovery_login',''):
        with pytest.raises(ValueError):rr.username('DIRECT',bad)
    with pytest.raises(ValueError):rr.username('FALLBACK',WORKER)
    assert rr.identify(make_url('postgresql://postgres:x@%s:5432/postgres'%HOST)) is None
    assert rr.identify(make_url('postgresql://%s.%s:x@%s:5432/postgres'%(WORKER,REF,HOST))) is None           # the pooler form is not valid on the direct host
    assert rr.identify(make_url('postgresql://%s:x@%s:5432/postgres'%(WORKER,POOLER))) is None               # nor the plain form on the pooler


def test_the_principal_is_bound_to_the_one_registered_route_with_no_fallback():
    direct=rr.url('DIRECT',WORKER,'x');pooler=rr.url('POOLER',WORKER,'x')
    assert runtime_principal(direct,trust(),'DIRECT')[1]==WORKER and runtime_principal(pooler,trust(),'POOLER')[1]==WORKER
    assert runtime_principal(direct,trust())[1]==WORKER                                                      # legacy call without a route still validates exactly
    with pytest.raises(Denied,match='RESTRICTED_ROUTE_MISMATCH'):runtime_principal(direct,trust(),'POOLER')
    with pytest.raises(Denied,match='RESTRICTED_ROUTE_MISMATCH'):runtime_principal(pooler,trust(),'DIRECT')
    for bad in ('postgresql://postgres:x@%s:5432/postgres'%HOST,'postgresql://postgres.%s:x@%s:5432/postgres'%(REF,HOST),'postgresql://%s.%s:x@%s:5432/postgres'%(WORKER,REF,HOST)):
        with pytest.raises(Denied,match='NO_MIGRATION_OR_STRONGER_RUNTIME_PRINCIPAL'):runtime_principal(bad,trust(),'DIRECT')
    with pytest.raises(Denied,match='REVIEWED_TLS_ENDPOINT_REQUIRED'):runtime_principal(direct,{'sslmode':'require'},'DIRECT')
    with pytest.raises(Denied,match='REVIEWED_TLS_ENDPOINT_REQUIRED'):runtime_principal('postgresql://%s:x@elsewhere.example:5432/postgres'%WORKER,trust(),'DIRECT')
    with pytest.raises(Denied,match='REVIEWED_CONNECTION_CONFIGURATION_REQUIRED'):runtime_principal(direct+'?sslmode=disable',trust(),'DIRECT')


def fake_dns(answers):
    seen=[]
    def run(command,**kw):
        host=next(h for h in answers if h in command[-1]);seen.append(host)
        value=answers[host]
        if isinstance(value,int):return SimpleNamespace(returncode=value,stdout=b'')
        return SimpleNamespace(returncode=0,stdout=json.dumps(value).encode())
    run.seen=seen;return run


ADMIN='postgresql+psycopg://postgres.%s:x@%s:5432/postgres'%(REF,POOLER)
REG={'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}


def test_the_restricted_host_gets_its_own_bounded_ipv4_resolution_and_the_admin_address_is_untouched():
    run=fake_dns({POOLER:['203.0.113.7'],HOST:['198.51.100.20']});p=Progress()
    prepared=prepare_connection(REG,ADMIN,progress=p,dns_run=run,restricted_host=HOST)
    assert prepared.hostaddr=='203.0.113.7' and prepared.restricted_hostaddr=='198.51.100.20' and run.seen==[POOLER,HOST]
    assert p.dns['address_count']==1 and p.dns_restricted['address_count']==1 and p.dns_restricted['subprocess_completed'] is True
    only=fake_dns({POOLER:['203.0.113.7']});q=Progress()
    prepared=prepare_connection(REG,ADMIN,progress=q,dns_run=only)
    assert prepared.restricted_hostaddr is None and only.seen==[POOLER]                                         # the pooler route resolves nothing extra
    assert dns_command(HOST)[-1].count(HOST)==1 and 'AF_INET,' in dns_command(HOST)[-1] and 'AF_INET6' not in dns_command(HOST)[-1]


@pytest.mark.parametrize('answer,reason',[(['2a05:d01c:b72:2a00:230e:f62a:3685:4264'],'REVIEWED_IPV4_ONLY'),([],'DNS_NO_ADDRESS'),(2,'DNS_NONZERO_EXIT'),(['not-an-address'],'DNS_INVALID_ADDRESS'),(['198.51.100.%d'%i for i in range(33)],'DNS_TOO_MANY_ADDRESSES')])
def test_an_unusable_direct_host_stops_preparation_with_a_fixed_reason(answer,reason):
    run=fake_dns({POOLER:['203.0.113.7'],HOST:answer})
    with pytest.raises(PreparationFailure) as caught:prepare_connection(REG,ADMIN,progress=Progress(),dns_run=run,restricted_host=HOST)
    assert caught.value.reason==reason and caught.value.stage=='DNS_RESOLUTION'


def make_runner(tmp_path,mode):
    registration=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,
                      evidence_directory='docs/design/ingestion-operational-execution-fixture',mode=mode,reuse_accepted_operational_installation=True)
    tmp_path.mkdir(parents=True,exist_ok=True)
    return orr.Runner(registration,Journal(tmp_path/'j'),lambda:None,source_reader=lambda r:None,github=SimpleNamespace(check=None,requests=0,mutation_uncertain=False),url_factory=lambda r,p:'',identity='postgres')


def test_the_direct_mode_is_a_finite_policy_free_diagnostic_on_the_one_direct_route(tmp_path):
    r=make_runner(tmp_path/'d',orr.DIRECT_MODE)
    assert r.route_name=='DIRECT' and r.settle_seconds==0 and r.owner.apply_policy is False and r.owner.permitted_policy_states==('SUCCESSOR_POLICY_APPLIED',)
    assert r.deadlines==orr.MATRIX_DEADLINES and r.owner.limits['commands']==orr.DIRECT_OWNER_LIMITS['commands'] and r.owner.limits['connections']==orr.DIRECT_OWNER_LIMITS['connections']
    assert r.authority==orr.AUTHORITY                                                                          # never used: the mode issues no grant
    other=make_runner(tmp_path/'p',orr.SETTLED_R2_MODE)
    assert other.route_name=='POOLER' and other.restricted_hostaddr is None and other.deadlines==orr.DEFAULT_DEADLINES


def test_a_direct_run_without_its_own_resolved_address_never_borrows_the_pooler_address(tmp_path):
    r=make_runner(tmp_path/'d',orr.DIRECT_MODE);r.hostaddr='203.0.113.7'
    with pytest.raises(Denied,match='DIRECT_ROUTE_ADDRESS_REQUIRED'):r.restricted_address()
    r.restricted_hostaddr='198.51.100.20';assert r.restricted_address()=='198.51.100.20'
    p=make_runner(tmp_path/'p',orr.SETTLED_R2_MODE);p.hostaddr='203.0.113.7';assert p.restricted_address()=='203.0.113.7'


def test_the_direct_diagnostic_is_not_a_capture_mode_and_binds_all_three_consumed_runs():
    assert orr.DIRECT_MODE in orr.DIAGNOSTIC_MODES and orr.DIRECT_MODE not in orr.SETTLED_MODES and orr.DIRECT_AUTHORITY not in (orr.AUTHORITY,orr.SETTLED_AUTHORITY,orr.SETTLED_R2_AUTHORITY)
    assert set(orr.DIRECT_PREDECESSOR)=={'state_directory','registration_sha256','events_sha256','final_result_sha256','run_1','run_2','run_3'} or set(orr.DIRECT_PREDECESSOR)>={'run_1','run_2','run_3'}
    assert orr.DIRECT_STATE not in {orr.SETTLED_STATE,orr.SETTLED_R2_STATE,orr.DIAGNOSTIC_STATE,orr.MATRIX_STATE} and orr.DIRECT_STATE.endswith('20261020')


@pytest.mark.parametrize('kind',['ok','wrong_host','untrusted'])
def test_real_tls_certificate_and_hostname_verification_for_the_direct_hostname(tmp_path,monkeypatch,kind):
    certificate=certs(tmp_path/'server','wrong.invalid' if kind=='wrong_host' else HOST)
    pinned=certs(tmp_path/'other',HOST)[0] if kind=='untrusted' else certificate[0]
    monkeypatch.setattr('verification.ingestion_storage.tls_trust.verified_trust',lambda now=None:(pinned,{}))
    b=DatabaseBudget();e=b.engine(rr.url('DIRECT',WORKER,'synthetic'),ssl={'sslmode':'verify-full','sslrootcert':str(pinned)},hostaddr='127.0.0.1',route='DIRECT')
    with wire_server('synthetic server answer','28000',tls=certificate):
        with pytest.raises(Exception):e.connect()
    receipt=b.close([]);reason=receipt['connection_diagnostics'][0]['reason_code']
    assert receipt['cleanup']=='CLOSED' and receipt['connection_attempts']==1
    if kind=='ok':assert not reason.startswith('TLS')                    # TLS and the hostname were accepted; the synthetic server then refused the login
    else:assert reason==('TLS_HOSTNAME_MISMATCH' if kind=='wrong_host' else 'TLS_CHAIN_REJECTED')


def test_the_connection_uses_the_pinned_address_the_direct_hostname_and_the_plain_role(monkeypatch):
    seen=[]
    import psycopg
    def intercept(cls,*a,**kw):seen.append(kw);raise psycopg.OperationalError('synthetic interception')
    monkeypatch.setattr(psycopg.Connection,'connect',classmethod(intercept))
    b=DatabaseBudget();e=b.engine(rr.url('DIRECT',EFFECT,'synthetic'),ssl=trust(),hostaddr='198.51.100.20',route='DIRECT')
    with pytest.raises(Exception):e.connect()
    b.close([])
    kw=seen[0]
    assert (kw['host'],kw['hostaddr'],kw['port'],kw['dbname'],kw['user'],kw['sslmode'])==(HOST,'198.51.100.20',5432,'postgres',EFFECT,'verify-full') and kw['sslrootcert']==trust()['sslrootcert']
    assert kw['options']=='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000' and kw['connect_timeout']==3 and len(seen)==1
