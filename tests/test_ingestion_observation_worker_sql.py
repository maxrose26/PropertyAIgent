"""Specification 034 section 3 and 8 (acceptance tests 1 and 2/3 at the two modified checks): the proposed observation admission is derived mechanically, explicitly boolean and default-deny.
Offline tests need no database. The PostgreSQL tests run the EXACT text of the two replaced predicates (extracted from the derived SQL) in a disposable PG17 and cover a NULL, missing, wrong and valid kind
with observation enablement present, absent and malformed, at BOTH checks. Nothing is installed or executed against any real ledger."""
import difflib
import itertools
import json
import os
import re

import pytest

from verification.ingestion_storage import observation_worker_sql as ow

ORIGINAL=ow.ORIGINAL.read_text(encoding="utf-8")
DERIVED=ow.derive()


def test_the_derivation_is_exactly_two_substitutions_and_nothing_else_changes():
    assert ow.derive()==DERIVED and DERIVED!=ORIGINAL
    changed=[l for l in difflib.unified_diff(ORIGINAL.splitlines(),DERIVED.splitlines(),lineterm="",n=0) if l[:1] in "+-" and l[:3] not in ("+++","---")]
    assert len(changed)==4      # two lines removed, two added
    removed=[l for l in changed if l[0]=="-"];added=[l for l in changed if l[0]=="+"]
    assert len(removed)==2 and len(added)==2
    # undoing the two substitutions reproduces the installed definition byte for byte
    back=DERIVED
    for old,new in (ow.SITE_BATCH,ow.SITE_CHECKPOINT):
        assert back.count(new)==1;back=back.replace(new,old)
    assert back==ORIGINAL


def test_the_derivation_refuses_a_source_where_a_substitution_site_is_not_unique_or_absent():
    for bad in (ORIGINAL.replace(ow.SITE_BATCH[0],"x"),ORIGINAL+ow.SITE_CHECKPOINT[0]):
        with pytest.raises(ValueError,match="SUBSTITUTION_SITE_NOT_UNIQUE"):ow.derive(bad)


def test_the_predicate_is_explicitly_boolean_and_default_deny_by_construction():
    for kind,subject in (("capture.checkpoint::jsonb->>'kind'","capture.subject::jsonb->>'council'"),("w.checkpoint::jsonb->>'kind'","w.subject::jsonb->>'council'")):
        guard=ow.reject_unless_admitted(kind,subject)
        assert guard in DERIVED and guard.startswith("(coalesce(") and guard.endswith(",false)) IS DISTINCT FROM true")      # every NULL removed, then rejected unless TRUE
        assert " NOT (" not in guard and "<>" not in guard      # no three-valued negation survives


def test_each_predicate_is_present_in_the_derived_function_at_its_own_site():
    batch,checkpoint=predicates().values()
    assert DERIVED.count(batch)==1 and DERIVED.count(checkpoint)==1 and ow.ANCHOR+checkpoint in DERIVED


def test_the_other_checks_in_the_function_are_untouched():
    assert DERIVED.count("LISTING_RECEIPT_V1")==ORIGINAL.count("LISTING_RECEIPT_V1")      # each site still names the receipt kind exactly once; op enqueue_child is the unchanged third
    assert "LISTING_OBSERVATION_V1" not in ORIGINAL and DERIVED.count("LISTING_OBSERVATION_V1")==2      # the observation kind appears only in the two modified predicates
    assert DERIVED.count("public.ingestion_bolton_allowed")==ORIGINAL.count("public.ingestion_bolton_allowed")


KINDS=[None,"LISTING_RECEIPT_V1","LISTING_OBSERVATION_V1","LISTING_OBSERVATION_V2","","listing_observation_v1"]
ENABLEMENTS=[("absent",{}),("empty",{"observation_councils":[]}),("listed",{"observation_councils":["bolton"]}),("other council",{"observation_councils":["oldham"]}),
             ("wrong type string",{"observation_councils":"bolton"}),("wrong type object",{"observation_councils":{"bolton":True}}),("null",{"observation_councils":None})]
COUNCILS=["bolton",None]


def expected_admitted(kind,grant,council):
    """Independent restatement of the rule (not derived from the SQL): a receipt is always admitted; an observation only for a council listed in an array enablement; everything else is rejected."""
    if kind=="LISTING_RECEIPT_V1":return True
    if kind=="LISTING_OBSERVATION_V1":
        e=grant.get("observation_councils");return isinstance(e,list) and council is not None and council in e
    return False


def predicates():
    """The two replaced predicates, as text (the checkpoint site's anchor to its own line is not part of the predicate)."""
    return {"batch_row/batch_reseal capture binding":ow.reject_unless_admitted("capture.checkpoint::jsonb->>'kind'","capture.subject::jsonb->>'council'"),
            "op checkpoint":ow.reject_unless_admitted("w.checkpoint::jsonb->>'kind'","w.subject::jsonb->>'council'")}


def connection():
    raw=os.environ.get("INGESTION_PROVISIONING_TEST_URL")
    if not raw:
        if os.environ.get("INGESTION_REQUIRE_LOCAL_PG"):pytest.fail("disposable PostgreSQL required")
        pytest.skip("disposable PostgreSQL required")
    import psycopg
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info.get("host"),info.get("dbname"))==("127.0.0.1","ingestion_provisioning_test")      # disposable fixture only
    return psycopg.connect(raw,autocommit=True,connect_timeout=3)


def evaluate(conn,predicate,alias,kind,grant,council):
    """Run the replaced predicate as the function does: g, and an aliased row with json checkpoint/subject columns."""
    checkpoint=json.dumps({"kind":kind}) if kind is not None else json.dumps({"other":1})      # None = the key is absent
    q="SELECT %s FROM (SELECT %%s::jsonb AS g) q, (SELECT %%s::json AS checkpoint, %%s::json AS subject) %s"%(predicate,alias)
    return conn.execute(q,(json.dumps(grant),checkpoint,json.dumps({"council":council}) if council is not None else json.dumps({}))).fetchone()[0]


@pytest.mark.parametrize("site",["batch_row/batch_reseal capture binding","op checkpoint"])
def test_postgres_the_replaced_predicate_rejects_unless_it_is_true_for_every_kind_enablement_and_council(site):
    predicate=predicates()[site];alias="capture" if site.startswith("batch") else "w"
    with connection() as conn:
        for kind,(label,grant),council in itertools.product(KINDS,ENABLEMENTS,COUNCILS):
            rejected=evaluate(conn,predicate,alias,kind,grant,council)
            assert rejected in (True,False),(site,kind,label,council,rejected)      # never NULL: a NULL would let the OR chain fall through and ADMIT
            assert rejected is (not expected_admitted(kind,grant,council)),(site,kind,label,council,rejected)


@pytest.mark.parametrize("site",["batch_row/batch_reseal capture binding","op checkpoint"])
def test_postgres_a_null_or_missing_kind_is_rejected_with_observation_enablement_both_present_and_absent(site):
    predicate=predicates()[site];alias="capture" if site.startswith("batch") else "w"
    with connection() as conn:
        for grant in ({},{"observation_councils":["bolton"]}):
            for checkpoint in ('{"kind":null}','{}'):      # SQL NULL from JSON null, and from an absent key
                q="SELECT %s FROM (SELECT %%s::jsonb AS g) q, (SELECT %%s::json AS checkpoint, '{\"council\":\"bolton\"}'::json AS subject) %s"%(predicate,alias)
                assert conn.execute(q,(json.dumps(grant),checkpoint)).fetchone()[0] is True,(site,grant,checkpoint)


def test_postgres_the_receipt_flow_is_unchanged_at_both_checks_without_any_enablement():
    with connection() as conn:
        for site,alias in (("batch_row/batch_reseal capture binding","capture"),("op checkpoint","w")):
            assert evaluate(conn,predicates()[site],alias,"LISTING_RECEIPT_V1",{},None) is False      # admitted: not rejected


def test_postgres_the_derived_function_is_valid_plpgsql_and_the_original_is_too():
    """Both definitions are parsed by PostgreSQL itself in a rolled-back transaction (body syntax only; no table, role or ledger row is needed or touched)."""
    match=lambda text:re.search(r"CREATE FUNCTION public\.ingestion_worker_step\(.*?\$fn\$;",text,re.S).group(0)
    for text in (ORIGINAL,DERIVED):
        with connection() as conn:
            conn.autocommit=False
            try:
                conn.execute("SET LOCAL check_function_bodies=on")
                conn.execute("CREATE SCHEMA obs_worker_syntax_check");conn.execute("SET LOCAL search_path=obs_worker_syntax_check,pg_catalog")
                for table in ("ingestion_work_items","ingestion_work_attempts"):conn.execute("CREATE TABLE obs_worker_syntax_check.%s(x integer)"%table)      # stubs inside the rolled-back scratch schema, so the body can be compiled
                conn.execute(match(text).replace("public.","obs_worker_syntax_check."))
            finally:conn.rollback()


def test_postgres_negative_control_the_first_draft_expression_admitted_a_null_kind_when_enabled_and_is_therefore_not_used():
    """Evidence for the defect that the explicit-boolean form fixes: IS DISTINCT FROM ... AND NOT (kind='O' AND enabled) is NULL (not TRUE) for a NULL kind with the council enabled,
    so inside the function's OR chain nothing raised and the checkpoint was ADMITTED."""
    draft=("((w.checkpoint::jsonb->>'kind') IS DISTINCT FROM 'LISTING_RECEIPT_V1' AND NOT ((w.checkpoint::jsonb->>'kind')='LISTING_OBSERVATION_V1' AND coalesce(g->'observation_councils','[]'::jsonb) ? (w.subject::jsonb->>'council')))")
    with connection() as conn:
        q="SELECT %s FROM (SELECT '{\"observation_councils\":[\"bolton\"]}'::jsonb AS g) q, (SELECT '{}'::json AS checkpoint, '{\"council\":\"bolton\"}'::json AS subject) w"%draft
        assert conn.execute(q).fetchone()[0] is None      # NULL: not a rejection
        assert evaluate(conn,predicates()["op checkpoint"],"w",None,{"observation_councils":["bolton"]},"bolton") is True      # the replacement rejects it


def test_current_v3_reconciliation_is_reversible_and_single_function_only():
    from verification.ingestion_storage import screening_v3_worker_sql as v3
    current=v3.derive();combined=ow.combined()
    assert ow.undo_combined(combined)==current
    assert combined!=ow.derive()  # do not overwrite the integrated v3 body with PR164's old prototype
    for old,new in ow.combined_sites():assert current.count(old)==1
    with pytest.raises(ValueError):ow.combined(current+'\n'+ow.combined_sites()[0][0])
    assert ow.rollback_script()==v3.CEREMONY_OPEN+v3.original_function(current)+'\n'+v3.CEREMONY_CLOSE
    assert ow.installation_script().count('CREATE OR REPLACE FUNCTION')==1
    # All non-worker definitions, including stop/exception/recovery, are exact.
    f=lambda s:re.sub(r'CREATE FUNCTION public.ingestion_worker_step\(.*?\$fn\$;', '',s,flags=re.S)
    assert f(combined)==f(current)


def test_committed_install_and_rollback_text_match_the_mechanical_derivation():
    from pathlib import Path
    root=Path('docs/design/ingestion-partial-observation-20261022')
    assert (root/'worker-step-observation.sql').read_text()==ow.installation_script()
    assert (root/'worker-step-v3-rollback.sql').read_text()==ow.rollback_script()


def test_current_combined_predicate_is_bolton_received_exact_and_null_safe():
    # Evaluate the current predicate through PostgreSQL, separate from PR164's
    # historical two-site matrix. No grant is issued and no ledger row changed.
    guard=next(new for old,new in ow.combined_sites() if old==ow.SITE_CHECKPOINT[0]).split(ow.ANCHOR,1)[1]
    assert guard.endswith(' IS DISTINCT FROM true')
    with connection() as conn:
        for council,semantics,enable in itertools.product(('bolton','bury',None),('RECEIVED','VALIDATED',None),([],['bolton'],['bury'],['bolton','bury'],None,'bolton')):
            query="SELECT %s FROM (SELECT %%s::jsonb AS g) q,(SELECT %%s::json AS checkpoint,%%s::json AS subject) w" % guard
            result=conn.execute(query,(json.dumps(dict(observation_councils=enable)),json.dumps(dict(kind='LISTING_OBSERVATION_V1')),json.dumps(dict(council=council,semantics=semantics)))).fetchone()[0]
            assert result is not (council=='bolton' and semantics=='RECEIVED' and enable==['bolton'])


def test_runtime_worker_body_pin_matches_the_mechanical_replacement():
    import hashlib
    from app.ingestion.observation_screening import OBSERVATION_WORKER_BODY_SHA256
    body=re.search(r'AS \$fn\$(.*?)\$fn\$;',ow.installation_script(),re.S).group(1)
    assert hashlib.sha256(body.encode()).hexdigest()==OBSERVATION_WORKER_BODY_SHA256
