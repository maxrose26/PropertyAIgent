"""Offline exact route/role regression; never opens a database connection."""
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage.operational_controller import runtime_principal,DatabaseBudget
from verification.ingestion_storage.tls_trust import verified_trust

HOST='aws-0-eu-west-2.pooler.supabase.com'
PROJECT='zcikcfgpblzuzpanpdqd'

def trust():
    ca,_=verified_trust()
    return {'sslmode':'verify-full','sslrootcert':str(ca)}

@pytest.mark.parametrize('role',['ingestion_worker_login','ingestion_effect_login','ingestion_application_login'])
def test_exact_pooler_routing_username_and_runtime_transaction_mode(role):
    url=f'postgresql://{role}.{PROJECT}:placeholder@{HOST}:5432/postgres'
    u,actual=runtime_principal(url,trust())
    assert u.username==role+'.'+PROJECT and actual==role
    budget=DatabaseBudget();engine=budget.engine(url,ssl=trust())
    assert engine.get_execution_options()=={}
    # Engine construction is lazy: this regression must never connect.
    assert budget.attempts==0 and budget.statements==0
    assert engine.pool.size()==1
    assert engine.dialect._on_connect_isolation_level==('AUTOCOMMIT' if role=='ingestion_worker_login' else 'READ COMMITTED')
    engine.dispose()

@pytest.mark.parametrize('user',[
    'postgres.'+PROJECT,'ingestion_worker_login','ingestion_worker_login.other',
    'ingestion_storage_login.'+PROJECT,'ingestion_recovery_login.'+PROJECT,
    'ingestion_worker_login.'+PROJECT+'.other'])
def test_other_principals_never_reach_connect(user):
    with pytest.raises(Denied):runtime_principal(f'postgresql://{user}:placeholder@{HOST}:5432/postgres',trust())

@pytest.mark.parametrize('host,port,db,query',[
    ('example.invalid',5432,'postgres',''),(HOST,6543,'postgres',''),
    (HOST,5432,'other',''),(HOST,5432,'postgres','?sslmode=disable'),
])
def test_route_and_query_overrides_rejected(host,port,db,query):
    with pytest.raises(Denied):runtime_principal(f'postgresql://ingestion_worker_login.{PROJECT}:placeholder@{host}:{port}/{db}{query}',trust())

@pytest.mark.parametrize('ssl',[None,{'sslmode':'require'},{'sslmode':'verify-full','sslrootcert':'/tmp/unreviewed-ca'}])
def test_tls_cannot_be_weakened(ssl):
    with pytest.raises(Denied):runtime_principal(f'postgresql://ingestion_worker_login.{PROJECT}:placeholder@{HOST}:5432/postgres',ssl)

def test_disposable_only_recovery_mapping_stays_separate():
    _,role=runtime_principal('postgresql://ingestion_recovery_login:placeholder@127.0.0.1:5432/ingestion_provisioning_test',None)
    assert role=='ingestion_recovery_login'
