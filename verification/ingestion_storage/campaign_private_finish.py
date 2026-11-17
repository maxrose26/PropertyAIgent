"""Private-only campaign finish guard adapted from pinned #213.

Original database_evidence.FINISH_GUARD_SQL is preserved in #213 f027ba28.
Only the outward private receipt discriminant changes. Ordinary intake stays
unchanged. No installation or connection occurs here.
"""
FINISH_GUARD_SQL = r'''
   IF e->>'evidence_backend'='POSTGRES_PILOT_V1' THEN
    IF p->'publication'->>'backend' IS DISTINCT FROM 'PRIVATE_POSTGRES_V1'
     OR p->'publication'->>'period' IS DISTINCT FROM a OR p->'publication'->>'run_id' IS DISTINCT FROM p->>'run_id'
     OR p->'publication'->>'name' IS DISTINCT FROM 'final/result-before-publication.json'
     OR NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
       AND d.name='final/result-before-publication.json' AND d.sha256=p->'publication'->>'sha256'
       AND d.sha256=encode(sha256(d.body),'hex') AND octet_length(d.body)=(p->'publication'->>'bytes')::integer
       AND (convert_from(d.body,'UTF8')::jsonb)->>'period'=a
       AND (convert_from(d.body,'UTF8')::jsonb)->>'run_id'=p->>'run_id'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'status'=p->>'status'
       AND (convert_from(d.body,'UTF8')::jsonb)->'execution_binding'=e->'execution_binding'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'cleanup'='CLOSED'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'authority_closure'='INVALIDATED'
       AND (convert_from(d.body,'UTF8')::jsonb)->>'github_publication'='NOT_REQUESTED')
     OR NOT EXISTS(SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
       AND d.name='final/events-before-publication.json' AND d.sha256=encode(sha256(d.body),'hex')
       AND jsonb_typeof(convert_from(d.body,'UTF8')::jsonb)='array')
     OR EXISTS(SELECT 1 FROM jsonb_each(e->'days'->(ctl->'intake_run'->>'day')) x
       JOIN public.ingestion_work_items w ON w.key=x.value#>>'{}'
       WHERE w.state IN ('COMPLETE','DEFERRED') AND NOT EXISTS(
        SELECT 1 FROM public.ingestion_run_evidence d WHERE d.period=a AND d.run_id=p->>'run_id'
         AND d.name IN ('capture-1/source.json','capture-2/source.json')
         AND d.sha256=w.checkpoint::jsonb->>'source_sha256'
         AND d.sha256=encode(sha256(d.body),'hex')
         AND (((convert_from(d.body,'UTF8')::jsonb)->>'council'=w.subject::jsonb->>'council' AND w.subject::jsonb->>'council'='tameside') OR (w.subject::jsonb->>'council'='manchester' AND (convert_from(d.body,'UTF8')::jsonb)->>'case'='discovery_manchester_ui_window'))
         AND (convert_from(d.body,'UTF8')::jsonb)->'requested_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end')
         AND (w.subject::jsonb->>'council'<>'manchester' OR w.state<>'COMPLETE' OR (convert_from(d.body,'UTF8')::jsonb)->'applied_interval'=jsonb_build_array(w.subject::jsonb->>'start',w.subject::jsonb->>'end'))
         AND w.checkpoint::jsonb->'durable_archive'->>'backend'='PRIVATE_POSTGRES_V1'
         AND w.checkpoint::jsonb->'durable_archive'->>'period'=a
         AND w.checkpoint::jsonb->'durable_archive'->>'run_id'=p->>'run_id'
         AND w.checkpoint::jsonb->'durable_archive'->>'name'=d.name
         AND (w.checkpoint::jsonb->'durable_archive'->>'bytes')::integer=octet_length(d.body)
       ))
    THEN RAISE EXCEPTION 'INTAKE_DATABASE_EVIDENCE_NOT_VERIFIED'; END IF;
   ELSIF p->'publication' ? 'backend' THEN RAISE EXCEPTION 'INTAKE_EVIDENCE_BACKEND_NOT_AUTHORISED';
   END IF;
'''

def adapt(source):
    anchor="  IF p->>'operation'='intake_finish' THEN\n"
    commit="OR coalesce(p->'publication'->>'commit','') !~ '^[a-f0-9]{40}$'"
    if source.count(anchor)!=1 or source.count(commit)!=1:
        raise ValueError('CAMPAIGN_PRIVATE_FINISH_SOURCE_DRIFT')
    return source.replace(anchor,anchor+FINISH_GUARD_SQL,1).replace(commit,"OR (e->>'evidence_backend' IS DISTINCT FROM 'POSTGRES_PILOT_V1' AND coalesce(p->'publication'->>'commit','') !~ '^[a-f0-9]{40}$')",1)
