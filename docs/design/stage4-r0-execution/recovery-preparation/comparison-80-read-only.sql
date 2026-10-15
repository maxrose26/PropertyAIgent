-- READ ONLY: exact frozen 80 identities; maximum two matches per identity.
-- No planning facts, credentials or broad identity export.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
WITH requested(council_code, reference) AS (
  VALUES
    ('bolton', '01780/26'),
    ('bolton', '01778/26'),
    ('bolton', '01776/26'),
    ('bolton', '01775/26'),
    ('bolton', '01769/26'),
    ('bolton', '01768/26'),
    ('bolton', '01821/26'),
    ('bolton', '01816/26'),
    ('bolton', '01815/26'),
    ('bolton', '01813/26'),
    ('bolton', '01811/26'),
    ('bolton', '01810/26'),
    ('bolton', '01809/26'),
    ('bolton', '01808/26'),
    ('bolton', '01807/26'),
    ('bolton', '01806/26'),
    ('bolton', '01805/26'),
    ('bolton', '01804/26'),
    ('bolton', '01801/26'),
    ('bolton', '01800/26'),
    ('bolton', '01799/26'),
    ('bolton', '01797/26'),
    ('bolton', '01796/26'),
    ('bolton', '01795/26'),
    ('bolton', '01794/26'),
    ('bolton', '01793/26'),
    ('bolton', '01791/26'),
    ('bolton', '01790/26'),
    ('bolton', '01789/26'),
    ('bolton', '01787/26'),
    ('bolton', '01786/26'),
    ('bolton', '01785/26'),
    ('bolton', '01784/26'),
    ('bolton', '01783/26'),
    ('bolton', '01782/26'),
    ('bolton', '01858/26/PREMIN'),
    ('bolton', '01852/26'),
    ('bolton', '01851/26'),
    ('bolton', '01848/26'),
    ('bolton', '01847/26'),
    ('bolton', '01845/26'),
    ('bolton', '01843/26'),
    ('bolton', '01842/26'),
    ('bolton', '01841/26'),
    ('bolton', '01840/26'),
    ('bolton', '01839/26'),
    ('bolton', '01838/26'),
    ('bolton', '01836/26'),
    ('bolton', '01833/26'),
    ('bolton', '01832/26'),
    ('bolton', '01827/26'),
    ('bolton', '01826/26'),
    ('bolton', '01825/26'),
    ('bolton', '01823/26'),
    ('bury', '73701'),
    ('bury', '73700'),
    ('bury', '73699'),
    ('bury', '73698'),
    ('bury', '73697'),
    ('bury', '73736'),
    ('bury', '73733'),
    ('bury', '73730'),
    ('bury', '73729'),
    ('bury', '73728'),
    ('bury', '73726'),
    ('bury', '73725'),
    ('bury', '73723'),
    ('bury', '73722'),
    ('bury', '73721'),
    ('bury', '73720'),
    ('bury', '73719'),
    ('bury', '73718'),
    ('bury', '73716'),
    ('bury', '73713'),
    ('bury', '73708'),
    ('bury', '73755'),
    ('bury', '73748'),
    ('bury', '73743'),
    ('bury', '73742'),
    ('bury', '73741')
), compared AS (
 SELECT r.council_code, r.reference,
        COALESCE(m.matches, '[]'::jsonb) AS matches,
        COALESCE(m.n, 0) AS matching_rows_up_to_two
 FROM requested r
 LEFT JOIN LATERAL (
   SELECT jsonb_agg(jsonb_build_object('id', x.id,
            'council_code', x.council_code, 'reference', x.reference)
            ORDER BY x.id) AS matches, count(*) AS n
   FROM (SELECT a.id, a.council_code, a.reference
         FROM public.applications a
         WHERE a.council_code = r.council_code AND a.reference = r.reference
         ORDER BY a.id LIMIT 2) x
 ) m ON TRUE
)
SELECT jsonb_build_object(
 'snapshot_timestamp', statement_timestamp(),
 'database_name', current_database(),
 'requested_identities', (SELECT count(*) FROM requested),
 'result_identities', count(*),
 'comparison', jsonb_agg(jsonb_build_object(
   'council_code', council_code, 'reference', reference,
   'matching_rows_up_to_two', matching_rows_up_to_two, 'matches', matches)
   ORDER BY council_code, reference)
) AS identity_comparison
FROM compared;
COMMIT;
