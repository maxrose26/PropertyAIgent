"""No network, DB, credentials or CLI execution. Verify secret handoff boundaries."""
from unittest.mock import MagicMock
import pytest
from verification.ingestion_storage.credential_mapping import install_mapping,put_secret
from verification.ingestion_storage import credential_mapping

def owner_args():
 return ['credential_mapping','--authority',credential_mapping.AUTHORITY,'--accept-verifier-retention','--revision','a'*40,'--binding','registration.json','--binding-sha256','b'*64,'--consumption-record','consumed.json']


def test_noninteractive_owner_input_is_rejected_before_password_prompt(monkeypatch):
 monkeypatch.setattr('sys.argv',owner_args())
 monkeypatch.setattr('sys.stdin.isatty',lambda:False)
 prompt=MagicMock();monkeypatch.setattr(credential_mapping.getpass,'getpass',prompt)
 with pytest.raises(SystemExit,match='SECURE_TTY'):credential_mapping.main()
 prompt.assert_not_called()


def connection():
 c=MagicMock();c.info.host='127.0.0.1';c.info.port=5432;c.info.dbname='ingestion_provisioning_test';c.info.user='provisioning_migrator'
 c.execute.return_value.fetchone.return_value=(False,False,False,False,False,False);c.pgconn.encrypt_password.return_value=b'SCRAM-SHA-256$DISPOSABLE_VERIFIER';return c


def test_direct_mapping_primitive_rejects_non_disposable_connection():
 c=connection();c.info.host='aws-0-eu-west-2.pooler.supabase.com';runner=MagicMock()
 with pytest.raises(ValueError,match='DISPOSABLE_CREDENTIAL'):install_mapping(c,attested=True,runner=runner)
 c.execute.assert_not_called();c.pgconn.encrypt_password.assert_not_called();runner.assert_not_called()


def test_no_mutation_without_explicit_risk_acceptance_or_disposable_fixture():
 c=connection()
 with pytest.raises(ValueError,match='RISK_ACCEPTANCE'):install_mapping(c,attested=False)
 c.execute.assert_not_called()


def test_secret_only_stdin_and_roles_remain_disabled():
 c=connection();runner=MagicMock();runner.return_value.returncode=0
 receipts=install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 assert len(receipts)==2 and all(not r['login_enabled'] for r in receipts)
 assert all('PRIVATE' not in str(r) and 'SCRAM' not in str(r) for r in receipts)
 for call in runner.call_args_list:
  assert 'PRIVATE' not in str(call.args) and b'PRIVATE' in call.kwargs['input']
  assert call.kwargs['timeout']==20
  assert call.kwargs['env']['GH_HOST']=='github.com' and call.kwargs['env']['GH_PROMPT_DISABLED']=='1'
  assert call.kwargs['env']['GH_DEBUG']==''
 assert c.pgconn.encrypt_password.call_count==2
 assert c.execute.call_args_list[0].args==("SET statement_timeout='10s'",)
 assert c.execute.call_args_list[1].args==("SET lock_timeout='3s'",)


def test_failed_secret_upload_stops_without_second_password_or_activation():
 c=connection();runner=MagicMock();runner.return_value.returncode=1
 with pytest.raises(RuntimeError,match='NOT_CONFIRMED'):install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 assert c.pgconn.encrypt_password.call_count==1 and runner.call_count==1


def test_uncertain_database_commit_stops_before_secret_upload():
 c=connection();c.transaction.return_value.__exit__.side_effect=RuntimeError('LOST_ACK');runner=MagicMock()
 with pytest.raises(RuntimeError,match='LOST_ACK'):install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 runner.assert_not_called();assert c.pgconn.encrypt_password.call_count==1


def test_old_provider_attestation_flag_cannot_admit_new_method(monkeypatch):
 monkeypatch.setattr('sys.argv',['credential_mapping','--authority',credential_mapping.AUTHORITY,'--provider-password-redaction-attested'])
 monkeypatch.setattr('sys.stdin.isatty',lambda:True)
 monkeypatch.setattr('sys.stderr.isatty',lambda:True)
 prompt=MagicMock();monkeypatch.setattr(credential_mapping.getpass,'getpass',prompt)
 with pytest.raises(SystemExit):credential_mapping.main()
 prompt.assert_not_called()


def binding():
 from datetime import datetime,timezone,timedelta
 from pathlib import Path
 import hashlib
 paths=['verification/ingestion_storage/credential_mapping.py','verification/ingestion_storage/tls_trust.py','docs/design/ingestion-provisioning-20261016/install.sql','docs/design/ingestion-provisioning-20261016/activate.sql','docs/design/ingestion-provisioning-20261016/revoke.sql','docs/design/ingestion-provisioning-20261016/storage-readback.sql','docs/design/ingestion-readiness-20261016/three-items.json']
 return {'authority':credential_mapping.AUTHORITY,'controller':credential_mapping.CONTROLLER,'risk_acceptance':credential_mapping.RISK,'roles':list(credential_mapping.MAPPINGS),'method':'CLIENT_GENERATED_SCRAM_SHA_256_MEMORY_TO_PROTECTED_SECRET','project':'zcikcfgpblzuzpanpdqd','endpoint':'aws-0-eu-west-2.pooler.supabase.com:5432/postgres','environment':credential_mapping.ENVIRONMENT,'revision':'a'*40,'limits':dict(credential_mapping.LIMITS),'expires_at':(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat(),'hashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}}


@pytest.mark.parametrize('field,value',[('roles',['ingestion_worker_login','another_login']),('controller','another_controller'),('revision','c'*40),('risk_acceptance','PROVIDER_REDACTION_CONFIRMED'),('limits',{'supervised_seconds':241}),('endpoint','another_endpoint'),('method','PLAINTEXT_SQL')])
def test_broader_or_different_registration_fails_before_any_effect(field,value):
 b=binding();b[field]=value
 with pytest.raises(ValueError,match='EXACT_RISK_SCOPE'):credential_mapping.validate_binding(b,'a'*40)


def test_expired_or_changed_content_binding_is_denied():
 b=binding();b['expires_at']='2020-01-01T00:00:00+00:00'
 with pytest.raises(ValueError,match='EXPIRY'):credential_mapping.validate_binding(b,'a'*40)
 b=binding();b['hashes']['docs/design/ingestion-provisioning-20261016/activate.sql']='0'*64
 with pytest.raises(ValueError,match='CONTENT_CHANGED'):credential_mapping.validate_binding(b,'a'*40)


def test_exact_risk_mapping_uses_48_random_bytes_without_redaction_claim(monkeypatch):
 c=connection();c.info.host='aws-0-eu-west-2.pooler.supabase.com';c.info.port=5432;c.info.dbname='postgres';c.info.user='postgres.zcikcfgpblzuzpanpdqd';c.pgconn.ssl_in_use=True
 c.execute.return_value.fetchone.side_effect=[('postgres','postgres',False),(False,False,False,False,False,False),(False,False,False,False,False,False)]
 entropy=MagicMock(return_value='DISPOSABLE_ONLY_'*5);monkeypatch.setattr(credential_mapping.secrets,'token_urlsafe',entropy)
 runner=MagicMock();runner.return_value.returncode=0
 rows=install_mapping(c,risk_binding=binding(),revision='a'*40,runner=runner)
 assert entropy.call_count==2 and all(x.args==(48,) for x in entropy.call_args_list)
 assert [r['role'] for r in rows]==list(credential_mapping.MAPPINGS)
 assert all(not r['login_enabled'] for r in rows)
 assert runner.call_count==2


def test_production_password_factory_override_is_rejected_before_sql():
 c=connection();c.info.host='aws-0-eu-west-2.pooler.supabase.com';c.info.dbname='postgres';c.info.user='postgres.zcikcfgpblzuzpanpdqd';c.pgconn.ssl_in_use=True
 with pytest.raises(ValueError,match='ENTROPY_FACTORY'):install_mapping(c,risk_binding=binding(),revision='a'*40,password_factory=lambda:'bad')
 c.execute.assert_not_called()
