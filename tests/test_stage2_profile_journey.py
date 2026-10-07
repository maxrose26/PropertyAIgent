"""Offline Streamlit journey with synthetic admitted identity and SQLite only.
The adapter binds the existing test lease in AppTest's script thread; it does
not test browser OAuth or change application access controls.
"""
from contextlib import contextmanager
from pathlib import Path
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from app.db.models import Base, Council, Site, Application, Settings
from app.security import access
from app.ui import common, access as ui_access


@pytest.mark.parametrize("limited", [True, False])
def test_dashboard_to_same_profile_source_and_return_preserves_buyer(tmp_path,monkeypatch,limited):
    engine=create_engine("sqlite:///"+str(tmp_path/"journey.sqlite"))
    Base.metadata.create_all(engine)  # opt-in historical adapter seeds synthetic buyers
    with Session(engine) as session:
        session.add(Council(code="testcouncil",name="Synthetic council",base_url="https://example.invalid",date_field_mode="received",doc_system="idox"))
        site=Site(council_code="testcouncil",canonical_address="synthetic",display_address="Synthetic journey subject")
        session.add(site);session.flush()
        sid=site.id
        session.add(Application(council_code="testcouncil",site_id=sid,reference="SYN/JOURNEY",
            proposal="Erection of 40 dwellings",decision="Granted",
            decision_issued_date=(dt.date.today()-dt.timedelta(days=3*365-25)).isoformat(),
            unit_confirmation_status="undetermined" if limited else None,
            summary_url="https://example.invalid/planning/SYN-JOURNEY"))
        session.commit()
    actor=access.current_actor()
    def admitted(**kwargs):
        access.registry.check(actor)
        access._current.set(actor)
        return actor
    @contextmanager
    def scope():
        with access.actor_scope(actor): yield actor
    @contextmanager
    def db():
        with access.actor_scope(actor),Session(engine) as session:
            yield session,session.get(Settings,1)
    monkeypatch.setattr(ui_access,"admitted_actor",admitted)
    monkeypatch.setattr(ui_access,"page_scope",scope)
    monkeypatch.setattr(common,"get_db",db)
    monkeypatch.setattr(common,"bootstrap",lambda: access.require_admitted())
    monkeypatch.setattr(common,"credits_sidebar",lambda *_:None)
    root=Path(__file__).resolve().parents[1]
    at=AppTest.from_file(str(root/"app/ui/streamlit_app.py"))
    at.session_state["active_buyer_key"]="nesten_homes"
    at.run(timeout=30)
    assert not at.exception, [(e.message,e.stack_trace) for e in at.exception]
    links=[e.proto for e in at.get("page_link") if "SYN%2FJOURNEY" in str(e.proto) or "SYN/JOURNEY" in str(e.proto)]
    # The emitted destination carries stable subject and source identity.
    assert links
    from app.reporting.buyer_family_feed import build_buyer_opportunity_families
    from app.reporting.family_presentation import present_family_result
    with Session(engine) as session:
        family_view = present_family_result(build_buyer_opportunity_families(session, "nesten_homes", limit=10), {}).families[0]
        subject_params = family_view.best.params
    from app.reporting.opportunity_feed import build_opportunity_feed
    with Session(engine) as session:
        card=next(c for c in build_opportunity_feed(session,limit=10)["cards"] if c["params"].get("site_id")==str(sid))
    at.switch_page("pages/1_Scheme_Detail.py")
    at.query_params.update(card["params"])
    at.query_params["phase_code"]="requested-scope"
    at.run(timeout=30)
    assert not at.exception, [(e.message,e.stack_trace) for e in at.exception]
    text="\n".join(str(e.value) for kind in ("markdown","caption","info","subheader","title") for e in at.get(kind))
    assert "Synthetic journey subject" in text and "SYN/JOURNEY" in text
    assert "wider site" in text and "requested-scope" in text
    assert "Detailed scheme evidence is not available" in text if limited else "Planning" in text
    assert "https://example.invalid/planning/SYN-JOURNEY" in " ".join(str(e.proto) for e in at.get("link_button"))
    assert at.session_state["active_buyer_key"]=="nesten_homes"
    assert any("Back to opportunities" in str(e.proto) for e in at.get("page_link"))
    at.query_params.clear()
    at.query_params.update(subject_params)
    at.run(timeout=30)
    assert not at.exception, [(e.message,e.stack_trace) for e in at.exception]
    def explanation_text():
        return "\n".join(str(e.value) for kind in ("markdown","caption","info","subheader") for e in at.get(kind))
    assert "Originating acquisition subject" in explanation_text()
    assert subject_params["subject_key"] in explanation_text()
    assert "Active buyer: nesten_homes" in explanation_text()
    assert family_view.best.fit_label in explanation_text()
    assert "Why it fits" in explanation_text()
    at.query_params["buyer_key"] = "housing_association"
    at.run(timeout=30)
    assert not at.exception
    assert "Subject-specific mandate explanation unavailable" in explanation_text()
    assert "Originating acquisition subject" not in explanation_text()
    at.query_params["buyer_key"] = "nesten_homes"
    at.query_params["subject_key"] = "tampered-phase"
    at.run(timeout=30)
    assert not at.exception
    assert "Subject-specific mandate explanation unavailable" in explanation_text()
    assert "Originating acquisition subject" not in explanation_text()
    at.query_params["subject_key"] = subject_params["subject_key"]
    selector = next(s for s in at.selectbox if s.label == "Viewing opportunities for")
    different = next(o for o in selector.options if "Housing" in o)
    selector.select(different).run(timeout=30)
    assert not at.exception
    assert at.session_state["active_buyer_key"] == "housing_association"
    assert "Originating acquisition subject" not in explanation_text()
    # Existing buyer-switch security clears navigation; replaying the old
    # buyer's link must still withhold its subject assessment.
    at.query_params.update(subject_params)
    at.run(timeout=30)
    assert "Subject-specific mandate explanation unavailable" in explanation_text()
    assert "Originating acquisition subject" not in explanation_text()
    selector = next(s for s in at.selectbox if s.label == "Viewing opportunities for")
    selector.select(next(o for o in selector.options if "Nesten" in o)).run(timeout=30)
    assert at.session_state["active_buyer_key"] == "nesten_homes"
    at.switch_page("pages/00_Dashboard.py");at.query_params.clear();at.run(timeout=30)
    assert not at.exception
    assert at.session_state["active_buyer_key"]=="nesten_homes"
    engine.dispose()
