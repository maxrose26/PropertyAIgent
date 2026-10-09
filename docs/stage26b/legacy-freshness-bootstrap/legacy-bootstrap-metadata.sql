BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout='5s';
SET LOCAL lock_timeout='2s';
SHOW transaction_read_only;
WITH a AS MATERIALIZED (SELECT a.id,a.site_id,a.council_code,a.reference,a.status,a.decision,a.application_type,a.decision_issued_date,a.status_verified_at FROM public.applications a JOIN public.sites s ON s.id=a.site_id WHERE NOT coalesce(s.excluded,false) ORDER BY a.id LIMIT 1501), summaries AS (SELECT coalesce(prompt_version,'[NULL]') prompt_version,count(*) n,count(*) FILTER(WHERE headline IS NOT NULL AND headline<>'') narrative_count FROM public.allocation_intelligence_summaries GROUP BY prompt_version)
SELECT jsonb_build_object('utc',now(),'read_only',current_setting('transaction_read_only'),'nonexcluded_sites',(SELECT count(*) FROM public.sites WHERE NOT coalesce(excluded,false)),'applications',coalesce((SELECT jsonb_agg(a ORDER BY id) FROM a),'[]'::jsonb),'overflow',(SELECT count(*)>1500 FROM a),'summary_versions',(SELECT jsonb_agg(summaries ORDER BY prompt_version) FROM summaries),'allocation_count',(SELECT count(*) FROM public.local_plan_sites),'verified_inactive_role',(SELECT NOT rolcanlogin AND NOT rolinherit AND NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname='propertyaigent_evidence_validator')) AS metadata;
ROLLBACK;
