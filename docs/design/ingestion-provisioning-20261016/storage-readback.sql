BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='3s';
SET LOCAL idle_in_transaction_session_timeout='10s';
SELECT jsonb_build_object(
 'current_user',current_user,'session_user',session_user,
 'rows',(SELECT jsonb_agg(to_jsonb(w) ORDER BY key) FROM public.ingestion_work_items w),
 'attempts',(SELECT count(*) FROM public.ingestion_work_attempts),
 'serialized_bytes',(SELECT sum(octet_length(to_jsonb(w)::text)) FROM public.ingestion_work_items w),
 'physical_bytes',pg_total_relation_size('public.ingestion_work_items')+pg_total_relation_size('public.ingestion_work_attempts'));
ROLLBACK;
