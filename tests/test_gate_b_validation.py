"""Stage 2.5B Gate B (specification 026): the read-only production discovery validation runner, proven OFFLINE on synthetic SQLite data only.

Covers: read-only enforcement, blocked writes, no network/model, deterministic artifact, mandate-sourced scale, phase-subject vs qualified-phasing distinction, honest legacy comparison,
no unit summation / residual / availability inference, Housing Association not inheriting total-site phasing, no credential values, real-mode route refusal, instrumentation.
"""
from __future__ import annotations

import copy
import json
import re
import socket
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import verification.gate_b.runner as runner
import verification.gate_b.safety as safety
from app.db.models import Application, Site
from app.policy.buyer_matching import discovery_bounds
from app.policy.buyer_profiles import BUYER_PROFILES
from benchmark.v7.runner import FORBIDDEN_INFERENCES
from tests.test_buyer_family_feed import LAPSE_AGE, World
from tests.test_family_dashboard import treat_portal_estimates_as_exact

FIXED = lambda: __import__("datetime").datetime(2026, 10, 7, 12, 0, tzinfo=__import__("datetime").timezone.utc)   # noqa: E731


@pytest.fixture
def world(session, monkeypatch):
    treat_portal_estimates_as_exact(monkeypatch)                  # the fixtures carry unbounded portal estimates; the REAL relevance rule is exercised on exact counts
    return World(session, monkeypatch)


def seed(world):
    big = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500, units_rm=140)          # oversized parent + buyer-sized CURRENT phase
    plain = world.site(outline_age=LAPSE_AGE, parent="S", units_out=120)                                                   # in-range ordinary site
    address_only = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500)
    rm = world.session.query(Application).filter(Application.site_id == address_only.id, Application.reference.like("RM/%")).one()
    rm.proposal, rm.address = "Reserved matters for 30 dwellings", "Phase 2, Mill Lane, Anytown"                            # phase label in the ADDRESS only: a phase subject, no qualified evidence
    world.session.commit()
    return big, plain, address_only


def run(session, **kw):
    return runner.run_validation(session, real=False, code_sha="test-sha", clock=FIXED, **kw)


def without_measurements(artifact):
    clone = copy.deepcopy(artifact)
    clone["efficiency"].pop("runtime_seconds", None)
    for stage in clone["efficiency"]["stages"]:
        stage.pop("seconds", None)
    return clone


# --- 1-3. read-only, blocked writes, no model/network ----------------------------------------------------------------------------------------

def test_the_run_issues_only_read_statements_stages_nothing_and_never_commits(world):
    seed(world)
    statements = []
    from sqlalchemy import event
    engine = world.session.get_bind()
    listener = lambda conn, cursor, statement, *a: statements.append(statement)              # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        before = (world.session.query(Site).count(), world.session.query(Application).count())
        artifact = run(world.session)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert statements and all(safety.is_allowed_statement(s) or s.lstrip().upper().startswith("PRAGMA") for s in statements)
    assert not (world.session.new or world.session.dirty or world.session.deleted)
    assert (world.session.query(Site).count(), world.session.query(Application).count()) == before
    assert artifact["run_metadata"]["production_read_safety"]["committed"] is False


def test_every_kind_of_write_inside_the_window_is_blocked(world):
    seed(world)
    with safety.read_only_window(world.session, real=False) as (instrument, status):
        with pytest.raises(safety.ReadOnlyViolation):
            world.session.execute(text("DELETE FROM sites"))
        with pytest.raises(safety.ReadOnlyViolation):
            world.session.execute(text("UPDATE sites SET council_code = 'x'"))
        with pytest.raises(safety.ReadOnlyViolation):
            world.session.execute(text("INSERT INTO sites (council_code) VALUES ('x')"))
        world.session.add(Site(council_code="x", canonical_address="staged", display_address="staged"))
        with pytest.raises(safety.ReadOnlyViolation):
            world.session.flush()                                                            # a staged ORM mutation can never reach the database
        world.session.rollback()
        with pytest.raises(safety.ReadOnlyViolation):
            world.session.commit()
    assert world.session.query(Site).filter(Site.canonical_address == "staged").count() == 0


def test_the_statement_allow_list_is_exact():
    for ok in ("SELECT 1", "  select * from sites", "WITH x AS (SELECT 1) SELECT * FROM x", "SHOW transaction_read_only", "SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = 60000",
               "-- c\nSELECT 1"):
        assert safety.is_allowed_statement(ok), ok
    for bad in ("INSERT INTO t VALUES (1)", "UPDATE t SET a=1", "DELETE FROM t", "COMMIT", "SET ROLE x", "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE", "SET LOCAL lock_timeout = 1",
                "CREATE TABLE t (a int)", "DROP TABLE t", "TRUNCATE t", "GRANT ALL ON t TO x", "ALTER TABLE t ADD c int", "COPY t FROM STDIN", "CALL p()",
                "SELECT 1; DELETE FROM t", "SELECT 1; COMMIT; BEGIN; DELETE FROM t", "SHOW x; COMMIT", "SET LOCAL statement_timeout=1; SET SESSION AUTHORIZATION x",
                "/* /* */ SELECT 1 */ DELETE FROM t", "SELECT 1 /* x */", "SELECTX 1", "WITHDRAW 5", "SHOWDOWN", "-- c\nDELETE FROM t", ""):
        assert not safety.is_allowed_statement(bad), bad
    assert safety.is_allowed_statement("SELECT 1;") and safety.is_allowed_statement("SELECT 1 ;")          # one trailing semicolon is harmless


def test_every_new_postgres_transaction_is_made_read_only_first():
    executed = []
    connection = SimpleNamespace(execute=lambda statement: executed.append(str(statement)))
    safety.assert_read_only(connection, 45000)
    assert executed == ["SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = 45000"]
    assert all(safety.is_allowed_statement(s) for s in executed)
    source = open(safety.__file__, encoding="utf-8").read()
    assert 'event.listen(session, "after_begin", after_begin)' in source and "assert_read_only(connection, statement_timeout_ms)" in source   # re-asserted after any rollback


def test_the_guards_are_restored_even_when_the_window_raises(world):
    seed(world)
    originals = (socket.socket.connect, socket.create_connection, __import__("builtins").__import__)
    with pytest.raises(RuntimeError, match="boom"):
        with safety.read_only_window(world.session, real=False):
            raise RuntimeError("boom")
    assert (socket.socket.connect, socket.create_connection, __import__("builtins").__import__) == originals
    world.session.add(Site(council_code="x", canonical_address="after", display_address="after"))
    world.session.commit()                                                                  # outside the window normal behaviour is back (the window left no listener behind)
    assert world.session.query(Site).filter(Site.canonical_address == "after").count() == 1


def test_no_network_and_no_model_client_can_be_used_inside_the_window(world, monkeypatch):
    seed(world)
    with safety.read_only_window(world.session, real=False):
        with pytest.raises(safety.ReadOnlyViolation):
            socket.create_connection(("203.0.113.9", 443), timeout=1)
        with pytest.raises(safety.ReadOnlyViolation):
            socket.socket.connect(None, ("203.0.113.9", 443))        # the guard refuses before any socket is used (the offline sandbox forbids creating one)
        monkeypatch.delitem(sys.modules, "openai", raising=False)
        with pytest.raises(safety.ReadOnlyViolation):
            __import__("openai")
    source = open(runner.__file__, encoding="utf-8").read() + open(safety.__file__, encoding="utf-8").read()
    assert "OpenAI(" not in source and "requests." not in source and "urlopen" not in source
    assert not {"evaluate_frozen_input", "run_persisted_evaluation", "acquisition_evaluate"} & set(re.findall(r"\w+", source.replace("evaluate_frozen_input_not", "")))


def test_the_network_guard_permits_only_the_database_host():
    with safety.network_guard(allowed_hosts=("db.internal",)):
        with pytest.raises(safety.ReadOnlyViolation):
            socket.create_connection(("203.0.113.9", 443), timeout=1)
        # an allowed host is not refused by the GUARD (the connection itself then fails or succeeds on its own merits)
        try:
            socket.create_connection(("db.internal", 1), timeout=0.2)
        except safety.ReadOnlyViolation:
            raise
        except OSError:
            pass


# --- 4. determinism ------------------------------------------------------------------------------------------------------------------------------

def test_the_artifact_is_deterministic_for_identical_input_and_clock(world):
    seed(world)
    a, b = run(world.session), run(world.session)
    assert runner.artifact_json(without_measurements(a)) == runner.artifact_json(without_measurements(b))
    assert runner.shortlist_csv(a) == runner.shortlist_csv(b)
    assert a["run_metadata"]["timestamp_utc"] == "2026-10-07T12:00:00+00:00"


# --- 5. mandate semantics from the accepted policy -----------------------------------------------------------------------------------------

def test_scale_bounds_come_from_the_mandate_never_from_the_runner(world):
    seed(world)
    artifact = run(world.session)
    mandate = artifact["buyers"]["nesten_homes"]["mandate"]
    profile = BUYER_PROFILES["nesten_homes"]
    assert (mandate["preferred_min"], mandate["preferred_max"]) == (profile.target_unit_min, profile.target_unit_max) == (50, 200)
    assert (mandate["discovery_min"], mandate["discovery_max"]) == discovery_bounds(50, 200) == (45, 220)
    assert artifact["buyers"]["housing_association"]["mandate"]["scale_metric"] == "affordable_units"
    code = re.sub(r'""".*?"""', "", open(runner.__file__, encoding="utf-8").read(), flags=re.S)
    assert not re.search(r"\b(45|220|50|200|nesten_homes\s*==|housing_association\s*==)\b", code.replace("PRIMARY_BUYER = \"nesten_homes\"", ""))     # no hard-coded Nesten numbers or buyer-name branches
    assert 'buyer == "' not in code and "AFFORDABLE_UNITS" in code                                                              # the affordable-unit distinction follows the mandate's scale metric
    assert len(mandate["digest"]) == 16


# --- 6. phase subject vs qualified phasing evidence ----------------------------------------------------------------------------------------

def test_a_phase_subject_is_distinct_from_qualified_current_phasing_evidence(world):
    big, plain, address_only = seed(world)
    population = run(world.session)["aggregates"]["phasing_population"]
    assert population["planning_delivery_families_assessed"] == 3
    assert population["families_with_any_phase_subject"] == 2                                  # the genuine phase AND the address-only phase label
    assert population["qualified_phasing_state"]["CURRENT_EVIDENCED_PHASE"] == 1                # only the genuine one is qualified evidence
    assert population["phase_subject_without_qualified_phasing_evidence"] == 1                  # address-only: a phase subject without qualified evidence
    assert population["qualified_phasing_state"]["NONE_IDENTIFIED"] == 2


# --- Nesten report, review families, negative cohort ---------------------------------------------------------------------------------------

def test_nesten_review_family_lists_the_oversized_wider_development_with_its_buyer_sized_current_phase(world):
    big, plain, address_only = seed(world)
    nesten = run(world.session)["nesten"]
    review = nesten["oversized_wider_with_buyer_sized_current_phase"]
    assert [r["site_id"] for r in review] == [big.id]
    family = review[0]
    assert family["qualified_phasing_state"] == "CURRENT_EVIDENCED_PHASE" and family["oversized_wider"] and family["phasing_badge"] == "Phased delivery evidenced."
    assert family["family_fit"] == "STRONG_FIT" and "phase" in family["representative"]
    assert family["overlap"] == "MAY_OVERLAP_DO_NOT_ADD" and family["council_code"] == "testcouncil" and family["title"] == f"Site {big.id}"
    by_label = {s["label"]: s for s in family["subjects"]}
    named = next(s for s in family["subjects"] if s["named_phase"])
    assert named["fit"] == "STRONG_FIT" and by_label["Wider permission"]["named_phase"] is False and by_label["Permission approaching its assumed review date"]["fit"] == "INSUFFICIENT_EVIDENCE"
    assert named["count"]["display"] and by_label["Wider permission"]["count"]["display"] and named["reasons"]
    population = nesten["population"]
    assert population["oversized_wider_with_buyer_sized_current_phase"] == 1 and population["oversized_wider_families"] == 2
    assert population["oversized_wider_by_qualified_phasing_state"]["CURRENT_EVIDENCED_PHASE"] == 1 and population["oversized_wider_by_qualified_phasing_state"]["NONE_IDENTIFIED"] == 1
    assert population["fit"]["STRONG_FIT"] == 3 and population["families_evaluated"] == 3


def test_the_negative_cohort_records_evidence_gaps_without_reading_documents(world):
    big, plain, address_only = seed(world)
    cohort = run(world.session)["negative_cohort"]
    assert cohort["phase_subject_without_qualified_phasing_evidence"]["total"] == 1
    assert cohort["phase_subject_without_qualified_phasing_evidence"]["sample"][0]["title"] == f"Site {address_only.id}"
    assert set(cohort) == {"oversized_wider_without_qualified_phasing", "phase_subject_without_qualified_phasing_evidence", "currentness_unknown_phasing",
                           "phase_subject_without_exact_count", "no_buyer_relevant_acquisition_scope"}
    assert all(group["sample_limit"] == 25 and len(group["sample"]) <= 25 for group in cohort.values())


# --- 7. honest old/new comparison ------------------------------------------------------------------------------------------------------------

def test_comparison_categories_follow_the_written_definitions():
    from app.reporting.opportunity_families import FamilySubject, OpportunityFamily, RelatedSubject, ID_SYSTEM_FEED

    def subject(key, slot, fit, inv=False):
        return FamilySubject(domain="planning_delivery", anchor_id=1, subject_key=key, slot=slot, fit=fit, investigative=inv, id_system=ID_SYSTEM_FEED)
    rep, parent = subject("opp-phase-1-2", "PHASE", "STRONG_FIT"), subject("opp-lapse-1", "LIFECYCLE", "INSUFFICIENT_EVIDENCE", True)
    family = OpportunityFamily(("planning_delivery", 1), rep, (RelatedSubject(parent, "INSUFFICIENT_INVESTIGATIVE"),))
    legacy = lambda subjects, rank: {"index": {("planning_delivery", 1): {"subjects": subjects, "best_rank": rank}} if subjects else {}}   # noqa: E731
    assert runner.compare_with_legacy(family, True, legacy([], None))["comparison"] == runner.NEWLY_SURFACED
    assert runner.compare_with_legacy(family, True, legacy(["opp-lapse-1"], 2))["comparison"] == runner.BETTER_REPRESENTED        # strictly better representative
    assert runner.compare_with_legacy(family, True, legacy(["opp-lapse-1", "opp-phase-1-2"], 0))["comparison"] == runner.DEDUPLICATED      # several cards collapse: no better discovery claimed
    assert runner.compare_with_legacy(family, True, legacy(["opp-lapse-1", "opp-lapse-9"], 2))["comparison"] == runner.BETTER_REPRESENTED   # collapse AND a strictly better representative
    assert runner.compare_with_legacy(family, True, legacy(["opp-phase-1-2"], 0))["comparison"] == runner.COMPARABLE              # same representative: regrouping alone is never "new"
    assert runner.compare_with_legacy(family, False, legacy([], None))["comparison"] == runner.OUTSIDE_NEW_WINDOW
    assert runner.compare_with_legacy(family, True, None)["comparison"] is None                                                   # no comparator: no claim


def test_end_to_end_comparison_never_calls_a_regrouped_site_newly_surfaced(world):
    seed(world)
    artifact = run(world.session)
    counts = artifact["aggregates"]["comparison_counts_in_new_window"]
    legacy = artifact["nesten"]["legacy_window"]
    assert legacy["window"] == 20 and sum(counts.values()) == len(artifact["nesten"]["shortlist"])
    for row in artifact["nesten"]["shortlist"]:
        if row["legacy_cards_for_family"]:
            assert row["comparison"] in (runner.BETTER_REPRESENTED, runner.DEDUPLICATED, runner.COMPARABLE)         # the legacy window already held the site
        else:
            assert row["comparison"] == runner.NEWLY_SURFACED
    assert "not re-derived" in artifact["definitions"]["legacy_limits"] and "not re-derived" in artifact["aggregates"]["comparison_caveat"] and "non-commercial" in artifact["aggregates"]["comparison_caveat"]


# --- 8-10. no summation / residual / availability ----------------------------------------------------------------------------------------

def test_no_unit_summation_residual_or_availability_claim_anywhere_in_the_data_sections(world):
    seed(world)
    artifact = run(world.session)
    data = json.dumps({k: artifact[k] for k in ("aggregates", "buyers", "nesten", "negative_cohort")}, default=str)
    assert not re.search(r'"(summed|sum|combined|residual|remaining|total_(units|homes|dwellings))[a-z_]*":', data)
    for number in ("640", "360", "620", "380"):                                                # 500+140, 500-140, 500+120, 500-120
        assert f'"{number}' not in data and f"{number} homes" not in data
    for name, pattern in FORBIDDEN_INFERENCES.items():
        assert not re.search(pattern, data, re.I), name
    assert "availab" not in " ".join(artifact["nesten"]["shortlist"][0]["subjects"][0]["reasons"]["matches"]).lower()
    for family in artifact["nesten"]["shortlist"]:
        assert family["overlap"] in ("MAY_OVERLAP_DO_NOT_ADD", "SINGLE_SUBJECT")


# --- 11. Housing Association --------------------------------------------------------------------------------------------------------------------

def test_housing_association_does_not_inherit_total_site_phasing(world):
    seed(world)
    artifact = run(world.session)
    ha = artifact["buyers"]["housing_association"]
    assert "total_site_phasing_is_not_affordable_package_evidence" in ha and "total_site_phasing_is_not_affordable_package_evidence" not in artifact["buyers"]["nesten_homes"]
    assert ha["total_site_phasing_is_not_affordable_package_evidence"] == {"families_with_current_qualified_phasing": 1, "families_showing_phasing_badge": 0, "required_badge_count": 0, "holds": True}
    assert ha["population"]["oversized_wider_families"] == 0 and ha["population"]["oversized_wider_with_buyer_sized_current_phase"] == 0
    assert artifact["buyers"]["nesten_homes"]["population"]["families_showing_phasing_badge"] == 1      # the same evidence IS relevant for the total-units buyer
    for buyer in ("national_housebuilder", "strategic_land_buyer"):
        assert "population" in artifact["buyers"][buyer] and artifact["buyers"][buyer]["population"]["families_evaluated"] == 3


# --- 12. no credentials -----------------------------------------------------------------------------------------------------------------------------

def test_the_artifact_contains_no_credential_or_connection_values(world, monkeypatch):
    seed(world)
    monkeypatch.setenv("DATABASE_URL", "postgresql://svc_user:SUPERSECRETPASS@db.supabase.example:5432/postgres")
    artifact = run(world.session)
    blob = runner.artifact_json(artifact) + runner.shortlist_csv(artifact)
    for forbidden in ("SUPERSECRETPASS", "svc_user", "supabase.example", "postgresql://", "postgres://", "DATABASE_URL", "://", "password", "secret", "token"):
        assert forbidden.lower() not in blob.lower(), forbidden


# --- 13-14. real mode ---------------------------------------------------------------------------------------------------------------------------

def test_real_mode_refuses_a_non_postgres_route_and_needs_the_application_route(world, monkeypatch):
    seed(world)
    with pytest.raises(safety.RealModeRefused, match="PostgreSQL"):
        runner.run_validation(world.session, real=True, code_sha="x", clock=FIXED)
    for dialect, url, same_engine, expected in (("postgresql", None, True, "DATABASE_URL"), ("postgresql", "postgresql://u:p@h/d", False, "own engine")):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        if url:
            monkeypatch.setenv("DATABASE_URL", url)
        import app.db.session as app_session
        engine = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        monkeypatch.setattr(app_session, "get_engine", lambda engine=engine: engine if same_engine else object())
        stub = SimpleNamespace(get_bind=lambda engine=engine: engine, in_transaction=lambda: False)
        with pytest.raises(safety.RealModeRefused, match=expected):
            safety.check_route(stub, real=True)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr("app.db.session.get_engine", lambda: engine)
    assert safety.check_route(SimpleNamespace(get_bind=lambda: engine, in_transaction=lambda: False), real=True) == "postgresql"
    with pytest.raises(safety.RealModeRefused, match="fresh session"):
        with safety.read_only_window(SimpleNamespace(get_bind=lambda: engine, in_transaction=lambda: True), real=True):
            pass


def test_synthetic_mode_refuses_a_postgres_route(monkeypatch):
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    with pytest.raises(safety.RealModeRefused, match="synthetic"):
        safety.check_route(SimpleNamespace(get_bind=lambda: engine, in_transaction=lambda: False), real=False)


def test_the_cli_refuses_real_mode_without_the_exact_confirmation_phrase():
    import scripts.validate_v7_discovery as cli
    assert cli.CONFIRM_PHRASE == "RUN READ-ONLY V7 DISCOVERY VALIDATION"
    args = cli.parse_args(["--out-dir", "x"])
    assert args.mode == "synthetic" and args.confirm == ""
    source = open(cli.__file__, encoding="utf-8").read()
    assert "@authorised_cli('validate_v7_discovery')" in source and 'open(target, "x"' in source                       # explicit operator scope; never overwrites an artifact
    manifest = json.load(open("verification/stage1_cli_manifest.json", encoding="utf-8"))
    assert manifest["scripts/validate_v7_discovery.py"] == {"command": "validate_v7_discovery", "required_scope": "launch:validate_v7_discovery"}


# --- 15. instrumentation --------------------------------------------------------------------------------------------------------------------------

def test_query_and_entity_instrumentation_reports_costs(world):
    seed(world)
    efficiency = run(world.session)["efficiency"]
    assert efficiency["query_count"] > 0 and efficiency["runtime_seconds"] >= 0
    assert efficiency["entities_read_by_category"].get("Application", 0) > 0 and efficiency["entities_read_by_category"].get("Site", 0) > 0
    assert efficiency["entities_read_total"] == sum(efficiency["entities_read_by_category"].values())
    stages = efficiency["stages"]
    assert [s["stage"] for s in stages][:2] == ["load_subject_inputs", "evaluate:nesten_homes"] and "legacy_feed_window" in [s["stage"] for s in stages]
    assert sum(s["queries"] for s in stages) <= efficiency["query_count"] and sum(s["queries"] for s in stages) > 0
    assert efficiency["statement_kinds"].get("SELECT", 0) > 0


def test_the_one_read_principle_extra_buyers_cost_a_constant_not_a_per_site_read(world):
    """With the legacy comparator off, three more buyers must add a number of queries that does NOT grow with the number of sites (inputs and B2 site contexts are read once)."""
    def extra_for_three_buyers():
        one = run(world.session, buyers=("nesten_homes",), include_legacy=False)["efficiency"]["query_count"]
        four = run(world.session, include_legacy=False)["efficiency"]["query_count"]
        return four - one
    seed(world)
    small = extra_for_three_buyers()
    for _ in range(6):
        world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500, units_rm=140)
    large = extra_for_three_buyers()
    assert small == large and small <= 30, (small, large)


def test_the_circuit_breaker_aborts_a_runaway_read(world):
    seed(world)
    with pytest.raises(safety.QueryBudgetExceeded):
        run(world.session, max_queries=3)
    assert not (world.session.new or world.session.dirty)


def test_the_feed_refactor_keeps_the_original_result_shape(world):
    seed(world)
    import app.reporting.buyer_family_feed as bff
    result = bff.build_buyer_opportunity_families(world.session, "nesten_homes", 6)
    assert set(result) == {"families", "excluded_family_keys", "counts", "buyer_key"}
    inputs = bff.load_buyer_family_inputs(world.session)
    first = bff.evaluate_buyer_families(world.session, "nesten_homes", inputs, 6)
    second = bff.evaluate_buyer_families(world.session, "housing_association", inputs, 6)
    assert [f.family_key for f in first["families"]] == [f.family_key for f in result["families"]]
    assert all("buyer_fit" not in card for card in inputs.delivery)                      # shared inputs are never mutated by an evaluation
    assert second["buyer_key"] == "housing_association"
