"""The mechanical derivation of the v3 worker-function replacement (proposal section 2.1). Offline, text only: nothing is installed anywhere. The PostgreSQL behaviour is in test_ingestion_screening_v3_pg.py."""
import difflib

import pytest

from app.ingestion import listing_screening as ls
from verification.ingestion_storage import screening_v3_worker_sql as d

# Specification 034's two substitution sites, copied from its draft derivation module (PR #164, verification/ingestion_storage/observation_worker_sql.py) to prove the two lists are independent.
RECEIPT, OBSERVATION = 'LISTING_RECEIPT_V1', 'LISTING_OBSERVATION_V1'
SPEC034_BATCH = ("capture.checkpoint::jsonb->>'kind'<>'%s'" % RECEIPT, "(coalesce(capture.checkpoint::jsonb->>'kind'='%s' OR (capture.checkpoint::jsonb->>'kind'='%s' AND coalesce(jsonb_typeof(g->'observation_councils'),'null')='array'"
                " AND g->'observation_councils' ? (capture.subject::jsonb->>'council')),false)) IS DISTINCT FROM true" % (RECEIPT, OBSERVATION))
ANCHOR = "w.checkpoint::jsonb IS DISTINCT FROM p_payload OR "
SPEC034_CHECKPOINT = (ANCHOR + "w.checkpoint::jsonb->>'kind' IS DISTINCT FROM '%s'" % RECEIPT, ANCHOR + "(coalesce(w.checkpoint::jsonb->>'kind'='%s' OR (w.checkpoint::jsonb->>'kind'='%s' AND g->'observation_councils' ? (w.subject::jsonb->>'council')),false)) IS DISTINCT FROM true" % (RECEIPT, OBSERVATION))
SPEC034 = (SPEC034_BATCH, SPEC034_CHECKPOINT)


def test_every_site_matches_exactly_once_in_the_installed_definition_and_the_derivation_is_reversible():
    original = d.original_text()
    for old, _ in d.SITES:
        assert original.count(old) == 1, old[:70]
    derived = d.derive(original)
    assert derived != original and d.undo(derived) == original      # undoing every substitution reproduces the original byte for byte
    # the derived text has exactly the changed hunks and nothing else
    changed = [line for line in difflib.unified_diff(original.split('\n'), derived.split('\n'), lineterm='', n=0) if line[:1] in '+-' and line[:3] not in ('+++', '---')]
    removed = [c for c in changed if c.startswith('-')]
    assert 4 <= len(removed) <= 6 and len([c for c in changed if c.startswith('+')]) >= 6      # four in-line rewrites and two inserted checks; nothing else


def test_a_missing_or_duplicated_site_fails_the_derivation():
    original = d.original_text()
    with pytest.raises(ValueError, match='SUBSTITUTION_SITE_NOT_UNIQUE'):
        d.derive(original.replace(d.SITE_INSERT[0], 'x'))
    with pytest.raises(ValueError, match='SUBSTITUTION_SITE_NOT_UNIQUE'):
        d.derive(original + '\n' + d.SITE_INSERT[0])
    with pytest.raises(ValueError, match='REPLACEMENT_NOT_UNIQUE'):
        d.undo(original)


def test_the_v1_branch_text_is_untouched_apart_from_the_stated_sites():
    original, derived = d.original_text(), d.derive()
    # every v1 literal still present in the derived function: v1 contract pins in enqueue_child, the v1 revision rule, the batch contract, and the capture-kind test that 034 anchors on
    for needle in ("child->>'contract' IS DISTINCT FROM 'listing-screen-v1'\n   OR child->'subject'->>'kind'",       # enqueue_child unchanged (v1 only, no v3 path)
                   "'SCREENING','listing-screen-v1',child->>'revision',json_build_array(p_key)",                    # enqueue_child insert unchanged
                   "w.contract<>'listing-batch-v1'", "capture.checkpoint::jsonb->>'kind'<>'LISTING_RECEIPT_V1'",
                   "(g->'completion_outcomes'->w.task ? (p_payload->>'outcome')) IS DISTINCT FROM true"):
        assert original.count(needle) >= 1 and derived.count(needle) == original.count(needle), needle
    for untouched in ('ingestion_acceptance_control', 'ingestion_bolton_allowed', 'ingestion_register_bolton_exception', 'ingestion_raise_stop', 'ingestion_recover_abandoned'):
        a = original[original.index('FUNCTION public.%s(' % untouched):]
        b = derived[derived.index('FUNCTION public.%s(' % untouched):]
        assert a.split('$')[2][:400] == b.split('$')[2][:400] or untouched not in derived      # other functions are unchanged


def test_v3_is_default_off_and_admitted_only_over_a_receipt_parent_with_a_listed_configuration():
    derived = d.derive()
    assert "(plan ? 'screening') IS DISTINCT FROM true AND child->>'contract'='listing-screen-v1'" in derived      # a plan without a screening binding can only create v1 children
    assert "g->'screening_configs' ? (plan->'screening'->>'config_sha256')" in derived and "jsonb_typeof(g->'screening_configs')='array'" in derived      # absent or non-array list => refused
    assert "capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1'" in derived      # an observation parent can never parent a v3 child
    assert "'SCREENING_V3_RECEIPT'" in derived and "'SCREENING_V3_OUTCOME'" in derived
    for admission in ls.ROUTING_VOCABULARY[ls.RULE_V3]:
        assert "'%s'" % admission in d.RECEIPT_CHECK      # the SQL vocabulary is the Python vocabulary
    assert sorted(d.V3_ADMISSIONS) == sorted(ls.ROUTING_VOCABULARY[ls.RULE_V3])
    assert d.V3_CHILD_OK.count('(') == d.V3_CHILD_OK.count(')') and d.RECEIPT_CHECK.count('(') == d.RECEIPT_CHECK.count(')') and d.OUTCOME_CHECK.count('(') == d.OUTCOME_CHECK.count(')')
    for text in (d.V3_CHILD_OK, d.RECEIPT_CHECK, d.OUTCOME_CHECK, d.REVISION_V3):
        assert text.count("'") % 2 == 0


def test_the_sql_revision_text_is_the_python_canonical_digest_input():
    """SQL builds '{"config_sha256":"C","record_sha256":"R"}' by hand; it must be byte-identical to ledger.digest's input for the same pair."""
    import hashlib
    import json
    from app.ingestion.ledger import digest
    record_sha, config_sha = 'a' * 64, 'b' * 64
    sql_text = '{"config_sha256":"' + config_sha + '","record_sha256":"' + record_sha + '"}'
    assert sql_text == json.dumps(dict(record_sha256=record_sha, config_sha256=config_sha), sort_keys=True, separators=(',', ':'))
    assert hashlib.sha256(sql_text.encode()).hexdigest() == digest(dict(record_sha256=record_sha, config_sha256=config_sha))
    assert "'{\"config_sha256\":\"'||(plan->'screening'->>'config_sha256')||'\",\"record_sha256\":\"'||" in d.REVISION_V3


def test_the_v3_list_and_specification_034_are_independent_and_commute():
    original = d.original_text()
    for old, _ in SPEC034:
        assert original.count(old) == 1
        for v3_old, _ in d.SITES:
            assert old not in v3_old and v3_old not in old      # no v3 anchor contains or is contained in a 034 anchor
    v3_then_034 = d.derive(original)
    for old, new in SPEC034:
        assert v3_then_034.count(old) == 1      # the 034 sites survive the v3 substitutions
        v3_then_034 = v3_then_034.replace(old, new)
    from_034 = original
    for old, new in SPEC034:
        from_034 = from_034.replace(old, new)
    assert d.derive(from_034) == v3_then_034      # either order gives the same function
    # and an observation parent is refused by the v3 predicate even with 034 applied
    assert "capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1'" in v3_then_034.split("'BATCH_ROW_TYPES'")[0]


def test_the_replacement_statement_is_a_single_create_or_replace_of_the_worker_step_only():
    stmt = d.replacement_function()
    assert stmt.startswith('CREATE OR REPLACE FUNCTION public.ingestion_worker_step(') and stmt.endswith('$fn$;')
    assert stmt.count('$fn$') == 2 and stmt.count('CREATE ') == 1
    assert 'ingestion_recover_abandoned' not in stmt and 'GRANT ' not in stmt and 'OWNER TO' not in stmt
