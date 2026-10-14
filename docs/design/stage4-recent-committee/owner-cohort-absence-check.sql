BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';

WITH proposed(council_code, reference) AS (
  VALUES
    ('bolton', '21080/25'),
    ('manchester', '143413/FO/2025'),
    ('manchester', '145583/FO/2026'),
    ('salford', 'PA/2025/1664'),
    ('tameside', '26/00396/FUL')
)
SELECT
  transaction_timestamp() AS checked_at,
  p.council_code,
  p.reference,
  count(a.id) AS matching_rows_up_to_two,
  COALESCE(
    jsonb_agg(jsonb_build_object(
      'id', a.id,
      'council_code', a.council_code,
      'reference', a.reference
    )) FILTER (WHERE a.id IS NOT NULL),
    '[]'::jsonb
  ) AS matches
FROM proposed p
LEFT JOIN LATERAL (
  SELECT id, council_code, reference
  FROM public.applications
  WHERE council_code = p.council_code
    AND reference = p.reference
  LIMIT 2
) a ON true
GROUP BY p.council_code, p.reference
ORDER BY p.council_code, p.reference;

COMMIT;
