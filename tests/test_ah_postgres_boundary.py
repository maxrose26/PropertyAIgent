"""Negative admission tests require no PostgreSQL server or guard monkeypatches."""
import json
import pytest
from sqlalchemy import create_engine
from app.db.ah_claim_schema import migrate_local,require_local
from app.db.ah_disposable_postgres import create_disposable_engine,private_json
from app.policy.ah_claim_store import preview

@pytest.mark.parametrize('operation',[migrate_local,require_local,lambda e:preview(e,[1])])
def test_ordinary_postgres_always_closed(operation):
    e=create_engine('postgresql+psycopg://invalid@127.0.0.1:1/not_a_test')
    try:
        with pytest.raises(ValueError,match='migration remains disabled'):
            operation(e)
    finally:
        e.dispose()


def test_proof_rejects_public_permissions(tmp_path):
    p=tmp_path/'proof.json';p.write_text('{}');p.chmod(0o644)
    with pytest.raises(ValueError,match='ownership/mode'):
        private_json(p)


def test_proof_rejects_symlink(tmp_path):
    p=tmp_path/'proof.json';p.write_text('{}');p.chmod(0o600)
    link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(ValueError,match='symlink'):
        private_json(link)


def test_incomplete_proof_never_connects(tmp_path):
    p=tmp_path/'proof.json';p.write_text(json.dumps({'run_id':'bad'}));p.chmod(0o600)
    with pytest.raises(ValueError):
        create_disposable_engine(p)
