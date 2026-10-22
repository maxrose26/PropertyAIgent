"""Policy v6: ONE narrowly named, screening-only allowance for the retained Bolton capture, derived MECHANICALLY from the installed policy v5 (docs/design/ingestion-window-demonstration-20261023/policy-window-allowance.sql).

OFFLINE ONLY: nothing here installs or registers anything. v6 changes exactly the two policy functions v5 changes (ingestion_bolton_allowed, ingestion_register_bolton_exception), by exactly the substitutions below, each of
which must match once. It adds ONE name; it is not a reusable mechanism and not a cap increase:

* the stop predicate admits the name only in the exact generation-3 stop state (manual stop and last hard stop IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE, digest ff287601...f39f7b), exactly as for the window names;
* the scope is the retained window (Bolton RECEIVED 2026-09-28 to 2026-10-04) and nothing else;
* the cap of three exception keys is exempted for that one name, and only at generation 3;
* an additional exact-grant check applies to that name only: the retained capture key, a COMPLETE LISTING_RECEIPT_V1 root, source_calls = 0, writes = 0, exactly one listed screening configuration, exactly 59
  bound keys and exactly the four contracts and the binding mix of the registered retained world (1 capture root, 10 batch items, 24 v1 and 24 v3 screening items).

Generation, stops, consumed names and every historical entry are untouched; a name that already exists can never be registered again."""
from pathlib import Path

from app.ingestion.ledger import digest
from app.ingestion.listing_screening import RULE_V3, ScreeningRule

from verification.ingestion_storage.operational_owner import GENERATION3_STOP, GENERATION3_WINDOW_POLICY

NAME = 'AUTHORISE_INGESTION_BOLTON_SCREENING_V3_RETAINED_WINDOW_ONCE_20261030_SCREEN'      # the date is a namespace identifier
CAPTURE_KEY = 'd1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545'
WINDOW_CAPTURE = 'AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_CAPTURE'
WINDOW_SCREEN = 'AUTHORISE_INGESTION_BOLTON_WINDOW_DEMONSTRATION_ONCE_20261023_SCREEN'
IDOX = GENERATION3_STOP['manual_stop']
G3_SHA = GENERATION3_STOP['stop_state_sha256']
CONFIG_SHA = digest(ScreeningRule(RULE_V3, unit_threshold=10, link_related=False).config())      # the one frozen v3 configuration (the hosted half freezes the same one)
EXPECTED_KEYS = 59
EXPECTED_CONTRACTS = ['bolton-received-idox-coordinator-v1', 'listing-batch-v1', 'listing-screen-v1', 'listing-screen-v3']      # sorted, as the owner's grant builds them
POLICY_FILE = Path('docs/design/ingestion-screening-v3-activation-20261030/policy-screening-v3-allowance.sql')

HEADER = """-- POLICY V6 (screening-v3 retained-window assessment). Derived MECHANICALLY from policy v5 (docs/design/ingestion-window-demonstration-20261023/policy-window-allowance.sql); tests/test_ingestion_screening_v3_policy.py regenerates it and requires byte equality.
-- v5 admitted the two window-demonstration names at generation 3; both are consumed and invalidated. v6 admits, in the exact generation-3 stop state ONLY (manual stop and last hard stop both %(idox)s, stop-state digest %(sha)s)
-- and for the ONE exact retained scope (Bolton RECEIVED 2026-09-28 to 2026-10-04), exactly ONE more named allowance:
--   %(name)s   (screening only: source_calls=0, writes=0)
-- It exempts only that name from the cap of three exception keys, only at generation 3, and applies an exact-grant check to that name alone (retained capture key, COMPLETE receipt root, one listed configuration, 59 bound keys, the four contracts).
-- The generation is never reset, no stop is changed, no historical grant or exception is touched, and a name that already exists can never be registered again. Preparation only; no production release.
""" % dict(idox=IDOX, sha=G3_SHA, name=NAME)

EXACT_CHECK = """ IF a = '%(name)s' AND (g->>'capture_key' IS DISTINCT FROM '%(key)s' OR root.state<>'COMPLETE' OR root.checkpoint::jsonb->>'kind' IS DISTINCT FROM 'LISTING_RECEIPT_V1'
  OR (g->>'source_calls')::integer IS DISTINCT FROM 0 OR (g->>'writes')::integer IS DISTINCT FROM 0
  OR jsonb_typeof(g->'screening_configs') IS DISTINCT FROM 'array' OR jsonb_array_length(g->'screening_configs')<>1 OR g->'screening_configs' IS DISTINCT FROM '["%(cfg)s"]'::jsonb
  OR (SELECT count(*) FROM jsonb_each(g->'bindings'))<>%(keys)d
  OR jsonb_array_length(g->'keys')<>%(keys)d OR g->'contracts' IS DISTINCT FROM '%(contracts)s'::jsonb
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='DISCOVERY')<>1
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='LISTING_METADATA' AND x.value->>'contract'='listing-batch-v1')<>10
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='SCREENING' AND x.value->>'contract'='listing-screen-v1')<>24
  OR (SELECT count(*) FROM jsonb_each(g->'bindings') x WHERE x.value->>'task'='SCREENING' AND x.value->>'contract'='listing-screen-v3')<>24) THEN RAISE EXCEPTION 'EXACT_SCREENING_V3_ALLOWANCE'; END IF;
""" % dict(name=NAME, key=CAPTURE_KEY, keys=EXPECTED_KEYS, cfg=CONFIG_SHA, contracts='["' + '","'.join(EXPECTED_CONTRACTS) + '"]')


def derive(v5):
    """policy v6 text from policy v5 text; every substitution site must match exactly once."""
    out = v5[v5.index('BEGIN;'):]

    def swap(old, new):
        nonlocal out
        if out.count(old) != 1:
            raise ValueError('SUBSTITUTION_SITE_NOT_UNIQUE:' + old[:80])
        out = out.replace(old, new)
    # 1. the stop predicate in ingestion_bolton_allowed: one more branch, the same generation-3 conditions
    swap("  AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'))\n AND subject->>'council'='bolton'" % (IDOX, IDOX),
         "  AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s')\n  OR (authority = '%s'\n   AND (ctl->>'hard_stop_generation')::integer=3 AND (ctl->'bolton_exceptions'->authority->>'hard_stop_generation')::integer=3\n   AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'))\n AND subject->>'council'='bolton'" % (IDOX, IDOX, NAME, IDOX, IDOX))
    # 2. the retained window is the scope of the new name too (the same scope as the window names)
    swap("sc:=CASE WHEN a IN ('%s','%s') THEN" % (WINDOW_CAPTURE, WINDOW_SCREEN), "sc:=CASE WHEN a IN ('%s','%s','%s') THEN" % (WINDOW_CAPTURE, WINDOW_SCREEN, NAME))
    # 3. the stop-baseline predicate in ingestion_register_bolton_exception: the same exact generation-3 baseline
    swap("   AND p->>'stop_checkpoint_sha256'='%s',false))      -- NULL" % G3_SHA,
         "   AND p->>'stop_checkpoint_sha256'='%s',false)\n  OR coalesce(a = '%s' AND (ctl->>'hard_stop_generation')::integer=3 AND (p->>'hard_stop_generation')::integer=3\n   AND ctl->>'manual_stop'='%s' AND ctl->>'last_hard_stop'='%s'\n   AND p->>'stop_checkpoint_sha256'='%s',false))      -- NULL" % (G3_SHA, NAME, IDOX, IDOX, G3_SHA))
    # 4. the cap exemption: this one name, at generation 3 only
    swap("OR (a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=3),false))" % (WINDOW_CAPTURE, WINDOW_SCREEN),
         "OR (a IN ('%s','%s') AND (ctl->>'hard_stop_generation')::integer=3) OR (a = '%s' AND (ctl->>'hard_stop_generation')::integer=3),false))" % (WINDOW_CAPTURE, WINDOW_SCREEN, NAME))
    # 5. the exact-grant check for this name alone, after the root capture has been read
    anchor = "THEN RAISE EXCEPTION 'EXECUTION_AND_CAPTURE_BINDING'; END IF;\n"
    swap(anchor, anchor + EXACT_CHECK)
    return HEADER + out


def v5_text():
    return GENERATION3_WINDOW_POLICY.read_bytes().decode('utf-8').replace('\r\n', '\n')


def v6_text():
    return derive(v5_text())
