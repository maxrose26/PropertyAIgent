import hashlib
import pytest
from verification.ingestion_storage import tameside_package as p

def test_exact_policy_recipe():
 policy=p.seal_policy(manifest_sha256='a'*64,bound_at=1794934800)
 assert policy['expires_at']==1794936715 and policy['max_runs']==1
 assert policy['expected_stop']['hard_stop_generation']==16
 from app.ingestion.ledger import digest
 from app.ingestion.listing_screening import ScreeningRule,RULE_V3
 assert policy['screening_config']==digest(ScreeningRule(RULE_V3,unit_threshold=10,link_related=False).config())
 assert policy['councils']['tameside']['contract']=='tameside-screening-metadata-five-v1'
 command=p.job_command(policy,policy_path='/tmp/tameside-policy.json',output='/tmp/tameside-result')
 assert hashlib.sha256(p.encode_policy(policy)).hexdigest() in command
 assert p.PERIOD in command and 'owner_pilot_job' not in command

@pytest.mark.parametrize('extra',[{'hostaddr':'1.1.1.1'},{'bound_at':p.EXPIRY-2099},{'manifest_sha256':'WITHHELD'}])
def test_seal_refuses_drift(extra):
 args=dict(manifest_sha256='a'*64,bound_at=1794934800);args.update(extra)
 with pytest.raises(ValueError):p.seal_policy(**args)


def test_production_inventory_is_source_derived():
 from verification.ingestion_storage.tameside_owner_access import expected_functions
 policy=p.seal_policy(manifest_sha256='a'*64,bound_at=1794934800)
 expected=expected_functions(policy)
 assert len(expected)==9
 assert expected['ingestion_register_bolton_exception']['sha256']=='b1cb4b54493ce2b1ed2a90acb996a70e96cce9545171f57f7c9efd03ae4b382a'
 assert expected['ingestion_register_campaign_once']['security_definer'] is True
