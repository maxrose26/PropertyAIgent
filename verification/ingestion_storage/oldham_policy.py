"""Dormant policy: one substitution over the reviewed v3 worker, no installation on import."""
from . import screening_v3_worker_sql as v3
from . import observation_worker_sql as observation

OLD = 'IF NOT public.ingestion_bolton_allowed(ctl,p_authority,w.subject::jsonb) THEN'
NEW = 'IF NOT (public.ingestion_bolton_allowed(ctl,p_authority,w.subject::jsonb) OR public.ingestion_oldham_allowed(ctl,p_authority,w.key,w.subject::jsonb)) THEN'

FUNCTION = r"""
CREATE FUNCTION public.ingestion_oldham_allowed(ctl jsonb, authority text, work_key text, subject jsonb) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $oldham$
 SELECT coalesce(
 ctl->'global_stop'='{"reason":"CONSUMED_SALFORD_GLOBAL_STOP","run":"38884069913"}'::jsonb
 AND ctl->>'manual_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
 AND ctl->>'last_hard_stop'='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
 AND ctl->'hard_stop_generation'='3'::jsonb
 AND subject->>'council'='oldham'
 AND ctl->'oldham_allowances'->authority->'package'->>'authority'=authority
 AND ctl->'oldham_allowances'->authority->'package'->'scope'->>'council'='oldham'
 AND ctl->'oldham_allowances'->authority->'package'->'scope'->>'semantics'='RECEIVED'
 AND ctl->'oldham_allowances'->authority->'package'->'stop'=jsonb_build_object('global_stop',ctl->'global_stop','manual_stop',ctl->'manual_stop','last_hard_stop',ctl->'last_hard_stop','hard_stop_generation',ctl->'hard_stop_generation')
 AND ctl->'oldham_allowances'->authority->'source_cap'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'source_calls'
 AND ctl->'oldham_allowances'->authority->'write_cap'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'writes'
 AND ctl->'oldham_allowances'->authority->'expires_at'=ctl->'oldham_allowances'->authority->'package'->'registration'->'grant'->'expires_at'
 AND ctl->'oldham_allowances'->authority->>'package_sha256'=ctl->'grants'->authority->>'oldham_package_sha256'
 AND ctl->'oldham_allowances'->authority->>'package_sha256'=encode(sha256(convert_to((ctl->'oldham_allowances'->authority->'package')::text,'UTF8')),'hex')
 AND ctl->'oldham_allowances'->authority->>'revoked'='false'
 AND (ctl->'oldham_allowances'->authority->>'expires_at')::double precision>extract(epoch FROM clock_timestamp())
 AND ctl->'oldham_allowances'->authority->'grant_binding'=(ctl->'grants'->authority)-ARRAY['source_calls','writes']
 AND ((ctl->'grants'->authority)-ARRAY['source_calls','writes','oldham_package_sha256'])=((ctl->'oldham_allowances'->authority->'package'->'registration'->'grant')-ARRAY['source_calls','writes'])
 AND ctl->'oldham_allowances'->authority->'grant_binding'->'keys' ? work_key
 AND (ctl->'grants'->authority->>'source_calls')::integer BETWEEN 0 AND (ctl->'oldham_allowances'->authority->>'source_cap')::integer
 AND (ctl->'grants'->authority->>'writes')::integer BETWEEN 0 AND (ctl->'oldham_allowances'->authority->>'write_cap')::integer
 AND ctl->'oldham_allowances'->authority->'grant_binding'->'bindings'->work_key->'subject'=subject,false)
$oldham$;
REVOKE ALL ON FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) FROM PUBLIC;
"""

def replacement():
    text=v3.original_function(observation.combined())
    if text.count(OLD)!=1:raise ValueError('OLDHAM_POLICY_ANCHOR')
    text=text.replace(OLD,NEW)
    anchor=" IF ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb THEN"
    check=" IF (left(p_authority,23)='INGESTION_CHAIN_OLDHAM_') AND NOT public.ingestion_oldham_allowed(ctl,p_authority,w.key,w.subject::jsonb) THEN RAISE EXCEPTION 'OLDHAM_ALLOWANCE_INVALID' USING ERRCODE='42501'; END IF;\n"
    if text.count(anchor)!=1:raise ValueError('OLDHAM_STOP_ANCHOR')
    return text.replace(anchor,check+anchor)

def undo(text):
    if text.count(NEW)!=1:raise ValueError('OLDHAM_POLICY_INVERSE')
    check=" IF (left(p_authority,23)='INGESTION_CHAIN_OLDHAM_') AND NOT public.ingestion_oldham_allowed(ctl,p_authority,w.key,w.subject::jsonb) THEN RAISE EXCEPTION 'OLDHAM_ALLOWANCE_INVALID' USING ERRCODE='42501'; END IF;\n"
    if text.count(check)!=1:raise ValueError('OLDHAM_STOP_INVERSE')
    return text.replace(check,'').replace(NEW,OLD)

def installation_script():
    return v3.CEREMONY_OPEN+FUNCTION+'\n'+replacement()+'\n'+v3.CEREMONY_CLOSE

def rollback_script():
    return v3.CEREMONY_OPEN+v3.original_function(observation.combined())+'\nDROP FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb);\n'+v3.CEREMONY_CLOSE
