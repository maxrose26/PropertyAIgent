"""Uninstalled, fail-closed Tameside first historical issuer candidate.

NOT an executable release procedure. The normal rolling issuer/installer,
private evidence flag, owner connection and frozen #213 remain unchanged.
No credentials, SQL connection, source request or owner approval is supplied.

This is the first source-pinned part of the historical issuer/owner/runtime
integration. It deliberately always refuses invocation (WITHHELD) until a
separately reviewed release revision and explicit owner operation approval.
"""
import hashlib
from pathlib import Path
from .intake_policy import policy_sql

PINNED_POLICY_GIT_BLOB = "4896e5b0bef007143e0ee4eb06e7f969c0b4cafc"
PERIOD = "S4_TAMESIDE_RECEIVED_20260915_20260921_V1"
FUNCTION = "ingestion_register_tameside_first_once"
FIRST_DATE = "2026-09-15"
LAST_DATE = "2026-09-21"
REVIEW_STATUS = "WITHHELD"

# Exact existing production rolling capture guard; only the distinct,
# non-installed function is transformed. Ordinary policy_sql() is untouched.
_ROLLING = """OR item->'subject'->>'end'<>((clock_timestamp() AT TIME ZONE 'Europe/London')::date-1)::text
    OR item->'subject'->>'start'<>((clock_timestamp() AT TIME ZONE 'Europe/London')::date-7)::text"""
_HISTORICAL = """OR item->'subject'->>'end' IS DISTINCT FROM '2026-09-21'
    OR item->'subject'->>'start' IS DISTINCT FROM '2026-09-15'"""
_ENTRY_ANCHOR = "IF p->>'operation' IN ('intake_period','intake_capture','intake_screen','intake_close','intake_finish') THEN"
_ENTRY_GUARD = """ IF coalesce(p->>'operation','') NOT IN
   ('intake_period','intake_capture','intake_screen','intake_close','intake_finish')
 THEN RAISE EXCEPTION 'TAMESIDE_FIRST_NO_LEGACY_OPERATION' USING ERRCODE='42501'; END IF;
"""
_PERIOD_ANCHOR = "IF a IS NULL OR a !~ '^[A-Za-z0-9_-]{1,60}$' THEN RAISE EXCEPTION 'INTAKE_PERIOD_ID'; END IF;"
_GUARD = r"""
  -- Locks on the controller were already acquired by the existing issuer.
  -- This exact-period restriction applies to every operation, not just owner
  -- registration; the existing normal daily issuer remains byte-for-byte.
  IF current_database() IS DISTINCT FROM 'postgres'
   OR a IS DISTINCT FROM 'S4_TAMESIDE_RECEIVED_20260915_20260921_V1'
   OR (ctl->>'hard_stop_generation')::integer IS DISTINCT FROM 16
   OR ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb
   OR ctl->>'manual_stop' IS NOT NULL
   OR p->>'operation' NOT IN
      ('intake_period','intake_capture','intake_screen','intake_close','intake_finish')
  THEN RAISE EXCEPTION 'TAMESIDE_FIRST_SCOPE_OR_STOP' USING ERRCODE='42501'; END IF;
  IF p->>'operation'='intake_period' THEN
   IF p->'policy'->>'mode' IS DISTINCT FROM 'TAMESIDE_FIRST_HISTORICAL_V1'
    OR p->'policy'->'test_evidence' IS DISTINCT FROM 'false'::jsonb
    OR p->'policy'->'max_runs' IS DISTINCT FROM '1'::jsonb
    OR p->'policy'->'overlap_days' IS DISTINCT FROM '7'::jsonb
    OR p->'policy'->'councils' IS NULL
    OR (SELECT count(*) FROM jsonb_object_keys(p->'policy'->'councils'))<>1
    OR NOT (p->'policy'->'councils' ? 'tameside')
    OR p->'policy'->'first_batch' IS DISTINCT FROM
        '{"start":"2026-09-15","end":"2026-09-21","council":"tameside","semantics":"RECEIVED","max_runs":1,"status":"WITHHELD"}'::jsonb
    OR p->'policy'->'expected_stop'->'hard_stop_generation' IS DISTINCT FROM '16'::jsonb
    OR ctl->'intake_periods' ? a
   THEN RAISE EXCEPTION 'TAMESIDE_FIRST_POLICY_BOUND' USING ERRCODE='42501'; END IF;
  ELSE
   IF ctl->'intake_periods'->a->'first_batch' IS DISTINCT FROM
        '{"start":"2026-09-15","end":"2026-09-21","council":"tameside","semantics":"RECEIVED","max_runs":1,"status":"WITHHELD"}'::jsonb
    OR ctl->'intake_periods'->a->'max_runs' IS DISTINCT FROM '1'::jsonb
   THEN RAISE EXCEPTION 'TAMESIDE_FIRST_PERIOD_MISSING' USING ERRCODE='42501'; END IF;
   IF p->>'operation'='intake_capture'
    AND (jsonb_array_length(p->'rows') IS DISTINCT FROM 1
      OR p->'rows'->0->'subject'->>'council' IS DISTINCT FROM 'tameside'
      OR p->'rows'->0->'subject'->>'start' IS DISTINCT FROM '2026-09-15'
      OR p->'rows'->0->'subject'->>'end' IS DISTINCT FROM '2026-09-21'
      OR p->'rows'->0->'subject'->>'semantics' IS DISTINCT FROM 'RECEIVED')
   THEN RAISE EXCEPTION 'TAMESIDE_FIRST_CAPTURE_BOUND' USING ERRCODE='42501'; END IF;
  END IF;
  -- Deliberate permanent fail-close in THIS candidate. No signature,
  -- external manifest, reviewer acceptance or live enablement is claimed.
  RAISE EXCEPTION 'TAMESIDE_FIRST_MANIFEST_WITHHELD' USING ERRCODE='42501';
"""

def _policy_source_bytes():
    return Path("verification/ingestion_storage/intake_policy.py").read_bytes()

def render_inactive_tameside_first_issuer():
    """Pure SQL renderer; neither installs nor grants EXECUTE to anyone."""
    source = _policy_source_bytes()
    expected = hashlib.sha1(
        b"blob " + str(len(source)).encode() + b"\0" + source
    ).hexdigest()
    if expected != PINNED_POLICY_GIT_BLOB:
        raise ValueError("TAMESIDE_FIRST_POLICY_SOURCE_DRIFT")
    text = policy_sql()
    original = "CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception("
    if text.count(original) != 1 or text.count("$register$;") != 1:
        raise ValueError("TAMESIDE_FIRST_ISSUER_INVENTORY")
    function = text[text.index(original):text.index("$register$;") + len("$register$;")]
    if (function.count(_ROLLING) != 1 or function.count(_PERIOD_ANCHOR) != 1
            or function.count(_ENTRY_ANCHOR) != 1):
        raise ValueError("TAMESIDE_FIRST_ISSUER_ANCHOR_DRIFT")
    function = function.replace(original,
        "CREATE OR REPLACE FUNCTION public." + FUNCTION + "(", 1)
    # Refuse legacy Bolton operations before entering inherited fallback.
    function = function.replace(_ENTRY_ANCHOR,
        _ENTRY_GUARD + _ENTRY_ANCHOR, 1)
    function = function.replace(_ROLLING, _HISTORICAL, 1)
    function = function.replace(_PERIOD_ANCHOR, _PERIOD_ANCHOR + "\n" + _GUARD, 1)
    if function.count("TAMESIDE_FIRST_MANIFEST_WITHHELD") != 1:
        raise ValueError("TAMESIDE_FIRST_REFUSAL_REQUIRED")
    # PostgreSQL defaults new functions to PUBLIC EXECUTE; refuse by default.
    # This returned SQL is not wired into installation_script or the live runtime.
    return (function + "\nREVOKE ALL ON FUNCTION public." + FUNCTION +
            "(jsonb) FROM PUBLIC;\n")


# PA-D004 v1.3: ONE reusable source-pinned, uninstalled finite-batch
# renderer, not a new issuer module/function name for each council/week.
# This is a negative-only review artifact: every generated issuer ALWAYS
# refuses source work, even with a plausible manifest or owner-shaped policy.
CAMPAIGN_FUNCTION = "ingestion_register_campaign_once"
CAMPAIGN_MODE = "CAMPAIGN_FINITE_HISTORICAL_V1"


def _canonical_campaign_identity(as_of, council, start, end):
    """One canonical data-only selected period; never a per-batch SQL version."""
    import json
    from verification.discovery.ten_council_offline import select_finite_batch
    selected = select_finite_batch(as_of, council, start, end)
    if selected["current_day_partial"]:
        raise ValueError("CAMPAIGN_FINITE_CURRENT_DAY_PARTIAL")
    row = selected["selected_row"]
    full_sha = selected["selected_payload"]["finite_manifest_sha256"]
    token = hashlib.sha256(json.dumps(
        dict(row=row, full_manifest_sha256=full_sha),
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    return selected, row, "S4_FINITE_" + token, full_sha


def render_inactive_campaign_issuer(as_of, council, start, end):
    """Render a single selected campaign batch; never install or authorise it.

    select_finite_batch reconstructs the canonical 15-Sep-to-execution-date
    manifest, validates council/date alignment, source profile and unchanged
    per-run capacity. The rendered SQL additionally binds the exact selected
    council, date semantics, finite period, full nine-council plan digest and
    STOP generation 16. A digest is not an owner's signed release decision.
    No arbitrary SQL identifier, input date or caller-provided digest is used.
    This artifact is WITHHELD regardless of its inputs and is NOT a live path.
    """
    import json
    selected, row, period_id, full_sha = _canonical_campaign_identity(
        as_of, council, start, end)
    expected_first = '{"start":"2026-09-15","end":"2026-09-21","council":"tameside","semantics":"RECEIVED","max_runs":1,"status":"WITHHELD"}'
    first = json.dumps(dict(start=start, end=end, council=council,
                            semantics=row["semantics"], max_runs=1,
                            status=REVIEW_STATUS), separators=(",", ":"))
    sql = render_inactive_tameside_first_issuer()
    replacements = (
        ("ingestion_register_tameside_first_once", CAMPAIGN_FUNCTION),
        (PERIOD, period_id),
        (expected_first, first),
        ("TAMESIDE_FIRST_HISTORICAL_V1", CAMPAIGN_MODE),
        ("'tameside'", "'" + council + "'"),
        ("2026-09-15", start),
        ("2026-09-21", end),
        ("'RECEIVED'", "'" + row["semantics"] + "'"),
        ("TAMESIDE_FIRST_", "CAMPAIGN_FINITE_"),
    )
    for old, new in replacements:
        if old not in sql:
            raise ValueError("CAMPAIGN_FINITE_TEMPLATE_DRIFT")
        sql = sql.replace(old, new)
    # The ordinary issuer is unchanged; this candidate is a single distinct
    # function whose registration and capture remain permanently denied.
    anchor = "OR p->'policy'->'max_runs' IS DISTINCT FROM '1'::jsonb"
    if sql.count(anchor) != 1:
        raise ValueError("CAMPAIGN_FINITE_POLICY_ANCHOR_DRIFT")
    sql = sql.replace(anchor, anchor + "\n"
        + "    OR p->'policy'->>'campaign_source_plan_sha256' IS DISTINCT FROM '"
        + full_sha + "'", 1)
    if (sql.count("RAISE EXCEPTION 'CAMPAIGN_FINITE_MANIFEST_WITHHELD'") != 1
            or sql.count("CREATE OR REPLACE FUNCTION public."
                         + CAMPAIGN_FUNCTION + "(") != 1
            or "GRANT EXECUTE" in sql
            or "REVOKE ALL ON FUNCTION public." + CAMPAIGN_FUNCTION
                + "(jsonb) FROM PUBLIC;" not in sql
            or "current_database() IS DISTINCT FROM 'postgres'" not in sql):
        raise ValueError("CAMPAIGN_FINITE_INACTIVE_PROOF_FAILED")
    return dict(sql=sql, period=period_id, source_plan_sha256=full_sha,
                row=dict(row), review_status=REVIEW_STATUS,
                collection_authorised=False, installed=False)


# PA-D004 v1.3 production-direction artifact: ONE STABLE SQL BODY, independent
# of the number of councils or historical windows. It is NOT installed and
# deliberately refuses every invocation. The earlier per-batch negative proof
# above is retained as historical test evidence, not an installation pattern.
_STABLE_CAPTURE_DATES = """OR item->'subject'->>'end' IS DISTINCT FROM
       (ctl->'intake_periods'->a->'campaign_batch'->>'end')
    OR item->'subject'->>'start' IS DISTINCT FROM
       (ctl->'intake_periods'->a->'campaign_batch'->>'start')"""
# The frozen normal issuer was Tameside/Manchester-only and treated only
# Manchester as VALIDATED. The general campaign must bind *existing* finite
# source semantics for every profiled council, without changing policy_sql().
_STABLE_COUNCILS_ANCHOR = "OR (e->'councils')-ARRAY['tameside','manchester']<>'{}'::jsonb"
_STABLE_COUNCILS = """OR (e->'councils')-ARRAY['bolton','bury','manchester','oldham',
       'rochdale','salford','stockport','tameside','wigan']<>'{}'::jsonb"""
_STABLE_SEMANTICS_ANCHOR = """OR item->'subject'->>'semantics' IS DISTINCT FROM (CASE WHEN item->'subject'->>'council'='manchester' THEN 'VALIDATED' ELSE 'RECEIVED' END)"""
_STABLE_SEMANTICS = """OR item->'subject'->>'semantics' IS DISTINCT FROM
       (ctl->'intake_periods'->a->'campaign_batch'->>'semantics')"""
_STABLE_OWNER_GUARD = r"""
  -- Owner-sealed finite metadata, not a new SQL body per council/week.
  -- This candidate refuses even if a caller forges the correct-shaped policy.
  IF current_database() IS DISTINCT FROM 'postgres'
     OR (ctl->>'hard_stop_generation')::integer IS DISTINCT FROM 16
     OR ctl->'global_stop' IS DISTINCT FROM 'null'::jsonb
     OR ctl->>'manual_stop' IS NOT NULL
  THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_SCOPE_OR_STOP' USING ERRCODE='42501'; END IF;
  IF p->>'operation'='intake_period' THEN
   e:=p->'policy';
   IF e->>'mode' IS DISTINCT FROM 'CAMPAIGN_FINITE_HISTORICAL_V1'
      OR e->'test_evidence' IS DISTINCT FROM 'false'::jsonb
      OR e->'max_runs' IS DISTINCT FROM '1'::jsonb
      OR e->'overlap_days' IS DISTINCT FROM '7'::jsonb
      OR e->'expected_stop'->'hard_stop_generation' IS DISTINCT FROM '16'::jsonb
      OR e->'campaign_batch' IS NULL
      OR jsonb_typeof(e->'campaign_batch') IS DISTINCT FROM 'object'
      OR NOT (e->'campaign_batch' ?& ARRAY['start','end','council','semantics'])
      OR (e->'campaign_batch')-ARRAY['start','end','council','semantics']<>'{}'::jsonb
      OR jsonb_typeof(e->'campaign_batch'->'start') IS DISTINCT FROM 'string'
      OR jsonb_typeof(e->'campaign_batch'->'end') IS DISTINCT FROM 'string'
      OR jsonb_typeof(e->'campaign_batch'->'council') IS DISTINCT FROM 'string'
      OR jsonb_typeof(e->'campaign_batch'->'semantics') IS DISTINCT FROM 'string'
      OR e->'campaign_batch'->>'start' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}
      OR e->>'campaign_source_plan_sha256' !~ '^[0-9a-f]{64}$'
      OR (SELECT count(*) FROM jsonb_object_keys(e->'councils'))<>1
      OR NOT (e->'councils' ? (e->'campaign_batch'->>'council'))
      OR (e->'campaign_batch'->>'council') NOT IN
         ('bolton','bury','manchester','oldham','rochdale',
          'salford','stockport','tameside','wigan')
      OR (e->'campaign_batch'->>'semantics') IS DISTINCT FROM
         CASE WHEN e->'campaign_batch'->>'council'
             IN ('manchester','rochdale','salford','stockport')
              THEN 'VALIDATED' ELSE 'RECEIVED' END
      OR (e->'campaign_batch'->>'start')::date < '2026-09-15'::date
      OR ((e->'campaign_batch'->>'start')::date-'2026-09-15'::date)%7<>0
      OR (e->'campaign_batch'->>'end')::date-
         (e->'campaign_batch'->>'start')::date <> 6
      OR (e->'campaign_batch'->>'end')::date >=
         (clock_timestamp() AT TIME ZONE 'Europe/London')::date
      OR ctl->'intake_periods' ? a
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_OWNER_BATCH_INVALID'
       USING ERRCODE='42501'; END IF;
  ELSE
   IF ctl->'intake_periods'->a->>'mode' IS DISTINCT FROM
       'CAMPAIGN_FINITE_HISTORICAL_V1'
      OR ctl->'intake_periods'->a->'max_runs' IS DISTINCT FROM '1'::jsonb
      OR ctl->'intake_periods'->a->'campaign_batch' IS NULL
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_PERIOD_MISSING'
       USING ERRCODE='42501'; END IF;
   IF p->>'operation'='intake_capture'
      AND (jsonb_array_length(p->'rows') IS DISTINCT FROM 1
       OR p->'rows'->0->'subject'->>'council' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'council')
       OR p->'rows'->0->'subject'->>'start' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'start')
       OR p->'rows'->0->'subject'->>'end' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'end')
       OR p->'rows'->0->'subject'->>'semantics' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'semantics'))
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_CAPTURE_INVALID'
       USING ERRCODE='42501'; END IF;
  END IF;
  -- No release signature or production owner route has been reviewed.
  -- This unconditional refusal cannot be toggled by environment or policy.
  RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD' USING ERRCODE='42501';
"""


def render_inactive_stable_campaign_issuer():
    """One byte-stable, NEVER-INSTALLED issuer for every finite campaign batch.

    Future review must separately prove the owner registration lifecycle,
    actual production session ACL, and runtime binding. Do not install this
    negative-only SQL and do not treat its syntax proof as operational approval.
    """
    source = _policy_source_bytes()
    if hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source
                    ).hexdigest() != PINNED_POLICY_GIT_BLOB:
        raise ValueError("CAMPAIGN_STABLE_POLICY_SOURCE_DRIFT")
    raw = policy_sql()
    original = "CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception("
    if (raw.count(original) != 1 or raw.count("$register$;") != 1):
        raise ValueError("CAMPAIGN_STABLE_POLICY_INVENTORY_DRIFT")
    function = raw[raw.index(original):raw.index("$register$;") + len("$register$;")]
    if any(function.count(anchor) != 1 for anchor in
           (_ROLLING, _ENTRY_ANCHOR, _PERIOD_ANCHOR,
            _STABLE_COUNCILS_ANCHOR, _STABLE_SEMANTICS_ANCHOR)):
        raise ValueError("CAMPAIGN_STABLE_ISSUER_ANCHOR_DRIFT")
    function = function.replace(original,
        "CREATE OR REPLACE FUNCTION public." + CAMPAIGN_FUNCTION + "(", 1)
    function = function.replace(_ENTRY_ANCHOR,
        _ENTRY_GUARD.replace("TAMESIDE_FIRST_", "CAMPAIGN_STABLE_")
        + _ENTRY_ANCHOR, 1)
    function = function.replace(_ROLLING, _STABLE_CAPTURE_DATES, 1)
    function = function.replace(_STABLE_COUNCILS_ANCHOR,
                                _STABLE_COUNCILS, 1)
    function = function.replace(_STABLE_SEMANTICS_ANCHOR,
                                _STABLE_SEMANTICS, 1)
    function = function.replace(_PERIOD_ANCHOR,
        _PERIOD_ANCHOR + "\n" + _STABLE_OWNER_GUARD, 1)
    result = (function + "\nREVOKE ALL ON FUNCTION public."
              + CAMPAIGN_FUNCTION + "(jsonb) FROM PUBLIC;\n")
    if (result.count("RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD'") != 1
            or "GRANT EXECUTE" in result
            or "ingestion_register_disposable_catchup" in result
            or _ROLLING in result):
        raise ValueError("CAMPAIGN_STABLE_FAIL_CLOSED_DRIFT")
    return result


def prepare_inactive_campaign_owner_batch(as_of, council, start, end):
    """One finite, source-pinned owner REVIEW payload; never registration.

    There is no SQL connection, owner identity, release signature or worker
    execution path here. An actual owner must later seal exactly one reviewed
    batch using separately approved install/rollback and stop CAS authority.
    """
    selected, row, period_id, full_sha = _canonical_campaign_identity(
        as_of, council, start, end)
    stable = render_inactive_stable_campaign_issuer()
    return dict(schema="PA_D004_STABLE_OWNER_PREVIEW_V1",
                period=period_id, campaign_batch=dict(row),
                campaign_source_plan_sha256=full_sha,
                mode=CAMPAIGN_MODE, max_runs=1, overlap_days=7,
                expected_generation=16,
                stable_issuer_sha256=hashlib.sha256(stable.encode()).hexdigest(),
                manifest_status="WITHHELD", installed=False,
                registered=False, live_collection_authorised=False)

      OR e->'campaign_batch'->>'end' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}
      OR e->>'campaign_source_plan_sha256' !~ '^[0-9a-f]{64}$'
      OR (SELECT count(*) FROM jsonb_object_keys(e->'councils'))<>1
      OR NOT (e->'councils' ? (e->'campaign_batch'->>'council'))
      OR (e->'campaign_batch'->>'council') NOT IN
         ('bolton','bury','manchester','oldham','rochdale',
          'salford','stockport','tameside','wigan')
      OR (e->'campaign_batch'->>'semantics') IS DISTINCT FROM
         CASE WHEN e->'campaign_batch'->>'council'
             IN ('manchester','rochdale','salford','stockport')
              THEN 'VALIDATED' ELSE 'RECEIVED' END
      OR (e->'campaign_batch'->>'start')::date < '2026-09-15'::date
      OR ((e->'campaign_batch'->>'start')::date-'2026-09-15'::date)%7<>0
      OR (e->'campaign_batch'->>'end')::date-
         (e->'campaign_batch'->>'start')::date <> 6
      OR (e->'campaign_batch'->>'end')::date >=
         (clock_timestamp() AT TIME ZONE 'Europe/London')::date
      OR ctl->'intake_periods' ? a
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_OWNER_BATCH_INVALID'
       USING ERRCODE='42501'; END IF;
  ELSE
   IF ctl->'intake_periods'->a->>'mode' IS DISTINCT FROM
       'CAMPAIGN_FINITE_HISTORICAL_V1'
      OR ctl->'intake_periods'->a->'max_runs' IS DISTINCT FROM '1'::jsonb
      OR ctl->'intake_periods'->a->'campaign_batch' IS NULL
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_PERIOD_MISSING'
       USING ERRCODE='42501'; END IF;
   IF p->>'operation'='intake_capture'
      AND (jsonb_array_length(p->'rows') IS DISTINCT FROM 1
       OR p->'rows'->0->'subject'->>'council' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'council')
       OR p->'rows'->0->'subject'->>'start' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'start')
       OR p->'rows'->0->'subject'->>'end' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'end')
       OR p->'rows'->0->'subject'->>'semantics' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'semantics'))
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_CAPTURE_INVALID'
       USING ERRCODE='42501'; END IF;
  END IF;
  -- No release signature or production owner route has been reviewed.
  -- This unconditional refusal cannot be toggled by environment or policy.
  RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD' USING ERRCODE='42501';
"""


def render_inactive_stable_campaign_issuer():
    """One byte-stable, NEVER-INSTALLED issuer for every finite campaign batch.

    Future review must separately prove the owner registration lifecycle,
    actual production session ACL, and runtime binding. Do not install this
    negative-only SQL and do not treat its syntax proof as operational approval.
    """
    source = _policy_source_bytes()
    if hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source
                    ).hexdigest() != PINNED_POLICY_GIT_BLOB:
        raise ValueError("CAMPAIGN_STABLE_POLICY_SOURCE_DRIFT")
    raw = policy_sql()
    original = "CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception("
    if (raw.count(original) != 1 or raw.count("$register$;") != 1):
        raise ValueError("CAMPAIGN_STABLE_POLICY_INVENTORY_DRIFT")
    function = raw[raw.index(original):raw.index("$register$;") + len("$register$;")]
    if any(function.count(anchor) != 1 for anchor in
           (_ROLLING, _ENTRY_ANCHOR, _PERIOD_ANCHOR,
            _STABLE_COUNCILS_ANCHOR, _STABLE_SEMANTICS_ANCHOR)):
        raise ValueError("CAMPAIGN_STABLE_ISSUER_ANCHOR_DRIFT")
    function = function.replace(original,
        "CREATE OR REPLACE FUNCTION public." + CAMPAIGN_FUNCTION + "(", 1)
    function = function.replace(_ENTRY_ANCHOR,
        _ENTRY_GUARD.replace("TAMESIDE_FIRST_", "CAMPAIGN_STABLE_")
        + _ENTRY_ANCHOR, 1)
    function = function.replace(_ROLLING, _STABLE_CAPTURE_DATES, 1)
    function = function.replace(_STABLE_COUNCILS_ANCHOR,
                                _STABLE_COUNCILS, 1)
    function = function.replace(_STABLE_SEMANTICS_ANCHOR,
                                _STABLE_SEMANTICS, 1)
    function = function.replace(_PERIOD_ANCHOR,
        _PERIOD_ANCHOR + "\n" + _STABLE_OWNER_GUARD, 1)
    result = (function + "\nREVOKE ALL ON FUNCTION public."
              + CAMPAIGN_FUNCTION + "(jsonb) FROM PUBLIC;\n")
    if (result.count("RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD'") != 1
            or "GRANT EXECUTE" in result
            or "ingestion_register_disposable_catchup" in result
            or _ROLLING in result):
        raise ValueError("CAMPAIGN_STABLE_FAIL_CLOSED_DRIFT")
    return result


def prepare_inactive_campaign_owner_batch(as_of, council, start, end):
    """One finite, source-pinned owner REVIEW payload; never registration.

    There is no SQL connection, owner identity, release signature or worker
    execution path here. An actual owner must later seal exactly one reviewed
    batch using separately approved install/rollback and stop CAS authority.
    """
    selected, row, period_id, full_sha = _canonical_campaign_identity(
        as_of, council, start, end)
    stable = render_inactive_stable_campaign_issuer()
    return dict(schema="PA_D004_STABLE_OWNER_PREVIEW_V1",
                period=period_id, campaign_batch=dict(row),
                campaign_source_plan_sha256=full_sha,
                mode=CAMPAIGN_MODE, max_runs=1, overlap_days=7,
                expected_generation=16,
                stable_issuer_sha256=hashlib.sha256(stable.encode()).hexdigest(),
                manifest_status="WITHHELD", installed=False,
                registered=False, live_collection_authorised=False)

      OR e->'campaign_source_plan_sha256' IS NULL
      OR e->>'campaign_source_plan_sha256' !~ '^[0-9a-f]{64}$'
      OR (SELECT count(*) FROM jsonb_object_keys(e->'councils'))<>1
      OR NOT (e->'councils' ? (e->'campaign_batch'->>'council'))
      OR (e->'campaign_batch'->>'council') NOT IN
         ('bolton','bury','manchester','oldham','rochdale',
          'salford','stockport','tameside','wigan')
      OR (e->'campaign_batch'->>'semantics') IS DISTINCT FROM
         CASE WHEN e->'campaign_batch'->>'council'
             IN ('manchester','rochdale','salford','stockport')
              THEN 'VALIDATED' ELSE 'RECEIVED' END
      OR (e->'campaign_batch'->>'start')::date < '2026-09-15'::date
      OR ((e->'campaign_batch'->>'start')::date-'2026-09-15'::date)%7<>0
      OR (e->'campaign_batch'->>'end')::date-
         (e->'campaign_batch'->>'start')::date <> 6
      OR (e->'campaign_batch'->>'end')::date >=
         (clock_timestamp() AT TIME ZONE 'Europe/London')::date
      OR ctl->'intake_periods' ? a
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_OWNER_BATCH_INVALID'
       USING ERRCODE='42501'; END IF;
  ELSE
   IF ctl->'intake_periods'->a->>'mode' IS DISTINCT FROM
       'CAMPAIGN_FINITE_HISTORICAL_V1'
      OR ctl->'intake_periods'->a->'max_runs' IS DISTINCT FROM '1'::jsonb
      OR ctl->'intake_periods'->a->'campaign_batch' IS NULL
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_PERIOD_MISSING'
       USING ERRCODE='42501'; END IF;
   IF p->>'operation'='intake_capture'
      AND (jsonb_array_length(p->'rows') IS DISTINCT FROM 1
       OR p->'rows'->0->'subject'->>'council' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'council')
       OR p->'rows'->0->'subject'->>'start' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'start')
       OR p->'rows'->0->'subject'->>'end' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'end')
       OR p->'rows'->0->'subject'->>'semantics' IS DISTINCT FROM
          (ctl->'intake_periods'->a->'campaign_batch'->>'semantics'))
   THEN RAISE EXCEPTION 'CAMPAIGN_STABLE_CAPTURE_INVALID'
       USING ERRCODE='42501'; END IF;
  END IF;
  -- No release signature or production owner route has been reviewed.
  -- This unconditional refusal cannot be toggled by environment or policy.
  RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD' USING ERRCODE='42501';
"""


def render_inactive_stable_campaign_issuer():
    """One byte-stable, NEVER-INSTALLED issuer for every finite campaign batch.

    Future review must separately prove the owner registration lifecycle,
    actual production session ACL, and runtime binding. Do not install this
    negative-only SQL and do not treat its syntax proof as operational approval.
    """
    source = _policy_source_bytes()
    if hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source
                    ).hexdigest() != PINNED_POLICY_GIT_BLOB:
        raise ValueError("CAMPAIGN_STABLE_POLICY_SOURCE_DRIFT")
    raw = policy_sql()
    original = "CREATE OR REPLACE FUNCTION public.ingestion_register_bolton_exception("
    if (raw.count(original) != 1 or raw.count("$register$;") != 1):
        raise ValueError("CAMPAIGN_STABLE_POLICY_INVENTORY_DRIFT")
    function = raw[raw.index(original):raw.index("$register$;") + len("$register$;")]
    if any(function.count(anchor) != 1 for anchor in
           (_ROLLING, _ENTRY_ANCHOR, _PERIOD_ANCHOR,
            _STABLE_COUNCILS_ANCHOR, _STABLE_SEMANTICS_ANCHOR)):
        raise ValueError("CAMPAIGN_STABLE_ISSUER_ANCHOR_DRIFT")
    function = function.replace(original,
        "CREATE OR REPLACE FUNCTION public." + CAMPAIGN_FUNCTION + "(", 1)
    function = function.replace(_ENTRY_ANCHOR,
        _ENTRY_GUARD.replace("TAMESIDE_FIRST_", "CAMPAIGN_STABLE_")
        + _ENTRY_ANCHOR, 1)
    function = function.replace(_ROLLING, _STABLE_CAPTURE_DATES, 1)
    function = function.replace(_STABLE_COUNCILS_ANCHOR,
                                _STABLE_COUNCILS, 1)
    function = function.replace(_STABLE_SEMANTICS_ANCHOR,
                                _STABLE_SEMANTICS, 1)
    function = function.replace(_PERIOD_ANCHOR,
        _PERIOD_ANCHOR + "\n" + _STABLE_OWNER_GUARD, 1)
    result = (function + "\nREVOKE ALL ON FUNCTION public."
              + CAMPAIGN_FUNCTION + "(jsonb) FROM PUBLIC;\n")
    if (result.count("RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD'") != 1
            or "GRANT EXECUTE" in result
            or "ingestion_register_disposable_catchup" in result
            or _ROLLING in result):
        raise ValueError("CAMPAIGN_STABLE_FAIL_CLOSED_DRIFT")
    return result


def prepare_inactive_campaign_owner_batch(as_of, council, start, end):
    """One finite, source-pinned owner REVIEW payload; never registration.

    There is no SQL connection, owner identity, release signature or worker
    execution path here. An actual owner must later seal exactly one reviewed
    batch using separately approved install/rollback and stop CAS authority.
    """
    selected, row, period_id, full_sha = _canonical_campaign_identity(
        as_of, council, start, end)
    stable = render_inactive_stable_campaign_issuer()
    return dict(schema="PA_D004_STABLE_OWNER_PREVIEW_V1",
                period=period_id, campaign_batch=dict(row),
                campaign_source_plan_sha256=full_sha,
                mode=CAMPAIGN_MODE, max_runs=1, overlap_days=7,
                expected_generation=16,
                stable_issuer_sha256=hashlib.sha256(stable.encode()).hexdigest(),
                manifest_status="WITHHELD", installed=False,
                registered=False, live_collection_authorised=False)
