"""Request-local, exact subject navigation; no substitute or private cache."""
from types import SimpleNamespace

import pytest

from app.reporting.profile_destination import resolve_subject_explanation


@pytest.fixture
def resolver(monkeypatch):
    import app.security.access as access
    import app.policy.buyer_profile_store as profiles
    import app.reporting.buyer_family_feed as feed
    monkeypatch.setattr(access, "require_admitted", lambda: None)
    monkeypatch.setattr(profiles, "get_buyer_profile_dataclass", lambda session, key: object() if key == "own" else None)
    calls = []
    monkeypatch.setattr(feed, "load_site_subject_inputs", lambda session, site_id: calls.append(site_id) or SimpleNamespace(delivery=[1, 2], residuals={}))
    parent = SimpleNamespace(subject_key="parent", anchor_id=7, source={"buyer_fit": "parent-fit"})
    phase = SimpleNamespace(subject_key="phase", anchor_id=7, source={"buyer_fit": "phase-fit"})
    other = SimpleNamespace(subject_key="other", anchor_id=8, source={"buyer_fit": "other-fit"})
    monkeypatch.setattr(feed, "evaluate_buyer_families", lambda session, key, inputs, **kwargs:
                        {"families": [SimpleNamespace(members=(parent, phase, other))]})
    return calls, parent, phase


def test_exact_related_subject_not_representative(resolver):
    calls, parent, phase = resolver
    assert resolve_subject_explanation(None, site_id=7, buyer_key="own", subject_key="phase") is phase
    assert calls == [7]


@pytest.mark.parametrize("subject", ["tampered", "other"])
def test_missing_or_other_site_never_substitutes(resolver, subject):
    assert resolve_subject_explanation(None, site_id=7, buyer_key="own", subject_key=subject) is None


@pytest.mark.parametrize("buyer,key,origin", [(None, "phase", None), ("wrong", "phase", None), ("own", None, None), ("own", "phase", "wrong")])
def test_unavailable_buyer_or_navigation_does_not_load_subjects(resolver, buyer, key, origin):
    assert resolve_subject_explanation(None, site_id=7, buyer_key=buyer, subject_key=key, origin_buyer_key=origin) is None
    assert resolver[0] == []


def test_admission_failure_not_swallowed(monkeypatch):
    from app.security.access import AccessDenied
    import app.security.access as access
    def refuse():
        raise AccessDenied("denied")
    monkeypatch.setattr(access, "require_admitted", refuse)
    with pytest.raises(AccessDenied):
        resolve_subject_explanation(None, site_id=7, buyer_key="own", subject_key="phase")


def test_detail_loader_never_queries_full_universe(monkeypatch):
    import app.security.access as access
    from app.reporting.buyer_family_feed import load_site_subject_inputs
    monkeypatch.setattr(access, "require_admitted", lambda: None)
    class Empty:
        def scalars(self): return self
        def all(self): return []
        def __iter__(self): return iter(())
    class Session:
        def __init__(self): self.statements = []
        def execute(self, statement):
            self.statements.append(statement)
            return Empty()
    session = Session()
    inputs = load_site_subject_inputs(session, 7)
    assert inputs.delivery == [] and inputs.strategic == []
    assert len(session.statements) == 4
    for statement in session.statements:
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "applications.site_id = 7" in sql
        assert "local_plan_sites" not in sql


def test_real_authorised_buyer_lookup_denies_ungranted_context(session, monkeypatch):
    """Only synthetic lease acquisition is adapted; real grant-constrained SQL runs."""
    from app.db.models import Buyer
    from app.security.access import AccessDenied
    import app.security.access as access
    import app.services.authorised_reads as reads
    from sqlalchemy import select
    buyers = session.execute(select(Buyer).order_by(Buyer.id)).scalars().all()
    assert len(buyers) >= 2
    actor = SimpleNamespace(workspace_id=buyers[0].workspace_id, buyer_ids=frozenset({buyers[0].id}))
    monkeypatch.setattr(access, "require_admitted", lambda: actor)
    monkeypatch.setattr(reads, "require_admitted", lambda: actor)
    assert reads.buyer_by_key(session, buyers[0].buyer_key).id == buyers[0].id
    with pytest.raises(AccessDenied):
        resolve_subject_explanation(session, site_id=7, buyer_key=buyers[1].buyer_key, subject_key="phase")
