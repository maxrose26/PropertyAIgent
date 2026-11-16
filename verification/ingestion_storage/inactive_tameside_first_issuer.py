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
