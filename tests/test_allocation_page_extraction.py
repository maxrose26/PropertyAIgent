"""Sprint 3F ("Allocation Policy Page Extraction", Part 9) test suite.

No live council website dependency, no real OpenAI call anywhere - a fake
vision client stands in for the model (same pattern as tests/
test_visual_evidence.py), and every PDF is a small synthetic fixture
generated with reportlab.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.db.models import LocalPlan, LocalPlanSite, VisualEvidence
import app.visuals.rendering as rendering_module
from app.visuals.allocation_identifiers import (
    extract_allocation_identifiers,
    extract_allocation_title,
    normalise_policy_reference,
)
from app.visuals.matching import match_allocation_reference, match_report_visual
from app.visuals.page_detection import detect_candidate_pages_in_pdf, find_allocation_policy_signals
from app.visuals.pipeline import PipelineLimits, PipelineStats, process_local_plan_pdf, process_report
from app.visuals.review import confirm_image, reject_image


# --- fixture helpers ---------------------------------------------------

def _make_pdf(path, pages_text: list[str]) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for text in pages_text:
        c.setFont("Helvetica", 8)
        y = 750
        for line in text.split("\n"):
            c.drawString(72, y, line)
            y -= 12
        c.showPage()
    c.save()


def _make_local_plan(session, council_code="testcouncil", plan_name="Places for Everyone Test Plan") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name=plan_name, status="adopted", raw_status="Adopted")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, council_code="testcouncil", policy_reference="JPA 7", site_name="Elton Reservoir") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Places for Everyone Test Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.commit()
    return allocation


class _FakeVisionResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = None


class _FakeVisionClient:
    """Same fixed-classification-per-call pattern as test_visual_evidence.py,
    optionally returning a DIFFERENT result per call index (results list) so
    a multi-page run can simulate e.g. "map without identifier -> is_useful
    True" vs "policy text continuation -> is_useful False"."""

    def __init__(self, result_or_results):
        self._results = result_or_results if isinstance(result_or_results, list) else None
        self._single = result_or_results if self._results is None else None
        self.calls: list = []
        outer = self

        class _Responses:
            def create(self, model, input, text):
                if outer._results is not None:
                    result = outer._results[min(len(outer.calls), len(outer._results) - 1)]
                else:
                    result = outer._single
                outer.calls.append({"model": model})
                return _FakeVisionResponse(json.dumps(result))

        self.responses = _Responses()


def _classification_result(**overrides) -> dict:
    result = {
        "is_useful": True, "image_type": "allocation_map", "likely_object": "allocation",
        "reason": "an allocation boundary map is shown", "confidence": 0.9, "review_required": True,
    }
    result.update(overrides)
    return result


# Real-style Places for Everyone allocation page text (Sprint 3F live
# research: data/local_plans/bury/places_for_everyone.pdf pages 311/318/321),
# reproduced as a fixture, not read from the real file - kept short enough
# to be a realistic "text-heavy allocation page" without needing the real
# 561-page PDF for routine tests.
JPA7_PAGE_TEXT = """Policy JP Allocation 7 Elton Reservoir
Picture 11.16 JPA 7 Elton Reservoir
Policy
Any proposals for this allocation must be in accordance with a comprehensive
masterplan that has been approved by the LPA. It shall include a clear phasing
strategy as part of an integrated approach to the delivery of infrastructure to
support the scale of the whole development in line with Policy JP-D1
'Infrastructure Implementation'.
Development within this allocation will be required to:
1. Deliver a broad mix of around 3,500 homes to diversify the type of
accommodation in the Bury and Radcliffe areas. This includes an appropriate
mix of house types and sizes, accommodation for older people, plots for
custom and self-build and higher densities of development in areas with good
accessibility and with potential for improved public transport connectivity."""

JPA8_PAGE_TEXT = """Policy JP Allocation 8: Seedfield
Picture 11.17 JPA 8 Seedfield
Policy
Development in this allocation will be required to:
1. Deliver a broad mix of around 140 homes to diversify the type of
accommodation in the Seedfield area."""

JPA9_PAGE_TEXT = """Policy JP Allocation 9: Walshaw
Picture 11.18 JPA 9 Walshaw
Policy
Any proposals for this allocation must be in accordance with a comprehensive
masterplan that has been approved by the LPA."""


# --- 1. allocation page detection (Part 1) ----------------------------------

def test_allocation_policy_signal_detected_from_jpa_style_text():
    signals = find_allocation_policy_signals(JPA7_PAGE_TEXT)
    assert any("allocation reference identifier" in s for s in signals)


def test_text_heavy_allocation_page_is_still_a_candidate(tmp_path):
    # ~700 characters of dense policy prose under the identifier/title -
    # well above page_detection.LOW_TEXT_DENSITY_THRESHOLD (200) - the
    # low-text-density heuristic alone would NOT flag this page, but the
    # allocation-policy signal must, regardless.
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])
    assert len(JPA7_PAGE_TEXT.strip()) > 200  # sanity check on the fixture itself
    candidates = detect_candidate_pages_in_pdf(str(pdf_path))
    assert len(candidates) == 1
    assert any("allocation reference identifier" in r for r in candidates[0]["reasons"])


def test_generic_policy_allocation_pattern_is_a_candidate(tmp_path):
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, ["Policy HOM Allocation 12: a hypothetical future Local Plan's own layout, with substantial policy wording following the identifier and title on this page."])
    candidates = detect_candidate_pages_in_pdf(str(pdf_path))
    assert len(candidates) == 1


def test_unrelated_page_is_not_flagged_as_an_allocation_policy_page():
    assert find_allocation_policy_signals("This is a covering letter with no policy content at all.") == []


# --- 2. identifier extraction (Part 2) --------------------------------------

def test_extracts_jpa_with_space():
    ids = extract_allocation_identifiers("See allocation JPA 7 for details.")
    assert {"raw": "JPA 7", "normalised": "JPA7"} in ids


def test_extracts_jpa_without_space():
    ids = extract_allocation_identifiers("See allocation JPA7 for details.")
    assert any(i["normalised"] == "JPA7" for i in ids)


def test_extracts_jpa_with_decimal_suffix():
    ids = extract_allocation_identifiers("Policies JPA1.1 and JPA1.2 cover Northern Gateway.")
    normalised = {i["normalised"] for i in ids}
    assert "JPA1.1" in normalised
    assert "JPA1.2" in normalised


def test_extracts_policy_jp_allocation_phrasing_as_jpa_code():
    ids = extract_allocation_identifiers("Policy JP Allocation 16 sets out the requirements.")
    assert {"raw": "Policy JP Allocation 16", "normalised": "JPA16"} in ids


def test_extracts_jp_allocation_without_leading_policy():
    ids = extract_allocation_identifiers("JP Allocation 16 sets out the requirements.")
    assert any(i["normalised"] == "JPA16" for i in ids)


def test_extracts_hom_reference():
    ids = extract_allocation_identifiers("Site HOM 2.1 is allocated for housing.")
    assert any(i["normalised"] == "HOM2.1" for i in ids)


def test_extracts_hs_reference():
    ids = extract_allocation_identifiers("Allocation HS1 is shown on the map below.")
    assert any(i["normalised"] == "HS1" for i in ids)


def test_no_identifiers_on_plain_text():
    assert extract_allocation_identifiers("This page has no allocation code printed anywhere.") == []


def test_deduplicates_the_same_identifier_seen_twice():
    ids = extract_allocation_identifiers(JPA7_PAGE_TEXT)  # "JPA 7" and "Policy JP Allocation 7" both -> JPA7
    normalised = [i["normalised"] for i in ids]
    assert normalised.count("JPA7") == 1


# --- 3. identifier normalisation (Part 2) -----------------------------------

def test_normalise_policy_reference_strips_whitespace_and_case():
    assert normalise_policy_reference("JPA 7") == "JPA7"
    assert normalise_policy_reference("jpa7") == "JPA7"
    assert normalise_policy_reference("  JPA   7  ") == "JPA7"


def test_normalise_policy_reference_handles_none_and_empty():
    assert normalise_policy_reference("") == ""


def test_extract_allocation_title_from_policy_jp_allocation_phrasing():
    assert extract_allocation_title(JPA7_PAGE_TEXT) == "Elton Reservoir"


def test_extract_allocation_title_returns_none_when_absent():
    assert extract_allocation_title("This page has policy text but no identifier or title at all.") is None


# --- 4. matching priority chain (Part 5) ------------------------------------

def test_tier1_exact_policy_reference_match(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    other = _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Seedfield")
    result = match_allocation_reference(JPA7_PAGE_TEXT, [allocation, other])
    assert result["allocation_id"] == allocation.id
    assert result["match_method"] == "exact_policy_reference"
    assert result["match_confidence"] == 1.0
    assert result["ambiguous"] is False


def test_tier2_normalised_policy_reference_match(session):
    # Database stores "JPA 7" (with a space); the page prints "JPA7" (no
    # space, e.g. picked up from a differently-formatted source) - only a
    # NORMALISED comparison finds this, not an exact string match.
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    result = match_allocation_reference("Refer to allocation JPA7 shown below.", [allocation])
    assert result["allocation_id"] == allocation.id
    assert result["match_method"] == "normalised_policy_reference"
    assert result["match_confidence"] == 0.9
    assert result["ambiguous"] is False


def test_jp_allocation_phrasing_and_bare_code_for_the_same_number_do_not_double_count(session):
    # Regression (Sprint 3F live validation against the real Places for
    # Everyone PDF): "Policy JP Allocation 7" and "JPA 7" on the SAME
    # single-allocation page must collapse to ONE identifier, not two
    # differently-normalised ones ("JPA7" vs "POLICYJPALLOCATION7") - the
    # real bug this caused was every genuine single-allocation page being
    # wrongly treated as an ambiguous multi-allocation page.
    ids = extract_allocation_identifiers("Policy JP Allocation 7 Elton Reservoir\nPicture 11.16 JPA 7 Elton Reservoir")
    assert len(ids) == 1
    assert ids[0]["normalised"] == "JPA7"


def test_overview_page_listing_many_allocations_is_never_auto_linked(session):
    # Regression (Sprint 3F live validation): Places for Everyone's own
    # Table 11.1 lists ~34 different allocations' codes together on one
    # overview page. Even though only ONE of those codes (JPA 7) happens
    # to already be onboarded as a LocalPlanSite in this database, the
    # page itself is not "about" JPA 7 specifically - it must never be
    # auto-linked, only surfaced as an ambiguous review suggestion.
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    overview_text = (
        "Table 11.1 List of Places for Everyone Allocations\n"
        "Cross Boundary JPA1.1 Northern Gateway Heywood/Pilsworth\n"
        "Cross Boundary JPA1.2 Northern Gateway Simister and Bowlee\n"
        "Cross Boundary JPA2 Stakehill\n"
        "Bury JPA7 Elton Reservoir\n"
        "Bury JPA8 Seedfield\n"
        "Bury JPA9 Walshaw\n"
    )
    result = match_allocation_reference(overview_text, [allocation])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True
    assert result["match_method"] in ("exact_policy_reference", "normalised_policy_reference")


def test_decimal_and_whole_number_jpa_forms_of_the_same_allocation_still_count_as_one(session):
    # "JPA1.1" (bare code, with its decimal sub-part) and "Policy JP
    # Allocation 1" (the same real allocation, referred to without its
    # decimal in running prose) must still be recognised as ONE allocation
    # for ambiguity purposes, not two - this is what makes the overview-
    # page fix above safe for genuinely single-allocation pages that use a
    # compound JPA1.1-style code.
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA1.1", site_name="Northern Gateway")
    result = match_allocation_reference(
        "Policy JP Allocation 1 Northern Gateway\nPicture 11.9 JPA 1.1 Northern Gateway Heywood/Pilsworth", [allocation],
    )
    assert result["allocation_id"] == allocation.id
    assert result["ambiguous"] is False


def test_tier3_exact_allocation_title_match_when_no_code_present(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference=None, site_name="Elton Reservoir")
    result = match_allocation_reference("Policy Allocation 7 Elton Reservoir\nSome policy wording follows.", [allocation])
    assert result["allocation_id"] == allocation.id
    assert result["match_method"] == "exact_allocation_title"
    assert result["ambiguous"] is False


def test_tier1_ambiguous_when_two_allocations_share_the_same_printed_code(session):
    plan = _make_local_plan(session)
    a = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Site A")
    b = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Site B")
    result = match_allocation_reference("Allocation JPA 7 appears here.", [a, b])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True


def test_tier4_high_confidence_review_suggestion_from_substring_fallback(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference=None, site_name="Land off Test Road")
    result = match_allocation_reference("This shows Land off Test Road in context.", [allocation])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True
    assert result["match_method"] == "site_name"


def test_tier5_needs_review_when_nothing_found(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    result = match_allocation_reference("A completely unrelated page with no signal at all.", [allocation])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is False
    assert result["match_method"] is None


def test_never_guesses_between_two_different_identifiers_on_one_page(session):
    plan = _make_local_plan(session)
    a = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    b = _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Seedfield")
    result = match_allocation_reference("A schedule page mentioning both JPA 7 and JPA 8.", [a, b])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True


def test_match_report_visual_delegates_to_the_priority_chain_and_fills_local_plan_id(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    report = SimpleNamespace(local_plan_id=plan.id)
    result = match_report_visual(report, JPA7_PAGE_TEXT, [allocation])
    assert result["allocation_id"] == allocation.id
    assert result["local_plan_id"] == plan.id
    assert result["detected_allocation_reference"] == "JPA 7"
    assert result["detected_allocation_title"] == "Elton Reservoir"


# --- 5. detected reference/title always populated for provenance (Part 7) --

def test_detected_reference_and_title_persist_even_when_no_allocation_matches(session):
    plan = _make_local_plan(session)
    unrelated = _make_allocation(session, plan.id, policy_reference="JPA 99", site_name="Somewhere Else")
    result = match_allocation_reference(JPA7_PAGE_TEXT, [unrelated])
    assert result["allocation_id"] is None
    assert result["detected_allocation_reference"] == "JPA 7"
    assert result["detected_allocation_title"] == "Elton Reservoir"


# --- 6. "map without identifier" (Part 9) -----------------------------------

def test_map_without_identifier_has_no_detected_reference_and_falls_through(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    result = match_allocation_reference("A page showing a site boundary drawing with no printed code or title.", [allocation])
    assert result["detected_allocation_reference"] is None
    assert result["detected_allocation_title"] is None
    assert result["allocation_id"] is None


# --- 7. "policy page without map" (Part 9) - detected but classified not useful --

def test_policy_text_page_with_no_map_is_classified_not_useful(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])  # detected as a candidate via its identifier, even with no real map

    client = _FakeVisionClient(_classification_result(is_useful=False, image_type="unknown", likely_object="unclear"))
    stats = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), stats)

    row = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).one()
    assert row.image_type == "unknown"
    # Deterministic matching still ran and still recorded what it found,
    # independent of the AI classifier's own "not useful" verdict.
    assert row.detected_allocation_reference == "JPA 7"
    assert row.allocation_id == allocation.id


# --- 8. multi-page allocation (Part 9) --------------------------------------

def test_multi_page_allocation_produces_independent_correctly_scoped_rows(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    # Page 1: identifier + title. Page 2: a continuation page (drawing-sheet
    # style, low text + no identifier at all) - both must become their own
    # candidate/row, neither borrowing the other's page number or match.
    _make_pdf(pdf_path, [
        JPA7_PAGE_TEXT,
        "site boundary\nscale 1:1250\nnorth arrow",
    ])

    client = _FakeVisionClient(_classification_result())
    stats = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), stats)

    rows = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).order_by(VisualEvidence.source_page).all()
    assert [r.source_page for r in rows] == [1, 2]
    assert rows[0].detected_allocation_reference == "JPA 7"
    assert rows[0].allocation_id == allocation.id
    assert rows[1].detected_allocation_reference is None  # page 2 printed no code
    assert rows[1].allocation_id is None  # never guessed onto the same allocation just because it's nearby


# --- 9. duplicate prevention / idempotent reruns (Part 6/9) -----------------

def test_rerun_on_unchanged_plan_pdf_creates_no_duplicate_rows(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()
    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, PipelineStats())
    assert len(client.calls) == 1

    stats2 = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, stats2)  # no force
    assert len(client.calls) == 1  # no new AI call
    assert stats2.duplicates_skipped == 1
    assert session.query(VisualEvidence).filter_by(local_plan_id=plan.id).count() == 1


def test_rejected_allocation_page_is_never_reprocessed_even_with_force(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()
    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, PipelineStats())
    row = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).one()
    reject_image(session, row, reason="wrong page", confirmed_by="tester")

    stats2 = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, stats2, force=True)
    assert len(client.calls) == 1  # rejection is never overturned, even with --force
    still_current = session.query(VisualEvidence).filter_by(local_plan_id=plan.id, status="current").one()
    assert still_current.review_status == "rejected"


# --- 10. review workflow (Part 9) -------------------------------------------

def test_confirm_image_on_an_allocation_page_row(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), PipelineStats())
    row = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).one()
    assert row.review_status == "needs_review"

    confirm_image(session, row, confirmed_by="tester", image_type="allocation_map")
    assert row.review_status == "confirmed"
    assert row.image_type == "allocation_map"


# --- 11. Northern Gateway preservation (Part 6/9) ---------------------------

def test_processing_places_for_everyone_pdf_never_touches_an_unrelated_report_scoped_row(session, tmp_path, monkeypatch):
    # Simulates the real situation: Northern Gateway already has a
    # VisualEvidence row from a DIFFERENT source (a MonitoredReport, e.g.
    # Sprint 3C's masterplan pilot) - running the Places for Everyone
    # LOCAL PLAN pdf (a different scope entirely: local_plan_id, not
    # monitored_report_id) for JPA7/8/9 must never touch, duplicate, or
    # supersede that row, since Northern Gateway isn't even one of PfE's
    # own allocations (it belongs to Bury's own Local Plan - Sprint 3E's
    # live finding).
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    elton = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")

    bury_plan = _make_local_plan(session, plan_name="Bury Local Plan")
    northern_gateway = _make_allocation(session, bury_plan.id, policy_reference="JPA1.1", site_name="Northern Gateway")
    existing = VisualEvidence(
        monitored_report_id=None, document_id=None, local_plan_id=bury_plan.id, allocation_id=northern_gateway.id,
        source_page=20, image_type="masterplan", source_document_title="Bury Local Plan",
        review_status="confirmed", status="current", is_primary=True,
    )
    session.add(existing)
    session.commit()
    existing_id = existing.id

    pdf_path = tmp_path / "pfe.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])
    client = _FakeVisionClient(_classification_result())
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), PipelineStats())

    # Northern Gateway's own row: untouched, still current, still confirmed,
    # not superseded, not duplicated.
    ng_rows = session.query(VisualEvidence).filter_by(allocation_id=northern_gateway.id).all()
    assert len(ng_rows) == 1
    assert ng_rows[0].id == existing_id
    assert ng_rows[0].status == "current"
    assert ng_rows[0].review_status == "confirmed"

    # The new PfE row is correctly a SEPARATE, new row for Elton Reservoir.
    elton_rows = session.query(VisualEvidence).filter_by(allocation_id=elton.id).all()
    assert len(elton_rows) == 1
    assert elton_rows[0].id != existing_id


# --- 12. Places for Everyone batch extraction (Part 6/9) -------------------

def test_places_for_everyone_batch_extraction_links_each_page_to_the_right_allocation(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    jpa7 = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    jpa8 = _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Seedfield")
    jpa9 = _make_allocation(session, plan.id, policy_reference="JPA 9", site_name="Walshaw")

    pdf_path = tmp_path / "pfe.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT, JPA8_PAGE_TEXT, JPA9_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    stats = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), stats)

    assert stats.pages_rendered == 3
    assert stats.ai_classifications_run == 3

    rows = {r.allocation_id: r for r in session.query(VisualEvidence).filter_by(local_plan_id=plan.id).all()}
    assert set(rows) == {jpa7.id, jpa8.id, jpa9.id}
    assert rows[jpa7.id].source_page == 1
    assert rows[jpa8.id].source_page == 2
    assert rows[jpa9.id].source_page == 3
    assert rows[jpa7.id].detected_allocation_title == "Elton Reservoir"
    assert rows[jpa8.id].detected_allocation_title == "Seedfield"
    assert rows[jpa9.id].detected_allocation_title == "Walshaw"


def test_places_for_everyone_batch_rerun_is_fully_idempotent(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    _make_allocation(session, plan.id, policy_reference="JPA 8", site_name="Seedfield")
    _make_allocation(session, plan.id, policy_reference="JPA 9", site_name="Walshaw")

    pdf_path = tmp_path / "pfe.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT, JPA8_PAGE_TEXT, JPA9_PAGE_TEXT])
    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()

    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, PipelineStats())
    first_count = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).count()
    assert first_count == 3
    assert len(client.calls) == 3

    stats2 = PipelineStats()
    process_local_plan_pdf(session, client, plan, str(pdf_path), limits, stats2)
    assert len(client.calls) == 3  # no new AI calls at all
    assert stats2.duplicates_skipped == 3
    assert session.query(VisualEvidence).filter_by(local_plan_id=plan.id).count() == 3  # not 6


# --- 13. render hash stability (Part 9) -------------------------------------

def test_render_hash_is_stable_across_reruns_of_the_same_page(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    pdf_path = tmp_path / "plan.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), PipelineStats())
    row = session.query(VisualEvidence).filter_by(local_plan_id=plan.id).one()
    first_hash = row.page_render_hash
    assert first_hash is not None

    process_local_plan_pdf(session, client, plan, str(pdf_path), PipelineLimits(), PipelineStats())  # unchanged rerun
    session.refresh(row)
    assert row.page_render_hash == first_hash  # same source content -> identical hash, no drift


def test_report_scoped_extraction_also_uses_the_new_matching_chain(session, tmp_path, monkeypatch):
    # process_report (MonitoredReport scope) shares match_report_visual with
    # process_local_plan_pdf - confirming the improved matching chain applies
    # there too, not just the --local-plan-id CLI path.
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="JPA 7", site_name="Elton Reservoir")
    report = SimpleNamespace(id=1, local_plan_id=plan.id, council_code="testcouncil", title="PfE", final_url=None, url="https://example.invalid/pfe.pdf")
    pdf_path = tmp_path / "pfe.pdf"
    _make_pdf(pdf_path, [JPA7_PAGE_TEXT])

    client = _FakeVisionClient(_classification_result())
    process_report(session, client, report, str(pdf_path), PipelineLimits(), PipelineStats())

    row = session.query(VisualEvidence).filter_by(monitored_report_id=1).one()
    assert row.allocation_id == allocation.id
    assert row.match_method == "exact_policy_reference"
