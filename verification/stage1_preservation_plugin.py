"""Explicit opt-in pytest adapter for the historical acceptance suite only."""
import pytest
from verification.stage1_test_context import synthetic_context,seed_fixture

@pytest.fixture(autouse=True)
def stage1_historical_context(tmp_path,monkeypatch):
    from app.db.models import Base
    original=Base.metadata.create_all
    def create_all(bind,*args,**kwargs):
        original(bind,*args,**kwargs)
        seed_fixture(bind)
    monkeypatch.setattr(Base.metadata,'create_all',create_all)
    with synthetic_context(tmp_path): yield
