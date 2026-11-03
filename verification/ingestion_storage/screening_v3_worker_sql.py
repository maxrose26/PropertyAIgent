"""Proposal (PR #173) section 2.1: the replacement of public.ingestion_worker_step that adds the explicitly selected screening-v3 branch, derived MECHANICALLY from the installed reviewed definition
(docs/design/ingestion-operational-20261016/worker.sql) by a short list of textual substitutions, each of which must match exactly once.

OFFLINE ONLY: nothing here installs, executes or registers anything. The v1 branch's text and behaviour are unchanged. v3 is DEFAULT OFF: a v3 child is admitted only when (a) the batch plan carries a `screening` binding,
(b) the grant lists that binding's `config_sha256` in `screening_configs`, and (c) the capture parent is a `LISTING_RECEIPT_V1` (an observation parent is never admitted, with or without the specification 034 change).
SQL checks the plan binding against the grant list and that revision, checkpoint and outcome are consistent with it; it does NOT recompute the configuration (it cannot recompute canonical JSON from jsonb): a wrong
threshold or code binding is refused by the Python recomputation, the controller's trusted-memory comparison and the grant's per-key binding.

The substitution list is independent of specification 034's two sites (capture-kind test in batch_row/batch_reseal and the capture_only checkpoint anchor); the tests apply both lists in both orders."""
from pathlib import Path

from app.ingestion.listing_screening import ROUTING_VOCABULARY, RULE_V3, V1_CONTRACT, V3_CONTRACT

ORIGINAL = Path(__file__).resolve().parents[2] / 'docs/design/ingestion-operational-20261016/worker.sql'
V3_ADMISSIONS = sorted(ROUTING_VOCABULARY[RULE_V3])
V3_LIST = ','.join("'%s'" % a for a in V3_ADMISSIONS)

# (plan binding present) and valid, listed by the grant, v3 contract, receipt parent only
V3_CHILD_OK = ("((plan ? 'screening') IS TRUE AND jsonb_typeof(plan->'screening')='object' AND (plan->'screening')-ARRAY['contract','config_sha256']='{}'::jsonb"
               " AND plan->'screening'->>'contract'='%s' AND plan->'screening'->>'config_sha256' ~ '^[a-f0-9]{64}$'"
               " AND jsonb_typeof(g->'screening_configs')='array' AND g->'screening_configs' ? (plan->'screening'->>'config_sha256')"
               " AND child->>'contract'='%s' AND capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1')" % (V3_CONTRACT, V3_CONTRACT))
V1_CHILD_OK = "((plan ? 'screening') IS DISTINCT FROM true AND child->>'contract'='%s')" % V1_CONTRACT

REVISION_V1 = "encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')"
REVISION_V3 = ("encode(sha256(convert_to('{\"config_sha256\":\"'||(plan->'screening'->>'config_sha256')||'\",\"record_sha256\":\"'||"
               "encode(sha256(convert_to(p_payload->>'record_json','UTF8')),'hex')||'\"}','UTF8')),'hex')")

RECEIPT_CHECK = ("   IF w.contract='%s' AND (coalesce(p_payload->>'rule_version','')<>'%s' OR coalesce(p_payload->>'routing_authority','')<>'count_assessment'"
                 " OR jsonb_typeof(p_payload->'count_assessment') IS DISTINCT FROM 'object' OR coalesce((p_payload->'count_assessment'->>'admission') NOT IN (%s),true)"
                 " OR coalesce(p_payload->>'assessment_revision','')<>w.revision OR coalesce(p_payload->>'record_sha256','') !~ '^[a-f0-9]{64}$' OR coalesce(p_payload->>'config_sha256','') !~ '^[a-f0-9]{64}$'"
                 " OR encode(sha256(convert_to('{\"config_sha256\":\"'||(p_payload->>'config_sha256')||'\",\"record_sha256\":\"'||(p_payload->>'record_sha256')||'\"}','UTF8')),'hex') IS DISTINCT FROM w.revision"
                 " OR coalesce(NOT (g->'screening_configs' ? (p_payload->>'config_sha256')),true)) THEN RAISE EXCEPTION 'SCREENING_V3_RECEIPT'; END IF;\n"
                 % (V3_CONTRACT, RULE_V3, V3_LIST))
OUTCOME_CHECK = ("   IF w.contract='%s' AND (p_payload->>'outcome' IS DISTINCT FROM w.checkpoint::jsonb->'count_assessment'->>'admission'"
                 " OR coalesce(NOT (g->'screening_configs' ? (w.checkpoint::jsonb->>'config_sha256')),true)) THEN RAISE EXCEPTION 'SCREENING_V3_OUTCOME'; END IF;\n" % V3_CONTRACT)

# Each (old, new) must match exactly once in the original. Order is irrelevant: the anchors do not overlap.
SITE_TYPES = ("OR child->>'contract' IS DISTINCT FROM 'listing-screen-v1' OR jsonb_typeof(p_payload->'record_json') IS DISTINCT FROM 'string'",
              "OR (%s OR %s) IS DISTINCT FROM true OR jsonb_typeof(p_payload->'record_json') IS DISTINCT FROM 'string'" % (V1_CHILD_OK, V3_CHILD_OK))
SITE_CONTRACT = ("OR child->'dependencies' IS DISTINCT FROM jsonb_build_array(capture.key) OR child->>'task'<>'SCREENING' OR child->>'contract'<>'listing-screen-v1'",
                 "OR child->'dependencies' IS DISTINCT FROM jsonb_build_array(capture.key) OR child->>'task'<>'SCREENING' OR child->>'contract' IS DISTINCT FROM (CASE WHEN (plan ? 'screening') IS TRUE THEN '%s' ELSE '%s' END)"
                 % (V3_CONTRACT, V1_CONTRACT))
SITE_REVISION = ("(p_payload->>'record_json')::jsonb IS DISTINCT FROM rec OR %s IS DISTINCT FROM child->>'revision'" % REVISION_V1,
                 "(p_payload->>'record_json')::jsonb IS DISTINCT FROM rec OR (CASE WHEN (plan ? 'screening') IS TRUE THEN %s ELSE %s END) IS DISTINCT FROM child->>'revision'" % (REVISION_V3, REVISION_V1))
SITE_INSERT = ("'SCREENING','listing-screen-v1',child->>'revision',json_build_array(capture.key)",
               "'SCREENING',child->>'contract',child->>'revision',json_build_array(capture.key)")
SITE_CHECKPOINT = ("   -- SQL records a worker receipt, never promotes its contents to factual truth.\n",
                   RECEIPT_CHECK + "   -- SQL records a worker receipt, never promotes its contents to factual truth.\n")
SITE_COMPLETE = ("   IF w.contract='listing-batch-v1' THEN\n    IF w.checkpoint::jsonb->>'kind'<>'BATCH_PROGRESS_V1'",
                 OUTCOME_CHECK + "   IF w.contract='listing-batch-v1' THEN\n    IF w.checkpoint::jsonb->>'kind'<>'BATCH_PROGRESS_V1'")
SITES = (SITE_TYPES, SITE_CONTRACT, SITE_REVISION, SITE_INSERT, SITE_CHECKPOINT, SITE_COMPLETE)


def original_text():
    return ORIGINAL.read_bytes().decode('utf-8').replace('\r\n', '\n')


def derive(original=None, sites=SITES):
    """The replacement definition: every site must be present exactly once, or the derivation fails."""
    text = original if original is not None else original_text()
    for old, new in sites:
        if text.count(old) != 1:
            raise ValueError('SUBSTITUTION_SITE_NOT_UNIQUE:' + old[:80])
        text = text.replace(old, new)
    return text


def undo(derived, sites=SITES):
    """The inverse: undoing every substitution reproduces the original byte for byte."""
    text = derived
    for old, new in reversed(sites):
        if text.count(new) != 1:
            raise ValueError('REPLACEMENT_NOT_UNIQUE:' + new[:80])
        text = text.replace(new, old)
    return text


def capture_bound_sites():
    """Opt-in COMPLETE-capture task identity; historical v3/v1 remain valid.

    Reuses the observation revision formula without enabling partial observations.
    The SQL batch verifies the actual parent and its canonical digest before
    deriving a child; receipt validation requires that same digest and parent.
    """
    scoped="encode(sha256(convert_to('{\"assessment_revision\":\"'||%s||'\",\"observation_sha256\":\"'||(plan->>'capture_sha256')||'\"}','UTF8')),'hex')" % REVISION_V3
    result_base="encode(sha256(convert_to('{\"config_sha256\":\"'||(p_payload->>'config_sha256')||'\",\"record_sha256\":\"'||(p_payload->>'record_sha256')||'\"}','UTF8')),'hex')"
    result_scoped="encode(sha256(convert_to('{\"assessment_revision\":\"'||%s||'\",\"observation_sha256\":\"'||(p_payload->>'capture_checkpoint_sha256')||'\"}','UTF8')),'hex')" % result_base
    guard="""   IF w.contract='listing-screen-v3' AND p_payload ? 'capture_bound' THEN
    IF p_payload->'capture_bound' IS DISTINCT FROM 'true'::jsonb
    OR jsonb_array_length(w.dependencies::jsonb)<>1
    OR p_payload->>'capture_key' IS DISTINCT FROM w.dependencies->>0
    OR coalesce(p_payload->>'capture_checkpoint_sha256','') !~ '^[a-f0-9]{64}$'
    OR NOT EXISTS(SELECT 1 FROM public.ingestion_work_items x WHERE x.key=w.dependencies->>0
      AND x.state='COMPLETE' AND x.task='DISCOVERY' AND x.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1')
    THEN RAISE EXCEPTION 'CAPTURE_BOUND_RECEIPT'; END IF;
   END IF;
"""
    return (
        (REVISION_V3+" ELSE "+REVISION_V1,
         "(CASE WHEN plan->'capture_bound'='true'::jsonb THEN %s ELSE %s END) ELSE %s" % (scoped,REVISION_V3,REVISION_V1)),
        (result_base+" IS DISTINCT FROM w.revision",
         "(CASE WHEN p_payload->'capture_bound'='true'::jsonb THEN %s ELSE %s END) IS DISTINCT FROM w.revision" % (result_scoped,result_base)),
        ("   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')",guard+"   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')"),
        ("   idx:=coalesce((w.checkpoint::jsonb->>'next')::integer,(plan->>'first')::integer);",
         "   IF plan ? 'capture_bound' AND (plan->'capture_bound' IS DISTINCT FROM 'true'::jsonb OR NOT (plan ? 'screening')) THEN RAISE EXCEPTION 'CAPTURE_BOUND_PLAN'; END IF;\n   idx:=coalesce((w.checkpoint::jsonb->>'next')::integer,(plan->>'first')::integer);"),
    )


def capture_bound_text(original=None):
    """Reviewed offline extension; no installation, grant or source authority."""
    text=derive() if original is None else original
    for old,new in capture_bound_sites():
        if text.count(old)!=1:raise ValueError('SUBSTITUTION_SITE_NOT_UNIQUE:'+old[:80])
        text=text.replace(old,new)
    return text


def replacement_function(original=None):
    """Only the `CREATE FUNCTION public.ingestion_worker_step ... $fn$;` statement of the derived file, rewritten as CREATE OR REPLACE for installation over the installed original.
    Ownership and ACL are preserved by CREATE OR REPLACE; the installation ceremony re-asserts them (docs: installation route)."""
    text = derive(original)
    start = text.index('CREATE FUNCTION public.ingestion_worker_step(')
    end = text.index('$fn$;', text.index('AS $fn$', start)) + len('$fn$;')
    return text[start:end].replace('CREATE FUNCTION public.ingestion_worker_step(', 'CREATE OR REPLACE FUNCTION public.ingestion_worker_step(', 1)


CEREMONY_OPEN = """BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='10s';
GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;
GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;
SET LOCAL ROLE ingestion_storage_owner;
"""
CEREMONY_CLOSE = """RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER;
COMMIT;
"""
# Read back after the ceremony: the function body digest, its owner and ACL, and that the temporary owner capability is gone (the same five flags the owner's registration readback requires to be all false).
READBACK_SQL = {
    'body_sha256': "SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure",
    'owner': "SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure",
    'acl': "SELECT coalesce(array_agg(p.rolname||':'||a.privilege_type ORDER BY p.rolname,a.privilege_type),'{}') FROM pg_proc f CROSS JOIN LATERAL aclexplode(f.proacl) a JOIN pg_roles p ON p.oid=a.grantee WHERE f.oid='public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)'::regprocedure",
    'capability_absent': "SELECT pg_has_role(current_user,'ingestion_storage_owner','USAGE'),pg_has_role(current_user,'ingestion_storage_owner','SET'),pg_has_role(current_user,'ingestion_barrier_releaser','USAGE'),pg_has_role(current_user,'ingestion_barrier_releaser','SET'),has_schema_privilege('ingestion_storage_owner','public','CREATE')",
}


def original_function(original=None):
    """The installed (original) function statement, as CREATE OR REPLACE: the rollback text."""
    text = original if original is not None else original_text()
    start = text.index('CREATE FUNCTION public.ingestion_worker_step(')
    end = text.index('$fn$;', text.index('AS $fn$', start)) + len('$fn$;')
    return text[start:end].replace('CREATE FUNCTION public.ingestion_worker_step(', 'CREATE OR REPLACE FUNCTION public.ingestion_worker_step(', 1)


def installation_script(original=None):
    """The owner-terminal ceremony that replaces the function (the existing policy-ceremony shape): temporary, explicit, self-revoking ownership; ONE statement; no other object touched. For REVIEW ONLY: nothing runs it."""
    return CEREMONY_OPEN + replacement_function(original) + '\n' + CEREMONY_CLOSE


def rollback_script(original=None):
    """Byte-for-byte restoration of the previously installed reviewed function, by the same ceremony."""
    return CEREMONY_OPEN + original_function(original) + '\n' + CEREMONY_CLOSE
