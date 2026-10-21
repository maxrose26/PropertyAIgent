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
