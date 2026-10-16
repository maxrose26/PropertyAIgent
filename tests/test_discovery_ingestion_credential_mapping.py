"""No network, DB, credentials or CLI execution. Verify secret handoff boundaries."""
from unittest.mock import MagicMock
import pytest
from verification.ingestion_storage.credential_mapping import install_mapping,put_secret


def connection():
 c=MagicMock();c.execute.return_value.fetchone.return_value=(False,False,False,False,False,False);c.pgconn.encrypt_password.return_value=b'SCRAM-SHA-256$DISPOSABLE_VERIFIER';return c


def test_no_mutation_without_provider_redaction_attestation():
 c=connection()
 with pytest.raises(ValueError,match='ATTESTATION'):install_mapping(c,attested=False)
 c.execute.assert_not_called()


def test_secret_only_stdin_and_roles_remain_disabled():
 c=connection();runner=MagicMock();runner.return_value.returncode=0
 receipts=install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 assert len(receipts)==2 and all(not r['login_enabled'] for r in receipts)
 assert all('PRIVATE' not in str(r) and 'SCRAM' not in str(r) for r in receipts)
 for call in runner.call_args_list:
  assert 'PRIVATE' not in str(call.args) and b'PRIVATE' in call.kwargs['input']
  assert call.kwargs['timeout']==20
 assert c.pgconn.encrypt_password.call_count==2


def test_failed_secret_upload_stops_without_second_password_or_activation():
 c=connection();runner=MagicMock();runner.return_value.returncode=1
 with pytest.raises(RuntimeError,match='NOT_CONFIRMED'):install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 assert c.pgconn.encrypt_password.call_count==1 and runner.call_count==1


def test_uncertain_database_commit_stops_before_secret_upload():
 c=connection();c.transaction.return_value.__exit__.side_effect=RuntimeError('LOST_ACK');runner=MagicMock()
 with pytest.raises(RuntimeError,match='LOST_ACK'):install_mapping(c,attested=True,runner=runner,password_factory=lambda:'DISPOSABLE_PRIVATE_VALUE_'*3)
 runner.assert_not_called();assert c.pgconn.encrypt_password.call_count==1
