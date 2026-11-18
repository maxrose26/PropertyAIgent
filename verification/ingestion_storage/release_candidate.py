"""Pure offline compilation of the existing release and campaign boundaries.

No connection, installation, runtime activation or authority is supplied here.
The input must be an independently reviewed, exact post-recovery manifest and
policy. In particular this compiler never manufactures post-recovery hashes.
"""
import hashlib
import json
import math
import re
from pathlib import Path

from . import inactive_tameside_first_issuer as issuer

RELEASE_PATH = Path(__file__).with_name('inactive_shared_stop_release_v1.sql')
RELEASE_SHA = 'e6ada86a9e55521f9812c2064d5a60c3ba53bc5e0f6e508ca4a64bdca39a034a'
BATCH = dict(council='tameside', semantics='RECEIVED', start='2026-09-15', end='2026-09-21')
FOLLOW_ON = ('manchester', 'bolton', 'tameside', 'bury', 'oldham', 'rochdale',
             'salford', 'stockport', 'trafford', 'wigan')


def installed_campaign_sql(period, policy, as_of):
    """Common owner/runtime calculation of the exact policy-bound function.

    Fixed disposable projection changes fixture data/database identity only;
    it cannot install into postgres or qualify synthetic sources as live.
    The existing live code gates still apply at both calling entry points.
    """
    import copy
    projection = policy.get('test_evidence') is True
    target = copy.deepcopy(policy)
    for key in ('days', 'registered_at'):
        target.pop(key, None)
    if projection:
        if target.get('route') != 'DISPOSABLE' or target.get('hostaddr') is not None:
            raise ValueError('CAMPAIGN_DISPOSABLE_ROUTE')
        target.update(test_evidence=False, route='DIRECT', hostaddr='192.0.2.1')
    source = render_campaign(as_of=as_of, period=period, policy=target,
                             release_manifest_sha256=target['release_manifest_sha256'])
    if projection:
        actual = copy.deepcopy(policy)
        for key in ('days', 'registered_at'):
            actual.pop(key, None)
        source = source.replace(_literal(target), _literal(actual))
        source = source.replace("e->'test_evidence' IS DISTINCT FROM 'false'::jsonb",
                                "e->'test_evidence' IS DISTINCT FROM 'true'::jsonb")
        source = source.replace("current_database() IS DISTINCT FROM 'postgres'",
                                "current_database() IS DISTINCT FROM 'ingestion_provisioning_test'")
    return source


def _literal(value):
    return "'" + json.dumps(value, sort_keys=True, separators=(',', ':'),
                            allow_nan=False).replace("'", "''") + "'::jsonb"


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)


def render_release(manifest, *, expires_at):
    """Keep every lock/CAS/ACL check; bind seven exact dispositions and expiry.

    This is an execution candidate, not evidence that approval was granted.
    manifest_binding_sha256 uses PostgreSQL jsonb canonical text, as before.
    """
    source = RELEASE_PATH.read_text()
    if hashlib.sha256(source.encode()).hexdigest() != RELEASE_SHA:
        raise ValueError('RELEASE_TEMPLATE_DRIFT')
    prior = json.loads(re.search(r"expected_prior jsonb := '(\{.*?\})'::jsonb;",
                                source, re.S).group(1))
    if (type(manifest) is not dict or
            manifest.get('release_status') != 'ACCEPTED_FOR_OPERATIONAL_RELEASE' or
            not all(_sha(manifest.get(k)) for k in
                    ('review_sha256', 'manifest_binding_sha256', 'expected_controller_sha256')) or
            type(manifest.get('effects')) is not list or len(manifest['effects']) != 7 or
            {e.get('key') for e in manifest['effects']} != set(prior)):
        raise ValueError('RELEASE_EXACT_MANIFEST_REQUIRED')
    for effect in manifest['effects']:
        if (effect.get('prior_sha256') != prior[effect['key']] or
                not _sha(effect.get('work_sha256')) or not _sha(effect.get('attempts_sha256')) or
                effect.get('coverage') != 'UNKNOWN' or
                effect.get('source_or_write_replay_authorised') is not False):
            raise ValueError('RELEASE_EFFECT_BINDING_REQUIRED')
    if type(expires_at) not in (int, float) or not math.isfinite(expires_at) or expires_at <= 0:
        raise ValueError('RELEASE_FINITE_EXPIRY_REQUIRED')
    if manifest.get('expires_at') != expires_at:
        raise ValueError('RELEASE_EXPIRY_NOT_MANIFEST_BOUND')
    empty = "'{\"release_status\":\"WITHHELD\",\"review_sha256\":null,\"effects\":[]}'::jsonb"
    if source.count(empty) != 1:
        raise ValueError('RELEASE_MANIFEST_ANCHOR_DRIFT')
    source = source.replace(empty, _literal(manifest), 1)
    anchor = '  -- Sole permitted write:'
    guard = """  IF extract(epoch FROM clock_timestamp()) >= (review_manifest->>'expires_at')::double precision
  THEN RAISE EXCEPTION 'OWNER_RELEASE_EXPIRED'; END IF;
"""
    if source.count(anchor) != 1:
        raise ValueError('RELEASE_WRITE_ANCHOR_DRIFT')
    return source.replace(anchor, guard + anchor, 1)


def render_campaign(*, as_of, period, policy, release_manifest_sha256):
    """Single stable issuer with exact policy and accepted release binding.

    All-ten planning remains separate. Only this Tameside batch is admissible;
    changing council/window/pins/expiry requires a different reviewed artifact.
    """
    if not _sha(release_manifest_sha256) or policy.get('campaign_batch') != BATCH:
        raise ValueError('CAMPAIGN_EXACT_TAMESIDE_RELEASE_REQUIRED')
    issuer.review_inactive_campaign_owner_policy(
        as_of, **{k: BATCH[k] for k in ('council', 'start', 'end')},
        period=period, policy=policy, observed_stop=policy['expected_stop'],
        execution_binding=policy['execution_binding'])
    source = issuer.render_inactive_stable_campaign_issuer()
    refusal = "  RAISE EXCEPTION 'CAMPAIGN_STABLE_MANIFEST_WITHHELD' USING ERRCODE='42501';"
    if source.count(refusal) != 1:
        raise ValueError('CAMPAIGN_REFUSAL_ANCHOR_DRIFT')
    # Data equality includes expiry, source qualification, screening, route,
    # full execution binding and one-run constraint, not just a plausible SHA.
    guard = """  IF a IS DISTINCT FROM PERIOD
     OR ctl->'owner_shared_stop_release'->>'manifest_binding_sha256' IS DISTINCT FROM RELEASE
     OR (CASE WHEN p->>'operation'='intake_period' THEN p->'policy'
              ELSE ctl->'intake_periods'->a END) IS DISTINCT FROM POLICY
  THEN RAISE EXCEPTION 'CAMPAIGN_REVIEWED_BINDING_CHANGED' USING ERRCODE='42501'; END IF;
  IF p->>'operation'='intake_period' AND EXISTS (
     SELECT 1 FROM public.ingestion_work_items WHERE state='CLAIMED')
  THEN RAISE EXCEPTION 'CAMPAIGN_UNRELATED_CLAIMED'; END IF;
""".replace('PERIOD', "'" + period + "'").replace('RELEASE', "'" + release_manifest_sha256 + "'").replace('POLICY', _literal(policy))
    # The existing issuer appends operational days/runs to the stored policy.
    # Compare the immutable reviewed subset; reject unknown extra input keys
    # on initial registration via complete equality above.
    guard = guard.replace("ELSE ctl->'intake_periods'->a END",
                          "ELSE (ctl->'intake_periods'->a)-ARRAY['days','registered_at'] END")
    source = source.replace(refusal, guard, 1)
    # Consistent table-before-controller ordering, both for the owner's
    # preflight and for direct registration. No unrelated claim can race the
    # census before the period is committed.
    lock = 'LOCK TABLE public.ingestion_work_items, public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE;\n  '
    preflight = '  SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items'
    if source.count(preflight) != 2:
        raise ValueError('CAMPAIGN_LOCK_INVENTORY_DRIFT')
    source = source.replace(preflight, '  ' + lock + preflight.lstrip(), 1)
    second = source.index(preflight, source.index('RETURN jsonb_build_object'))
    source = source[:second] + ("  IF p->>'operation'='intake_period' THEN " + lock +
                              'END IF;\n') + source[second:]
    from .campaign_private_finish import adapt
    return adapt(source)


def render_campaign_install(**kwargs):
    from .inactive_owner_writer_install import render_inactive_stable_campaign_owner_install
    old = issuer.render_inactive_stable_campaign_issuer()
    source = render_inactive_stable_campaign_owner_install()
    if source.count(old) != 1:
        raise ValueError('CAMPAIGN_INSTALL_ANCHOR_DRIFT')
    compiled = render_campaign(**kwargs)
    name = 'public.' + issuer.CAMPAIGN_FUNCTION + '(jsonb)'
    # #213's actual recovery baseline explicitly requires no schema CREATE
    # for ingestion_storage_owner. Do not assume the fixture's broad grant.
    source = source.replace(
        " OR NOT pg_catalog.has_schema_privilege('ingestion_storage_owner','public','CREATE')",
        " OR pg_catalog.has_schema_privilege('ingestion_storage_owner','public','CREATE')")
    source = source.replace('SET LOCAL ROLE ingestion_storage_owner;',
        'GRANT CREATE ON SCHEMA public TO ingestion_storage_owner;\nSET LOCAL ROLE ingestion_storage_owner;', 1)
    source = source.replace('RESET ROLE;', """RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM ingestion_storage_owner;
DO $schema_restored$ BEGIN
 IF pg_catalog.has_schema_privilege('ingestion_storage_owner','public','CREATE')
 THEN RAISE EXCEPTION 'CAMPAIGN_INSTALL_SCHEMA_NOT_RESTORED'; END IF;
END $schema_restored$;""", 1)
    stopped = """DO $candidate_stopped_install$
DECLARE ctl jsonb;
BEGIN
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items
  WHERE key=repeat('0',64) FOR UPDATE;
 IF ctl->'hard_stop_generation' IS DISTINCT FROM '15'::jsonb
    OR ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
    OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
    OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
    OR ctl ? 'intake_run'
    OR EXISTS (SELECT 1 FROM public.ingestion_work_items WHERE state='CLAIMED'
               OR phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN')
 THEN RAISE EXCEPTION 'CAMPAIGN_INSTALL_NOT_STOPPED'; END IF;
END $candidate_stopped_install$;
"""
    # The dormant worker capability must be installed here, not supplied by a
    # fixture. Login access remains controlled by the existing finite lifecycle.
    return source.replace(old, stopped + compiled + '\nGRANT EXECUTE ON FUNCTION ' + name + ' TO postgres, ingestion_worker;\n', 1)


def render_dispositions(manifest):
    """Proposed six-row preservation transition, while stopped at generation15.

    Original work/attempt compound fingerprints must match under table locks.
    Original rows are saved verbatim in checkpoints; attempts/evidence are never
    changed. The seventh item (Bolton recovery) is handled solely by #213.
    A compiler return does not constitute an operational owner acceptance.
    """
    from .inactive_owner_writer_install import PRELUDE, EPILOGUE
    source = RELEASE_PATH.read_text()
    if hashlib.sha256(source.encode()).hexdigest() != RELEASE_SHA:
        raise ValueError('DISPOSITION_TEMPLATE_DRIFT')
    prior = json.loads(re.search(r"expected_prior jsonb := '(\{.*?\})'::jsonb;", source, re.S).group(1))
    if (type(manifest) is not dict or manifest.get('prior_fingerprints') != prior or
            not _sha(manifest.get('review_sha256')) or
            not isinstance(manifest.get('expires_at'), (int, float)) or
            not math.isfinite(manifest['expires_at']) or
            manifest.get('owner_risk_ref') != 'https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-6950521818' or
            manifest.get('review_risk_ref') != 'https://github.com/maxrose26/PropertyAIgent/issues/214#issuecomment-6951000467'):
        raise ValueError('DISPOSITION_EXACT_REVIEW_REQUIRED')
    canonical = {k: v for k, v in manifest.items() if k != 'review_sha256'}
    if hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'),
                                allow_nan=False).encode()).hexdigest() != manifest['review_sha256']:
        raise ValueError('DISPOSITION_MANIFEST_DIGEST')
    # Seven identities include the separately handled Bolton recovery. Its
    # original fingerprint is not incorrectly applied to its changed row.
    # The release transaction independently verifies that recovery receipt.
    body = """
LOCK TABLE public.ingestion_work_items, public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.ingestion_run_evidence IN SHARE MODE;
DO $preserve_dispositions$
DECLARE ctl jsonb; w public.ingestion_work_items%ROWTYPE; attempts jsonb;
        actual text; original jsonb; manifest jsonb := MANIFEST;
BEGIN
 SELECT outcome::jsonb INTO STRICT ctl FROM public.ingestion_work_items
  WHERE key=repeat('0',64) FOR UPDATE;
 IF ctl->'hard_stop_generation' IS DISTINCT FROM '15'::jsonb
  OR ctl->'global_stop' IS DISTINCT FROM '{"reason":"DAILY_INTAKE_SHARED_FAILURE"}'::jsonb
  OR ctl->>'manual_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
  OR ctl->>'last_hard_stop' IS DISTINCT FROM 'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP'
  OR ctl ? 'intake_run'
  OR extract(epoch FROM clock_timestamp()) >= (manifest->>'expires_at')::double precision
  OR EXISTS (SELECT 1 FROM public.ingestion_work_items WHERE state IN ('CLAIMED','PERSISTENCE_UNCERTAIN')
             OR phase IN ('SOURCE_INTENT','WRITE_INTENT'))
 THEN RAISE EXCEPTION 'DISPOSITION_STOP_OR_ACTIVITY_CHANGED'; END IF;
 FOR w IN SELECT * FROM public.ingestion_work_items
          WHERE key IN (SELECT jsonb_object_keys(manifest->'prior_fingerprints'))
            AND key<>'d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
          ORDER BY key FOR UPDATE LOOP
  SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY a.fence),'[]'::jsonb)
   INTO attempts FROM public.ingestion_work_attempts a WHERE a.work_key=w.key;
  original:=to_jsonb(w);
  actual:=encode(sha256(convert_to(jsonb_build_object('work',original,'attempts',attempts)::text,'UTF8')),'hex');
  IF actual IS DISTINCT FROM manifest->'prior_fingerprints'->>w.key
   OR w.state IS DISTINCT FROM 'SAFETY_BLOCKED' OR w.phase IS DISTINCT FROM 'RECOVERED'
   OR w.owner IS NOT NULL OR w.lease_until IS NOT NULL OR w.fence<>2
   OR jsonb_array_length(attempts)<>1
   OR attempts->0->>'phase' IS DISTINCT FROM 'RECOVERED'
   OR attempts->0->>'finished_at' IS NULL
  THEN RAISE EXCEPTION 'DISPOSITION_ORIGINAL_DRIFT'; END IF;
  UPDATE public.ingestion_work_items SET state='DEFERRED',phase='FINISHED',
   reason='REVIEWED_PRESERVE_NO_REPLAY',next_action='PRESERVE_HISTORY_NO_REPLAY',
   checkpoint=jsonb_build_object('review_sha256',manifest->>'review_sha256',
    'reviewer_evidence',manifest->>'review_risk_ref','original_work',original,
    'original_attempts',attempts,'prior_sha256',actual,'coverage','UNKNOWN',
    'owner_risk_ref',manifest->>'owner_risk_ref')::json,
   outcome=jsonb_build_object('outcome','REVIEW_ACCEPTED_PRESERVE_NO_REPLAY',
    'coverage','UNKNOWN','source_or_write_replay_authorised',false,
    'original_outcome',original->'outcome')::json WHERE key=w.key;
 END LOOP;
 IF (SELECT count(*) FROM public.ingestion_work_items
     WHERE key IN (SELECT jsonb_object_keys(manifest->'prior_fingerprints'))
       AND key<>'d9d8d667eef5fb012c74cdd28f5c55c6b577f749e7dc69d9179a6c032853d252'
       AND state='DEFERRED' AND phase='FINISHED'
       AND checkpoint::jsonb->>'review_sha256'=manifest->>'review_sha256')<>6
 THEN RAISE EXCEPTION 'DISPOSITION_INVENTORY'; END IF;
END $preserve_dispositions$;
""".replace('MANIFEST', _literal(manifest))
    # Preservation changes data only. Requiring CREATE WITH GRANT OPTION here
    # would invent an installation privilege prerequisite for a DML operation.
    return data_owner_prelude() + body + EPILOGUE


def data_owner_prelude():
    from .inactive_owner_writer_install import PRELUDE
    start='DO $owner_schema_preflight$'
    end='END $owner_schema_preflight$;\n'
    if PRELUDE.count(start)!=1 or PRELUDE.count(end)!=1:
        raise ValueError('DISPOSITION_CAPABILITY_TEMPLATE_DRIFT')
    return PRELUDE[:PRELUDE.index(start)]+PRELUDE[PRELUDE.index(end)+len(end):]


def manifest_from_readback(connection, proposal, *, operational_review_ref):
    """Seal observed post-recovery hashes, never predict them from old hashes.

    Caller supplies a FRESH read-only transaction after the approved mutations.
    This read is part of the proposed sequence, not an inspection authorisation.
    The release transaction independently rechecks every hash under locks.
    """
    render_dispositions(proposal)  # validate frozen prior identities and decision refs
    if not re.fullmatch(r'https://github.com/maxrose26/PropertyAIgent/pull/227#issuecomment-[0-9]+', operational_review_ref):
        raise ValueError('RELEASE_OPERATIONAL_REVIEW_REF')
    if connection.execute('SHOW transaction_read_only').fetchone() != ('on',):
        raise ValueError('RELEASE_READBACK_MUST_BE_READ_ONLY')
    rows=connection.execute("""SELECT w.key,
      encode(sha256(convert_to(to_jsonb(w)::text,'UTF8')),'hex'),
      (SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(a) ORDER BY fence)::text,'[]'),'UTF8')),'hex')
       FROM public.ingestion_work_attempts a WHERE a.work_key=w.key)
      FROM public.ingestion_work_items w WHERE key=ANY(%s) ORDER BY key""",
      (sorted(proposal['prior_fingerprints']),)).fetchall()
    if [r[0] for r in rows] != sorted(proposal['prior_fingerprints']):
        raise ValueError('RELEASE_READBACK_INVENTORY')
    effects=[]
    for key,work_sha,attempts_sha in rows:
        effect=dict(key=key,prior_sha256=proposal['prior_fingerprints'][key],
                    work_sha256=work_sha,attempts_sha256=attempts_sha,
                    release_containment='ACCEPT',coverage='UNKNOWN',
                    source_or_write_replay_authorised=False,
                    source_decision_scope='EXPLICIT_OPERATIONAL_RELEASE_NOT_PRESERVATION_ONLY',
                    review_ref=operational_review_ref)
        if key.startswith(('21330c06','dc8ae276')):
            effect.update(effect_state='UNKNOWN',risk_acceptance='OWNER_AND_DISTINCT_REVIEW_EXPLICIT_UNKNOWN',
                risk_boundary='NO_REPLAY_ONE_GENERATION_NO_COVERAGE',owner_decision_ref=proposal['owner_risk_ref'])
        effects.append(effect)
    controller=connection.execute("SELECT encode(sha256(convert_to(outcome::jsonb::text,'UTF8')),'hex') FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()
    if not controller: raise ValueError('RELEASE_READBACK_CONTROLLER')
    result=dict(release_status='ACCEPTED_FOR_OPERATIONAL_RELEASE',review_sha256=proposal['review_sha256'],
                expected_controller_sha256=controller[0],effects=effects,expires_at=proposal['expires_at'])
    result['manifest_binding_sha256']=connection.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(result),)).fetchone()[0]
    render_release(result,expires_at=proposal['expires_at'])
    return result
