"""Shared pytest fixtures for Policy Intelligence tests.

Every test runs against a fresh in-memory SQLite database (Base.metadata.
create_all against sqlite:///:memory:) - never the real data/deal_finder.db.
Nothing under tests/ should import app.db.session.get_engine/get_session,
since those point at the real on-disk database.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Council


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    db = session_local()
    db.add(Council(
        code="testcouncil", name="Test Council", base_url="https://example.invalid",
        date_field_mode="received", doc_system="idox",
    ))
    db.commit()
    yield db
    db.close()
    engine.dispose()
