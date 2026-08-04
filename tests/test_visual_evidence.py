"""Sprint 3C ("Allocation and Site-Plan Image Extraction", Part 18) - test
suite for the app.visuals package. No live council website dependency, no
real OpenAI call anywhere - a fake client stands in for the vision model
(matching the pattern already used for text extraction, see
tests/test_plan_evidence_extraction.py), and every PDF is a small
synthetic fixture generated with reportlab, never a real downloaded
document.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.db.models import Application, Document, LocalPlan, LocalPlanSite, Site, VisualEvidence
from app.visuals import IMAGE_TYPES
import app.visuals.rendering as rendering_module
from app.visuals.classification import CLASSIFICATION_SCHEMA, classify_page, normalise_classification
from app.visuals.document_selection import classify_document_candidacy, select_candidate_documents
from app.visuals.matching import find_allocation_mentions, match_document_visual, match_report_visual
from app.visuals.page_detection import detect_candidate_pages_in_pdf
from app.visuals.pipeline import PipelineLimits, PipelineStats, process_document
from app.visuals.primary_selection import compute_primary_flags, select_primary
from app.visuals.rendering import compute_file_hash, compute_page_render_hash, render_page, safe_storage_key
from app.visuals.review import reject_image
from app.visuals.site_view import build_site_visual_evidence


# --- fixture helpers ---------------------------------------------------

def _make_pdf(path, pages_text: list[str]) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for text in pages_text:
        c.setFont("Helvetica", 10)
        c.drawString(72, 700, text)
        c.showPage()
    c.save()


def _make_site(session, council_code="testcouncil", address="1 Test Street") -> Site:
    site = Site(council_code=council_code, canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_application(session, council_code="testcouncil", reference="APP/1", site_id=None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, proposal="10 dwellings")
    session.add(app)
    session.commit()
    return app


def _make_document(session, application_id, local_path, document_name="Site Plan.pdf", doc_type="other") -> Document:
    doc = Document(application_id=application_id, local_path=str(local_path), document_name=document_name, doc_type=doc_type)
    session.add(doc)
    session.commit()
    return doc


def _make_local_plan(session, council_code="testcouncil") -> LocalPlan:
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status="adopted", raw_status="Adopted")
    session.add(plan)
    session.commit()
    return plan


def _make_allocation(session, local_plan_id, council_code="testcouncil", policy_reference="HOM 1.1", site_name="Land off Test Road") -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=local_plan_id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.commit()
    return allocation


class _FakeVisionResponse:
    def __init__(self, output_text):
        self.output_text = output_text
        self.usage = None


class _FakeVisionClient:
    """result: a single fixed classification dict returned for EVERY call
    (matching tests/test_plan_evidence_extraction.py's fake-client pattern
    for text extraction) - the real image bytes on disk are irrelevant to
    what any test here asserts."""

    def __init__(self, result: dict):
        self._result = result
        self.calls: list = []
        outer = self

        class _Responses:
            def create(self, model, input, text):
                outer.calls.append({"model": model})
                return _FakeVisionResponse(json.dumps(outer._result))

        self.responses = _Responses()


def _classification_result(**overrides) -> dict:
    result = {
        "is_useful": True, "image_type": "site_location_plan", "likely_object": "site",
        "reason": "a boundary is shown", "confidence": 0.9, "review_required": True,
    }
    result.update(overrides)
    return result


# --- 1. candidate document selection (Part 4) --------------------------

def test_high_priority_title_term_is_a_candidate():
    is_candidate, term = classify_document_candidacy("Site Location Plan.pdf")
    assert is_candidate
    assert term == "site location plan"


def test_excluded_term_wins_even_with_a_matching_title():
    is_candidate, _ = classify_document_candidacy("Site Plan cover letter")
    assert not is_candidate


def test_excluded_doc_type_is_never_a_candidate_even_with_matching_title():
    is_candidate, _ = classify_document_candidacy("Site Plan", doc_type="officer_report")
    assert not is_candidate


def test_adopted_plan_report_type_is_always_a_candidate_regardless_of_title():
    is_candidate, term = classify_document_candidacy("Appendix 3", doc_type="adopted_plan")
    assert is_candidate
    assert term is None


def test_unrelated_document_is_not_a_candidate():
    is_candidate, _ = classify_document_candidacy("Planning Statement.pdf")
    assert not is_candidate


def test_select_candidate_documents_filters_a_mixed_list(session):
    app = _make_application(session)
    keep = Document(application_id=app.id, document_name="Site Location Plan.pdf", doc_type="other")
    drop = Document(application_id=app.id, document_name="Planning Statement.pdf", doc_type="planning_statement")
    session.add_all([keep, drop])
    session.commit()
    result = select_candidate_documents([keep, drop])
    assert [c["document"].id for c in result] == [keep.id]


# --- 2. candidate page detection (Part 5) -------------------------------

def test_detect_candidate_pages_flags_the_page_with_a_real_text_signal(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, [
        "Nothing relevant here, just administrative body text about fees and validation.",
        "This page shows the site boundary and red line clearly marked in the drawing.",
    ])
    candidates = detect_candidate_pages_in_pdf(str(pdf_path))
    assert [c["page_number"] for c in candidates] == [2]
    assert any("site boundary" in reason or "red line" in reason for reason in candidates[0]["reasons"])


def test_detect_candidate_pages_ignores_a_purely_textual_document(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, [
        "This is an ordinary planning statement page discussing policy compliance at length.",
        "Further discussion of viability, affordable housing calculations, and s106 obligations.",
    ])
    assert detect_candidate_pages_in_pdf(str(pdf_path)) == []


# --- 3. page-number preservation -----------------------------------------

def test_multi_page_pdf_preserves_correct_page_numbers(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["ordinary body text, nothing to see here", "site boundary shown on this page", "more ordinary body text"])
    candidates = detect_candidate_pages_in_pdf(str(pdf_path))
    assert [c["page_number"] for c in candidates] == [2]


def test_render_page_renders_the_requested_page_not_always_the_first(tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["PAGE ONE CONTENT ONLY"] * 1 + ["PAGE TWO IS COMPLETELY DIFFERENT CONTENT"])
    r1 = render_page(str(pdf_path), 1, "testcouncil", 1)
    r2 = render_page(str(pdf_path), 2, "testcouncil", 1)
    assert r1 is not None and r2 is not None
    assert r1["file_hash"] != r2["file_hash"]
    assert r1["image_path"] != r2["image_path"]


# --- 4. stable page hashing ------------------------------------------------

def test_compute_file_hash_is_stable_for_identical_content(tmp_path):
    p1, p2 = tmp_path / "a.pdf", tmp_path / "b.pdf"
    p1.write_bytes(b"identical content")
    p2.write_bytes(b"identical content")
    assert compute_file_hash(p1) == compute_file_hash(p2)


def test_compute_file_hash_differs_for_different_content(tmp_path):
    p1, p2 = tmp_path / "a.pdf", tmp_path / "b.pdf"
    p1.write_bytes(b"content A")
    p2.write_bytes(b"content B")
    assert compute_file_hash(p1) != compute_file_hash(p2)


def test_compute_page_render_hash_is_deterministic_and_page_specific():
    h1 = compute_page_render_hash("filehash123", 1)
    h2 = compute_page_render_hash("filehash123", 1)
    h3 = compute_page_render_hash("filehash123", 2)
    assert h1 == h2
    assert h1 != h3


def test_compute_page_render_hash_changes_with_render_version():
    h1 = compute_page_render_hash("filehash123", 1, render_version="v1")
    h2 = compute_page_render_hash("filehash123", 1, render_version="v2")
    assert h1 != h2


# --- 5. safe filename/storage-key generation (Part 6/Part 17) -------------

def test_safe_storage_key_sanitises_path_traversal_characters():
    key = safe_storage_key("../../evil", "../../../etc/passwd", 1)
    assert "/" not in key
    assert "\\" not in key
    assert ".." not in key


def test_safe_storage_key_is_stable_for_same_inputs():
    assert safe_storage_key("bury", 37, 1) == safe_storage_key("bury", 37, 1)


def test_safe_storage_key_differs_by_page_number():
    assert safe_storage_key("bury", 37, 1) != safe_storage_key("bury", 37, 2)


# --- 6. image-type schema validation (Part 3/Part 7) -----------------------

def test_classification_schema_enum_matches_image_types_exactly():
    assert set(CLASSIFICATION_SCHEMA["properties"]["image_type"]["enum"]) == set(IMAGE_TYPES)


def test_classification_schema_is_strict_with_no_additional_properties():
    assert CLASSIFICATION_SCHEMA["additionalProperties"] is False
    assert set(CLASSIFICATION_SCHEMA["required"]) == set(CLASSIFICATION_SCHEMA["properties"].keys())


def test_normalise_classification_clamps_invalid_image_type_to_unknown():
    result = normalise_classification({
        "is_useful": True, "image_type": "not_a_real_type", "likely_object": "site",
        "reason": "x", "confidence": 0.5, "review_required": False,
    })
    assert result["image_type"] == "unknown"


def test_normalise_classification_clamps_confidence_into_zero_one_range():
    result = normalise_classification({
        "is_useful": False, "image_type": "unknown", "likely_object": "unclear",
        "reason": None, "confidence": 5, "review_required": False,
    })
    assert result["confidence"] == 1.0


# --- 7. red-line-not-inferred-without-evidence (Part 7) --------------------

def test_normalise_classification_never_infers_boundary_type_from_reason_text():
    # A "reason" that mentions a red line does NOT get auto-promoted to
    # red_line_boundary just because the word appears - this module never
    # keyword-sniffs free text to invent a classification the model itself
    # didn't actually report (Part 7's explicit anti-invention rule).
    result = normalise_classification({
        "is_useful": True, "image_type": "site_location_plan", "likely_object": "site",
        "reason": "A clear red line boundary is visible around the site", "confidence": 0.9, "review_required": True,
    })
    assert result["image_type"] == "site_location_plan"


def test_classify_page_forces_review_required_true_for_a_useful_classification(tmp_path):
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"\x89PNG\r\nfake bytes for a fake image")
    # The fake model itself under-reports review_required=False - the
    # pipeline never trusts that for a useful classification (Part 9/10).
    client = _FakeVisionClient(_classification_result(review_required=False))
    result = classify_page(client, str(image_path))
    assert result["is_useful"] is True
    assert result["review_required"] is True


# --- 8. deterministic Application -> Site inheritance (Part 8) -------------

def test_match_document_visual_inherits_application_and_site():
    document = SimpleNamespace(application_id=42, application=SimpleNamespace(site_id=9))
    result = match_document_visual(document)
    assert result == {
        "application_id": 42, "site_id": 9, "local_plan_id": None, "allocation_id": None,
        "match_method": "document_application_inheritance", "match_confidence": 1.0, "ambiguous": False,
    }


def test_match_document_visual_leaves_site_null_when_application_unlinked():
    document = SimpleNamespace(application_id=42, application=SimpleNamespace(site_id=None))
    result = match_document_visual(document)
    assert result["application_id"] == 42
    assert result["site_id"] is None


# --- 9. allocation-reference matching (Part 8) ------------------------------

def test_find_allocation_mentions_matches_exact_policy_reference():
    allocations = [SimpleNamespace(id=1, policy_reference="HOM 2.30", site_name="Land off Test Road")]
    hits = find_allocation_mentions("This page discusses allocation HOM 2.30 in detail.", allocations)
    assert len(hits) == 1
    assert hits[0]["method"] == "policy_reference"
    assert hits[0]["allocation"].id == 1


def test_match_report_visual_auto_links_on_a_single_unambiguous_reference_match(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="HOM 2.30")
    other = _make_allocation(session, plan.id, policy_reference="HOM 2.31", site_name="A different site")
    report = SimpleNamespace(local_plan_id=plan.id)
    result = match_report_visual(report, "Allocation HOM 2.30 is shown on this page.", [allocation, other])
    assert result["allocation_id"] == allocation.id
    assert result["ambiguous"] is False


# --- 10. ambiguous matching enters review, never guessed (Part 8) ----------

def test_match_report_visual_leaves_ambiguous_when_two_references_appear(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference="HOM 2.30")
    other = _make_allocation(session, plan.id, policy_reference="HOM 2.31")
    report = SimpleNamespace(local_plan_id=plan.id)
    result = match_report_visual(report, "Allocations HOM 2.30 and HOM 2.31 both appear here.", [allocation, other])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True


def test_match_report_visual_leaves_ambiguous_on_a_name_only_match(session):
    plan = _make_local_plan(session)
    allocation = _make_allocation(session, plan.id, policy_reference=None, site_name="Land off Test Road")
    report = SimpleNamespace(local_plan_id=plan.id)
    result = match_report_visual(report, "This shows Land off Test Road.", [allocation])
    assert result["allocation_id"] is None
    assert result["ambiguous"] is True
    assert result["match_method"] == "site_name"


# --- 11. primary-image ranking (Part 9) -------------------------------------

def test_select_primary_prefers_confirmed_over_higher_confidence_unreviewed():
    unreviewed_high_confidence = SimpleNamespace(id=1, review_status="needs_review", image_type="site_location_plan", extraction_confidence=0.99, status="current")
    confirmed_lower_priority_type = SimpleNamespace(id=2, review_status="confirmed", image_type="masterplan", extraction_confidence=0.4, status="current")
    winner = select_primary([unreviewed_high_confidence, confirmed_lower_priority_type], "site")
    assert winner.id == 2


def test_select_primary_falls_back_to_highest_confidence_when_nothing_confirmed():
    low = SimpleNamespace(id=1, review_status="needs_review", image_type="masterplan", extraction_confidence=0.3, status="current")
    high = SimpleNamespace(id=2, review_status="needs_review", image_type="site_location_plan", extraction_confidence=0.8, status="current")
    assert select_primary([low, high], "site").id == 2


def test_select_primary_never_returns_a_rejected_image():
    only = SimpleNamespace(id=1, review_status="rejected", image_type="red_line_boundary", extraction_confidence=1.0, status="current")
    assert select_primary([only], "site") is None


def test_select_primary_ignores_superseded_images():
    superseded = SimpleNamespace(id=1, review_status="confirmed", image_type="red_line_boundary", extraction_confidence=1.0, status="superseded")
    assert select_primary([superseded], "site") is None


def test_compute_primary_flags_marks_exactly_one_winner():
    a = SimpleNamespace(id=1, review_status="needs_review", image_type="masterplan", extraction_confidence=0.3, status="current")
    b = SimpleNamespace(id=2, review_status="needs_review", image_type="site_location_plan", extraction_confidence=0.8, status="current")
    flags = compute_primary_flags([a, b], "site")
    assert flags == {1: False, 2: True}


# --- 12. human-confirmed outranks AI regardless of type priority (Part 9) --

def test_any_confirmed_image_outranks_any_unreviewed_image_of_a_higher_priority_type():
    confirmed_low_priority = SimpleNamespace(id=1, review_status="confirmed", image_type="phasing_plan", extraction_confidence=0.1, status="current")
    unreviewed_top_priority = SimpleNamespace(id=2, review_status="needs_review", image_type="red_line_boundary", extraction_confidence=1.0, status="current")
    winner = select_primary([confirmed_low_priority, unreviewed_top_priority], "site")
    assert winner.id == 1


# --- 13. rejected image stays rejected on rerun, even with --force (Part 10) -

def test_rejected_image_is_never_reprocessed_even_with_force(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["a page showing the site boundary clearly marked"])
    document = _make_document(session, application.id, pdf_path)

    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()
    process_document(session, client, document, limits, PipelineStats())
    assert len(client.calls) == 1

    row = session.query(VisualEvidence).filter_by(document_id=document.id).one()
    reject_image(session, row, reason="not actually useful evidence", confirmed_by="tester")

    stats2 = PipelineStats()
    process_document(session, client, document, limits, stats2, force=True)
    assert len(client.calls) == 1  # no new AI call - the rejection was never touched
    assert stats2.duplicates_skipped == 1
    still_current = session.query(VisualEvidence).filter_by(document_id=document.id, status="current").one()
    assert still_current.review_status == "rejected"


# --- 14. unchanged-document rerun is idempotent (Part 14) -------------------

def test_unchanged_document_rerun_makes_no_new_ai_call_or_duplicate_row(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["a page showing the site boundary clearly marked"])
    document = _make_document(session, application.id, pdf_path)

    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()
    process_document(session, client, document, limits, PipelineStats())
    assert len(client.calls) == 1

    stats2 = PipelineStats()
    process_document(session, client, document, limits, stats2)  # no force
    assert len(client.calls) == 1
    assert stats2.duplicates_skipped == 1
    assert session.query(VisualEvidence).filter_by(document_id=document.id).count() == 1


# --- 15. a genuinely changed source supersedes, never mutates in place (Part 14) -

def test_changed_source_creates_a_new_current_row_and_supersedes_the_old_one(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["version one showing the site boundary clearly marked"])
    document = _make_document(session, application.id, pdf_path)

    client = _FakeVisionClient(_classification_result())
    limits = PipelineLimits()
    process_document(session, client, document, limits, PipelineStats())
    original = session.query(VisualEvidence).filter_by(document_id=document.id).one()
    from app.visuals.review import confirm_image
    confirm_image(session, original, confirmed_by="tester")
    assert original.review_status == "confirmed"

    # The source file at the same local_path genuinely changes content -
    # a real re-scrape/re-download replacing the file, not a fresh upload.
    _make_pdf(pdf_path, ["version two - completely different content, site boundary clearly marked"])
    process_document(session, client, document, limits, PipelineStats())  # no --force needed - hash changed
    assert len(client.calls) == 2  # a genuine second AI call happened

    rows = session.query(VisualEvidence).filter_by(document_id=document.id).order_by(VisualEvidence.id).all()
    assert len(rows) == 2
    old_row, new_row = rows
    assert old_row.id == original.id
    assert old_row.status == "superseded"
    assert old_row.superseded_by_id == new_row.id
    assert old_row.review_status == "confirmed"  # the human decision on the OLD version is preserved, not overwritten
    assert new_row.status == "current"
    assert new_row.review_status == "needs_review"  # a genuinely new classification always starts fresh
    assert new_row.file_hash != old_row.file_hash  # the stale render was NOT reused


# --- 16. safe rendering-failure handling (Part 6/Part 17) ------------------

def test_render_page_returns_none_for_an_out_of_range_page(tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["only one page here"])
    assert render_page(str(pdf_path), 5, "testcouncil", 1) is None


def test_render_page_returns_none_and_leaves_no_partial_files_for_a_corrupt_pdf(tmp_path, monkeypatch):
    visuals_dir = tmp_path / "visuals"
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", visuals_dir)
    bad_path = tmp_path / "corrupt.pdf"
    bad_path.write_bytes(b"this is not a real pdf file")
    assert render_page(str(bad_path), 1, "testcouncil", 1) is None
    if visuals_dir.exists():
        assert list(visuals_dir.rglob("*.png")) == []


def test_render_page_refuses_an_oversized_source_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    monkeypatch.setattr(rendering_module, "MAX_RENDERABLE_FILE_SIZE", 10)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["some content that will exceed a 10-byte limit easily"])
    assert render_page(str(pdf_path), 1, "testcouncil", 1) is None


# --- 17. path-traversal prevention (Part 17) --------------------------------

def test_render_page_never_writes_outside_the_visuals_storage_directory(tmp_path, monkeypatch):
    visuals_dir = tmp_path / "visuals"
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", visuals_dir)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["some content"])
    result = render_page(str(pdf_path), 1, "../../evil", "../../../etc/passwd")
    if result is not None:
        assert str(visuals_dir.resolve()) in result["image_path"]
        assert ".." not in result["image_path"].replace(str(tmp_path.resolve()), "")


# --- 18. complete / partial / empty UI states (Part 11/Part 12) -------------

def test_site_visual_evidence_empty_state_when_nothing_extracted_yet(session):
    site = _make_site(session)
    assert build_site_visual_evidence(session, site.id) == {"primary": None, "others": []}


def test_site_visual_evidence_excludes_rejected_images_entirely(session):
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    document = _make_document(session, application.id, "/fake/path.pdf")
    rejected = VisualEvidence(document_id=document.id, site_id=site.id, source_page=1, image_type="unknown", review_status="rejected", status="current")
    session.add(rejected)
    session.commit()
    assert build_site_visual_evidence(session, site.id) == {"primary": None, "others": []}


def test_site_visual_evidence_partial_state_unreviewed_primary_no_others(session):
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    document = _make_document(session, application.id, "/fake/path.pdf")
    image = VisualEvidence(
        document_id=document.id, site_id=site.id, source_page=1, image_type="site_location_plan",
        review_status="needs_review", status="current", is_primary=True,
    )
    session.add(image)
    session.commit()
    result = build_site_visual_evidence(session, site.id)
    assert result["primary"].id == image.id
    assert result["others"] == []


def test_site_visual_evidence_complete_state_confirmed_primary_with_others(session):
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    document = _make_document(session, application.id, "/fake/path.pdf")
    primary = VisualEvidence(
        document_id=document.id, site_id=site.id, source_page=1, image_type="red_line_boundary",
        review_status="confirmed", status="current", is_primary=True,
    )
    other = VisualEvidence(
        document_id=document.id, site_id=site.id, source_page=2, image_type="masterplan",
        review_status="needs_review", status="current", is_primary=False,
    )
    session.add_all([primary, other])
    session.commit()
    result = build_site_visual_evidence(session, site.id)
    assert result["primary"].id == primary.id
    assert [o.id for o in result["others"]] == [other.id]


# --- 19. image/source provenance retained end-to-end (Part 13) -------------

def test_visual_evidence_row_retains_full_source_provenance(session, tmp_path, monkeypatch):
    monkeypatch.setattr(rendering_module, "VISUALS_DIR", tmp_path / "visuals")
    site = _make_site(session)
    application = _make_application(session, site_id=site.id)
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, ["a page showing the site boundary clearly marked"])
    document = _make_document(session, application.id, pdf_path, document_name="Site Location Plan.pdf")
    document.source_url = "https://portal.example.invalid/documents/doc123.pdf"
    session.commit()

    client = _FakeVisionClient(_classification_result())
    process_document(session, client, document, PipelineLimits(), PipelineStats())

    row = session.query(VisualEvidence).filter_by(document_id=document.id).one()
    assert row.source_document_title == "Site Location Plan.pdf"
    assert row.source_document_url == "https://portal.example.invalid/documents/doc123.pdf"
    assert row.source_page == 1
    assert row.extraction_method == "ai_vision"
    assert row.extraction_model == "gpt-4o-mini"
    assert row.extraction_prompt_version
    assert row.candidate_reason  # records WHY this page was a Stage-1 candidate
    assert row.file_hash
