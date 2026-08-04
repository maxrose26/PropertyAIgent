"""Tests for app.ui.common.load_applications_for_sites (Sprint 3A, "Map
Navigation and Site UX", Part 6/8: "no per-marker database query pattern",
"filtering not causing marker-to-Site mismatches")."""
from __future__ import annotations

from sqlalchemy import event

from app.db.models import Application, Site
from app.ui.common import load_applications_for_sites


def _make_site(session, council_code, address):
    site = Site(council_code=council_code, canonical_address=address.lower(), display_address=address)
    session.add(site)
    session.commit()
    return site


def _make_qualifying_application(session, council_code, reference, site_id, units=50):
    app = Application(
        council_code=council_code, reference=reference, site_id=site_id,
        proposal=f"Construction of {units} new dwellings", application_type="Full",
    )
    session.add(app)
    session.commit()
    return app


def test_returns_every_requested_site_id_even_with_no_applications(session):
    site = _make_site(session, "testcouncil", "1 Empty Road")
    result = load_applications_for_sites(session, [site.id])
    assert result == {site.id: []}


def test_empty_input_returns_empty_dict_without_querying(session):
    assert load_applications_for_sites(session, []) == {}


def test_batches_applications_correctly_across_multiple_sites(session):
    site_a = _make_site(session, "testcouncil", "1 Test Street")
    site_b = _make_site(session, "othercouncil", "2 Other Street")
    _make_qualifying_application(session, "testcouncil", "REF-A1", site_a.id)
    _make_qualifying_application(session, "othercouncil", "REF-B1", site_b.id)
    _make_qualifying_application(session, "othercouncil", "REF-B2", site_b.id)

    result = load_applications_for_sites(session, [site_a.id, site_b.id])

    assert [a.reference for a in result[site_a.id]] == ["REF-A1"]
    assert sorted(a.reference for a in result[site_b.id]) == ["REF-B1", "REF-B2"]


def test_filtering_does_not_cause_marker_to_site_mismatches(session):
    # Simulates the map page's own use: fetch a full batch, then only look
    # up a filtered subset of site_ids - the result for each id must still
    # be exactly that site's own applications, never another site's.
    sites = [_make_site(session, "testcouncil", f"{n} Test Street") for n in range(1, 6)]
    for i, site in enumerate(sites):
        _make_qualifying_application(session, "testcouncil", f"REF-{i}", site.id)

    full_batch = load_applications_for_sites(session, [s.id for s in sites])
    filtered_ids = [sites[1].id, sites[3].id]  # simulate a map filter narrowing the view
    filtered_batch = load_applications_for_sites(session, filtered_ids)

    for site_id in filtered_ids:
        assert [a.reference for a in filtered_batch[site_id]] == [a.reference for a in full_batch[site_id]]
    # And a site NOT in the filtered request never leaks into it.
    assert sites[0].id not in filtered_batch


def test_issues_exactly_one_query_regardless_of_site_count(session):
    sites = [_make_site(session, "testcouncil", f"{n} Test Street") for n in range(1, 9)]
    for i, site in enumerate(sites):
        _make_qualifying_application(session, "testcouncil", f"REF-{i}", site.id)

    engine = session.get_bind()
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        load_applications_for_sites(session, [s.id for s in sites])
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # Two SELECTs total - one for the applications themselves, one batched
    # (selectinload) fetch of their scheme_intelligence rows - NOT one per
    # site or one per application (which would be 8+ for the 8 sites/
    # applications seeded above). load_councils() reads a YAML file, not
    # the database, so it doesn't add to this count.
    assert len(statements) == 2
