"""Specification 034 section 3: the proposed replacement of public.ingestion_worker_step, derived mechanically from the installed reviewed definition by exactly two textual substitutions.
OFFLINE ONLY: nothing here installs, executes or registers anything. The admission predicate is explicitly boolean and default-deny: a NULL, absent or unrecognised kind, an enablement that is not a
JSON array, or an observation for a council the grant does not list, makes the predicate FALSE and the check raises."""
from pathlib import Path

ORIGINAL=Path(__file__).resolve().parents[2]/"docs/design/ingestion-operational-20261016/worker.sql"
RECEIPT="LISTING_RECEIPT_V1"
OBSERVATION="LISTING_OBSERVATION_V1"


def admitted(kind,subject):
    """TRUE only for a receipt, or an observation whose council the grant lists. coalesce(...,false) removes every NULL; the caller raises unless this is TRUE (IS DISTINCT FROM true)."""
    return ("coalesce(%s='%s' OR (%s='%s' AND coalesce(jsonb_typeof(g->'observation_councils'),'null')='array' AND g->'observation_councils' ? (%s)),false)"%(kind,RECEIPT,kind,OBSERVATION,subject))


def reject_unless_admitted(kind,subject):
    return "(%s) IS DISTINCT FROM true"%admitted(kind,subject)


SITE_BATCH=("capture.checkpoint::jsonb->>'kind'<>'%s'"%RECEIPT,reject_unless_admitted("capture.checkpoint::jsonb->>'kind'","capture.subject::jsonb->>'council'"))
ANCHOR="w.checkpoint::jsonb IS DISTINCT FROM p_payload OR "      # op enqueue_child has the same kind test and must stay unchanged, so the checkpoint site is anchored to its own line
SITE_CHECKPOINT=(ANCHOR+"w.checkpoint::jsonb->>'kind' IS DISTINCT FROM '%s'"%RECEIPT,ANCHOR+reject_unless_admitted("w.checkpoint::jsonb->>'kind'","w.subject::jsonb->>'council'"))


def derive(original=None):
    text=original if original is not None else ORIGINAL.read_text(encoding="utf-8")
    for old,new in (SITE_BATCH,SITE_CHECKPOINT):
        if text.count(old)!=1:raise ValueError("SUBSTITUTION_SITE_NOT_UNIQUE:"+old)
        text=text.replace(old,new)
    return text

# Reconcile PR164's two sites with the CURRENT reviewed v3 worker, never the
# obsolete pre-v3 body. No policy function, owner, signature or ACL changes.
def combined_sites():
    from . import screening_v3_worker_sql as v3
    def allowed(kind, subject):
        return ("coalesce(%s='LISTING_RECEIPT_V1' OR (%s='LISTING_OBSERVATION_V1' AND %s->>'council'='bolton' AND %s->>'semantics'='RECEIVED' AND g->'observation_councils'='[\"bolton\"]'::jsonb),false)" % (kind,kind,subject,subject))
    capkind="capture.checkpoint::jsonb->>'kind'"
    capallowed=allowed(capkind,'capture.subject::jsonb')
    base="(CASE WHEN (plan ? 'screening') IS TRUE THEN %s ELSE %s END)" % (v3.REVISION_V3,v3.REVISION_V1)
    scoped="encode(sha256(convert_to('{\"assessment_revision\":\"'||%s||'\",\"observation_sha256\":\"'||(plan->>'capture_sha256')||'\"}','UTF8')),'hex')" % base
    result_base="encode(sha256(convert_to('{\"config_sha256\":\"'||(p_payload->>'config_sha256')||'\",\"record_sha256\":\"'||(p_payload->>'record_sha256')||'\"}','UTF8')),'hex')"
    result_scoped="encode(sha256(convert_to('{\"assessment_revision\":\"'||%s||'\",\"observation_sha256\":\"'||(p_payload->>'observation_digest')||'\"}','UTF8')),'hex')" % result_base
    screening_check="""   IF w.task='SCREENING' THEN
    SELECT * INTO STRICT capture FROM public.ingestion_work_items WHERE key=w.dependencies::jsonb->>0 FOR SHARE;
    IF capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' THEN
     IF (%s) IS DISTINCT FROM true OR capture.state<>'COMPLETE'
      OR p_payload->>'source_kind' IS DISTINCT FROM 'LISTING_OBSERVATION_V1' OR p_payload->>'window_claim' IS DISTINCT FROM 'NONE'
      OR p_payload->>'observed_at' IS DISTINCT FROM capture.checkpoint::jsonb->>'observed_at'
      OR p_payload->>'source_sha256' IS DISTINCT FROM capture.checkpoint::jsonb->>'source_sha256'
      OR coalesce(p_payload->>'observation_digest','') !~ '^[a-f0-9]{64}$'
      OR (w.contract='listing-screen-v1' AND encode(sha256(convert_to('{"assessment_revision":"'||(p_payload->>'record_sha256')||'","observation_sha256":"'||(p_payload->>'observation_digest')||'"}','UTF8')),'hex') IS DISTINCT FROM w.revision)
     THEN RAISE EXCEPTION 'OBSERVATION_SCREEN_BINDING'; END IF;
    ELSIF p_payload ?| ARRAY['source_kind','observation_digest','window_claim','observed_at'] THEN RAISE EXCEPTION 'OBSERVATION_SOURCE_KIND'; END IF;
   END IF;
""" % capallowed
    resolve_check="   IF p_op='resolve_effect' THEN\n"
    resolve_new=resolve_check+"    IF (p_payload->>'kind'='LISTING_OBSERVATION_V1' AND (w.task<>'DISCOVERY' OR (%s) IS DISTINCT FROM true)) OR (w.task='DISCOVERY' AND (g->>'capture_only')::boolean IS TRUE AND (%s) IS DISTINCT FROM true) THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;\n" % (allowed("p_payload->>'kind'",'w.subject::jsonb'),allowed("p_payload->>'kind'",'w.subject::jsonb'))
    return (
        (resolve_check,resolve_new),
        ("  ELSIF p_op='checkpoint' THEN\n", "  ELSIF p_op='checkpoint' THEN\n   IF p_payload->>'kind'='LISTING_OBSERVATION_V1' AND (w.task<>'DISCOVERY' OR w.checkpoint::jsonb IS DISTINCT FROM p_payload OR (%s) IS DISTINCT FROM true) THEN RAISE EXCEPTION 'BROKER_CAPTURE_REQUIRED'; END IF;\n" % allowed("p_payload->>'kind'",'w.subject::jsonb')),
        (SITE_BATCH[0],"(%s) IS DISTINCT FROM true" % capallowed),
        (SITE_CHECKPOINT[0],ANCHOR+"(%s) IS DISTINCT FROM true" % allowed("w.checkpoint::jsonb->>'kind'",'w.subject::jsonb')),
        ("AND capture.checkpoint::jsonb->>'kind'='LISTING_RECEIPT_V1')", "AND (%s))" % capallowed),
        (base+" IS DISTINCT FROM child->>'revision'", "(CASE WHEN %s='LISTING_OBSERVATION_V1' THEN %s ELSE %s END) IS DISTINCT FROM child->>'revision'" % (capkind,scoped,base)),
        (result_base+" IS DISTINCT FROM w.revision", "(CASE WHEN p_payload->>'source_kind'='LISTING_OBSERVATION_V1' THEN %s ELSE %s END) IS DISTINCT FROM w.revision" % (result_scoped,result_base)),
        ("   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')",screening_check+"   IF w.contract='listing-screen-v3' AND (coalesce(p_payload->>'rule_version','')"),
        ("   idx:=coalesce((w.checkpoint::jsonb->>'next')::integer,(plan->>'first')::integer);", "   IF capture.checkpoint::jsonb->>'kind'='LISTING_OBSERVATION_V1' AND plan->>'source_kind' IS DISTINCT FROM 'LISTING_OBSERVATION_V1' THEN RAISE EXCEPTION 'OBSERVATION_PLAN_BINDING'; END IF;\n   idx:=coalesce((w.checkpoint::jsonb->>'next')::integer,(plan->>'first')::integer);"),
    )


def combined(current=None):
    from . import screening_v3_worker_sql as v3
    text=v3.derive() if current is None else current
    for old,new in combined_sites():
        if text.count(old)!=1:raise ValueError('SUBSTITUTION_SITE_NOT_UNIQUE:'+old[:80])
        text=text.replace(old,new)
    return text


def undo_combined(text):
    for old,new in reversed(combined_sites()):
        if text.count(new)!=1:raise ValueError('REPLACEMENT_NOT_UNIQUE:'+new[:80])
        text=text.replace(new,old)
    return text


def installation_script():
    from . import screening_v3_worker_sql as v3
    return v3.CEREMONY_OPEN+v3.original_function(combined())+'\n'+v3.CEREMONY_CLOSE


def rollback_script():
    from . import screening_v3_worker_sql as v3
    return v3.CEREMONY_OPEN+v3.original_function(v3.derive())+'\n'+v3.CEREMONY_CLOSE
