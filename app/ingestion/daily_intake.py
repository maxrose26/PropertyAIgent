"""Intake-only connection using existing capture, batches and restricted SQL.

No credential lookup, grant issuance, source transport, admission or scheduler.
The release supplies an authorised, supervised collector and existing registration
callback. Production bootstrap is deliberately absent until an existing mechanism
can express rolling Render authority. These functions do not confer that authority.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .ledger import Denied, bounded, digest
from .listing_screening import assessment_identity, routing_of, identity_admission_eligible

MAX_SLOTS = 3  # existing demonstrated package shape, not nine-council capacity


def current_windows(now, councils, *, overlap_days=7):
    """Current intake first; missed historical intervals stay separate gaps.

    Source dates are not public-availability dates. This does not declare recall
    or freshness, nor refresh decisions on older applications.
    """
    from verification.discovery.finite_acceptance import SEMANTICS
    if now.tzinfo is None or type(overlap_days) is not int or not 1 <= overlap_days <= 28:
        raise Denied('INTAKE_DATE_BOUND')
    councils=tuple(councils)
    if not 1 <= len(councils) <= MAX_SLOTS or len(set(councils)) != len(councils):
        raise Denied('INTAKE_SLOT_BOUND')
    if any(c not in SEMANTICS or c == 'trafford' for c in councils):
        raise Denied('INTAKE_COUNCIL')
    end=now.astimezone(ZoneInfo('Europe/London')).date()-timedelta(days=1)
    return [dict(council=c,semantics=SEMANTICS[c],start=(end-timedelta(days=overlap_days-1)).isoformat(),end=end.isoformat()) for c in councils]


def intake_slot(caller, root_key, collect, archive, prepare_screening, *, check=lambda:None):
    """One prebound scope. Persist capture before preparing/screening children.

    `collect` must be the release's authorised supervised collector. The existing
    source permit is a prerequisite, not minted here. Repeated completed delivery
    reads the retained checkpoint. Any attempted unfinished work requires existing
    reconciliation; expiry never permits source replay or reset accounting.
    """
    if not caller.intake_only:raise Denied('INTAKE_MODE_REQUIRED')
    check();caller.preflight(root_key)
    rows=caller.read_intake_items([root_key])
    if len(rows)!=1:raise Denied('INTAKE_ROOT_MISSING')
    root=rows[0]
    if root['state']=='COMPLETE':
        caller.read_capture()
    else:
        if root['checkpoint'] is not None or root['attempt_count'] or root['state']!='QUEUED':
            raise Denied('INTAKE_RECONCILE_NO_SOURCE_REPLAY')
        check()
        claim=caller.claim_intake_capture()  # stop/authority refusal before collector
        source,outer=collect(root)
        # Timestamp supplied by the supervised collection envelope, not retention
        # time or the historical date filter. Missing timestamp is a blocker.
        stamp=outer.get('observed_at')
        if not isinstance(stamp,str) or datetime.fromisoformat(stamp).tzinfo is None:
            raise Denied('OBSERVATION_TIME_REQUIRED')
        check()
        caller.capture(source,outer,expected_source_sha256=digest(source),
                       evidence_label='TEST_ARCHIVE_NOT_LIVE_EVIDENCE' if caller.allow_test_evidence else None,
                       archive=archive,observed_at=stamp,intake_claim=claim)
        caller.read_capture()  # committed readback before screening registration
    check()
    if caller.registration is None:
        registration=prepare_screening(caller.capture_receipt)
        if registration.kind!='SCREENING' or registration.facts or registration.factual_contracts:
            raise Denied('INTAKE_SCREENING_ONLY')
        if registration.grant.get('source_calls') != 0 or registration.grant.get('writes') != 0:
            raise Denied('INTAKE_EFFECT_AUTHORITY')
        caller.use(registration)
    rows=caller.read_intake_items([p['key'] for p in caller.registration.batches]) if caller.registration.batches else []
    if any(r['state']!='COMPLETE' and r['attempt_count'] for r in rows):
        raise Denied('INTAKE_SCREENING_RECOVERY_REQUIRES_RECONCILIATION')
    check();caller.screen();check()
    return backlog(caller)


def backlog(caller):
    """Read-only bounded projection, including unscreened retained records.

    A backlog is not the Application-based extraction consumer. No model,
    document, Application or opportunity interface is called here.
    """
    if not caller.intake_only:raise Denied('INTAKE_MODE_REQUIRED')
    capture=caller.read_capture()
    if capture.get('kind')!='LISTING_RECEIPT_V1' or not capture.get('durable_archive'):
        raise Denied('INTAKE_CAPTURE_REQUIRED')
    records=capture['records']
    if len(records)>60:raise Denied('INTAKE_ROW_BOUND')
    screens=caller.registration.screens if caller.registration else {}
    keys=[x['key'] for x in screens.values()]
    rows={r['key']:r for r in caller.read_intake_items(keys)} if keys else {}
    out=[]
    for record in records:
        expected=assessment_identity(record,caller.rule)
        descriptor=screens.get(record['reference'])
        row=rows.get(descriptor['key']) if descriptor else None
        result=row['checkpoint'] if row and row['state']=='COMPLETE' else None
        if row and (row['revision']!=expected[3] or row['dependencies']!=[caller.root_key]
                    or row['subject']!={'kind':'APPLICATION','council':capture['council'],'reference':record['reference']}):
            raise Denied('INTAKE_SCREENING_IDENTITY')
        if result and (result.get('record_sha256')!=expected[0] or result.get('config_sha256')!=expected[2]
                       or result.get('source_sha256')!=capture['source_sha256']):
            raise Denied('INTAKE_SCREENING_PROVENANCE')
        outcome=routing_of(result)[1] if result else None
        out.append(dict(council=capture['council'],reference=record['reference'],source_url=record['source_url'],
                        source_record_id=record['source_record_id'],fields=record['fields'],
                        observed_at=capture.get('observed_at'),capture_key=caller.root_key,
                        capture_sha256=digest(capture),source_sha256=capture['source_sha256'],
                        archive=capture['durable_archive'],screening_key=descriptor['key'] if descriptor else None,
                        screening_outcome=outcome,screening_state=row['state'] if row else 'NOT_PREPARED',
                        failure_reason=row['reason'] if row else None,
                        processing_state='AWAITING_LATER_ASSESSMENT_OR_EXTRACTION' if result else 'AWAITING_SCREENING',
                        admission_eligible=identity_admission_eligible(result) if result else False,
                        application_admitted=False,extraction_complete=False))
    return bounded(dict(records=out,coverage_advance=False,window_claim='NONE',extraction_consumer_connected=False),2*1024**2)


def inactive_main():
    """No legacy fallback, dynamic plugin, administrative URL or hidden activation."""
    import json
    print(json.dumps(dict(status='BLOCKED',reason='DAILY_INTAKE_AUTHORITY_BOOTSTRAP_NOT_SUPPORTED',
                          database_connections=0,source_requests=0,application_writes=0)))
    return 2
