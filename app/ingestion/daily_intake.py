"""Intake-only connection using existing capture, batches and restricted SQL.

No credential lookup, grant issuance, source transport, admission or scheduler.
The release supplies an authorised, supervised collector and existing registration
callback. The existing restricted controller supplies rolling authority and supervision.
These component functions cannot issue that authority themselves.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .ledger import Denied, bounded, digest
from .listing_screening import assessment_identity, routing_of, identity_admission_eligible

MAX_SLOTS = 3  # existing demonstrated package shape, not nine-council capacity


def contained_idox_failure(source,outer,root):
    """Only positively closed, fully accounted HTTP429/503 Idox failures.

    No exception-text classification, timeout generalisation, partial screening
    or invented browser cleanup. Other failures remain shared-stop failures.
    """
    import math
    from .coordinator import validate_outer
    status=((source.get('failure_diagnostic') or {}).get('transport') or {}).get('http_status')
    if not source.get('failure') or type(status) is not int or status not in (429,503):return None
    validate_outer(outer,root['limits'])
    r=source.get('resource') or {};scope=root['subject']
    if (source.get('council')!=scope['council'] or source.get('requested_interval')!=[scope['start'],scope['end']]
        or source.get('date_semantics')!=scope['semantics'] or source.get('persistence') is not False
        or source.get('cleanup') not in {'BOUNDARY_CLOSED','SESSION_BOUNDARY_CLOSED'}
        or source.get('proof_retention_failure') or r.get('retries')!=0 or r.get('budget_exhaustion') is not False):
        raise Denied('CONTAINED_FAILURE_EVIDENCE')
    for k,cap in [('requests_attempted',10),('received_bytes',3000000)]:
        if type(r.get(k)) is not int or not 0<=r[k]<=cap:raise Denied('CONTAINED_FAILURE_ACCOUNTING')
    if type(r.get('elapsed_seconds')) not in (int,float) or not math.isfinite(r['elapsed_seconds']) or not 0<=r['elapsed_seconds']<=45:
        raise Denied('CONTAINED_FAILURE_ACCOUNTING')
    return 'RATE_LIMIT' if status==429 else 'SOURCE_UNAVAILABLE'


def current_windows(now, councils, *, overlap_days=7):
    """Current intake first; missed historical intervals stay separate gaps.

    Source dates are not public-availability dates. This does not declare recall
    or freshness, nor refresh decisions on older applications.
    """
    from app.pipeline.discovery_contract import COUNCILS
    from app.config import get_council
    if now.tzinfo is None or type(overlap_days) is not int or not 1 <= overlap_days <= 28:
        raise Denied('INTAKE_DATE_BOUND')
    councils=tuple(councils)
    if not 1 <= len(councils) <= MAX_SLOTS or len(set(councils)) != len(councils):
        raise Denied('INTAKE_SLOT_BOUND')
    if any(c not in COUNCILS for c in councils):
        raise Denied('INTAKE_COUNCIL')
    end=now.astimezone(ZoneInfo('Europe/London')).date()-timedelta(days=1)
    return [dict(council=c,semantics=get_council(c).date_field_mode.upper(),start=(end-timedelta(days=overlap_days-1)).isoformat(),end=end.isoformat()) for c in councils]


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
        # Only the connected rolling route supplies this qualified classifier.
        # A recognised failed audit is archived/settled, never screened as a
        # complete or partial listing. Unknown failures propagate and stop.
        classifier=getattr(caller,'contained_failure',None)
        category=classifier(source,outer,root) if classifier is not None else None
        if category is not None:
            caller.settle_intake_failure(claim,category,source,outer,archive)
            return dict(status='INCOMPLETE',failure=category,council=root['subject']['council'],
                        records=[],coverage_advance=False,window_claim='NONE')
        # A non-contained, incomplete audit is not a qualified capture. Only
        # the selected private backend can preserve the original evidence;
        # never promote it to a checkpoint, screening, or coverage claim.
        if isinstance(source,dict) and source.get('failure'):
            retain=getattr(caller,'retain_unqualified_source',None)
            if retain is not None:
                retain(source,outer,root)
                raise Denied('INTAKE_UNQUALIFIED_SOURCE_EVIDENCE_ONLY')
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
    if not caller.capture_receipt['records']:return backlog(caller)
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
    batches=caller.registration.batches if caller.registration else []
    keys=[caller.root_key,*[x['key'] for x in screens.values()],*[x['key'] for x in batches]]
    rows={r['key']:r for r in caller.read_intake_items(keys)}
    out=[]
    for record in records:
        expected=assessment_identity(record,caller.rule)
        from .observation_screening import observation_revision
        task_revision=observation_revision(expected[3],digest(capture))
        descriptor=screens.get(record['reference'])
        row=rows.get(descriptor['key']) if descriptor else None
        result=row['checkpoint'] if row and row['state']=='COMPLETE' else None
        if row and (row['revision']!=task_revision or row['dependencies']!=[caller.root_key]
                    or row['subject']!={'kind':'APPLICATION','council':capture['council'],'reference':record['reference']}):
            raise Denied('INTAKE_SCREENING_IDENTITY')
        if result and (result.get('record_sha256')!=expected[0] or result.get('config_sha256')!=expected[2]
                       or result.get('capture_bound') is not True or result.get('assessment_revision')!=task_revision
                       or result.get('capture_checkpoint_sha256')!=digest(capture)
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
                        processing_state=_screening_only_state(result) if result else 'AWAITING_SCREENING',
                        admission_eligible=identity_admission_eligible(result) if result else False,
                        application_admitted=False,extraction_complete=False))
    tasks=[{k:r[k] for k in ('key','task','state','phase','reason','attempt_count','next_action')} for r in rows.values()]
    return bounded(dict(records=out,tasks=tasks,coverage_advance=False,window_claim='NONE',extraction_consumer_connected=False),2*1024**2)



def _screening_only_state(result):
    """Expose the authoritative screening route, never factual admission.

    This projection cannot prove an Application, verified units, coverage,
    buyer qualification or downstream extraction. Unknown routes refuse.
    """
    return 'SCREENING_ONLY_'+routing_of(result)[1]

def backlog_page(ledger,councils,contracts,rule,*,after=None,limit=3,connection=None):
    """Paginated restricted read across runs, no historical key inventory.

    Uses the existing primary-key cursor and SELECT permission; no new index,
    table, grant, task claim or downstream processing. A page is not coverage.
    Separate observations remain separate with their original provenance.
    """
    import re
    from sqlalchemy import select,cast,and_,or_
    from sqlalchemy.dialects.postgresql import JSONB
    from .schema import WorkItem as W
    if (type(limit) is not int or not 1<=limit<=3 or not 1<=len(councils)<=2
        or len(set(councils))!=len(councils) or len(contracts)!=len(councils)
        or after is not None and not re.fullmatch('[a-f0-9]{64}',after)):
        raise Denied('BACKLOG_PAGE_BOUND')
    # A cross-product of councils and contracts would admit a root under a
    # different council's approved contract. Bind each exact pair instead.
    paired=or_(*(and_(W.c.subject['council'].as_string()==c,
                      W.c.contract==contract) for c,contract in zip(councils,contracts)))
    query=select(W).where(W.c.task=='DISCOVERY',
                          W.c.subject['kind'].as_string()=='DISCOVERY_SCOPE',paired)
    if after is not None:query=query.where(W.c.key>after)
    from contextlib import nullcontext
    with (nullcontext(connection) if connection is not None else ledger.worker_engine.begin()) as connection:
        ledger._limits(connection)
        roots=[dict(r) for r in connection.execute(query.order_by(W.c.key).limit(limit+1)).mappings()]
        more=len(roots)>limit;roots=roots[:limit];records=[];failures=[]
        for root in roots:
            capture=root['checkpoint'] or {}
            if capture.get('kind')!='LISTING_RECEIPT_V1' or root['state']!='COMPLETE':
                failures.append(dict(capture_key=root['key'],council=root['subject']['council'],state=root['state'],
                                     reason=root['reason'],phase=root['phase'],attempt_count=root['attempt_count'],
                                     evidence=capture.get('durable_archive'),downstream_complete=False))
                continue
            # COMPLETE alone is not proof of a usable listing: require the
            # stored root, final receipt, and privately read-back archive to
            # agree on the exact source evidence before exposing this backlog.
            subject=root['subject'];archive=capture.get('durable_archive')
            # Historical Bolton RECEIVED-v1 receipts omit date_semantics.
            # Only this exact legacy contract can inherit its bound scope basis;
            # explicit contradictory source evidence must still be rejected.
            legacy_received_basis=(isinstance(subject,dict)
                and subject.get('council')=='bolton'
                and root['contract']=='bolton-received-idox-coordinator-v1'
                and subject.get('semantics')=='RECEIVED'
                and 'date_semantics' not in capture)
            outcome=root['outcome'];source_sha=capture.get('source_sha256')
            if (not isinstance(subject,dict) or not isinstance(archive,dict)
                or not isinstance(outcome,dict) or not isinstance(source_sha,str)
                or re.fullmatch('[a-f0-9]{64}',source_sha) is None
                or archive.get('sha256')!=source_sha or archive.get('readback_verified') is not True
                or outcome.get('outcome')!='ENUMERATED_METADATA_RETAINED'
                or outcome.get('source_sha256')!=source_sha
                or capture.get('accounting_complete') is not True
                or capture.get('cleanup')!='CLOSED'
                or capture.get('council')!=subject.get('council')
                or capture.get('contract')!=root['contract']
                or capture.get('interval')!=[subject.get('start'),subject.get('end')]
                or (capture.get('date_semantics')!=subject.get('semantics') and not legacy_received_basis)
                or not isinstance(capture.get('records'),list) or len(capture['records'])>60):
                raise Denied('BACKLOG_CAPTURE_PROVENANCE')
            # Preserve historical v1/unbound v3 alongside an eventual bound
            # v3 WITHOUT raising the 60-row SQL read or returned-item bound.
            # Summarise all versions server-side; fetch only actionable rows.
            from sqlalchemy import func,and_,or_
            subject_json=cast(W.c.subject,JSONB)
            scope=(W.c.task=='SCREENING',cast(W.c.dependencies,JSONB)==[root['key']])
            bound_v3=and_(W.c.contract=='listing-screen-v3',
                         W.c.checkpoint['capture_bound'].as_string()=='true')
            selected=or_(W.c.state!='COMPLETE',bound_v3)
            summaries=[dict(g) for g in connection.execute(
                select(subject_json.label('subject'),
                       func.count().label('total'),
                       func.count().filter(W.c.contract=='listing-screen-v1').label('v1'),
                       func.count().filter(W.c.contract=='listing-screen-v3').label('v3'),
                       func.count().filter(bound_v3).label('bound'),
                       func.count().filter(W.c.state!='COMPLETE').label('unfinished'),
                       func.count().filter(selected).label('selected'))
                .where(*scope).group_by(subject_json)
                .order_by(subject_json).limit(61)).mappings()]
            if len(summaries)>60:raise Denied('BACKLOG_ASSESSMENT_OVERFLOW')
            expected_refs={r['reference'] for r in capture['records']}
            if len(expected_refs)!=len(capture['records']):raise Denied('BACKLOG_DUPLICATE_CAPTURE_REFERENCE')
            grouped={}
            for g in summaries:
                subject=g['subject']
                if (not isinstance(subject,dict) or subject.get('reference') not in expected_refs
                    or subject!=dict(kind='APPLICATION',council=capture['council'],
                                     reference=subject.get('reference'))):
                    raise Denied('BACKLOG_SCREENING_IDENTITY')
                if g['total']!=g['v1']+g['v3']:
                    raise Denied('BACKLOG_UNKNOWN_ASSESSMENT_CONTRACT')
                if (g['v1']>1 or g['v3']>2 or g['bound']>1
                    or g['v3']==2 and g['bound']!=1
                    or g['unfinished'] and g['total']>1):
                    raise Denied('BACKLOG_MULTIPLE_ASSESSMENTS')
                grouped[subject['reference']]=g
            active=[dict(s) for s in connection.execute(
                select(W).where(*scope,selected)
                .order_by(W.c.key).limit(61)).mappings()]
            if len(active)>60:raise Denied('BACKLOG_ASSESSMENT_OVERFLOW')
            active_by_ref={}
            for s in active:
                sub=s['subject']
                if (not isinstance(sub,dict) or sub.get('reference') not in grouped
                    or sub!=dict(kind='APPLICATION',council=capture['council'],
                                 reference=sub.get('reference'))):
                    raise Denied('BACKLOG_SCREENING_IDENTITY')
                active_by_ref.setdefault(sub['reference'],[]).append(s)
            if any(len(active_by_ref.get(ref,[]))!=g['selected']
                   for ref,g in grouped.items()):
                raise Denied('BACKLOG_SCREENING_IDENTITY')
            for record in capture['records']:
                group=grouped.get(record['reference'])
                matches=active_by_ref.get(record['reference'],[])
                current=[m for m in matches if (m['contract']=='listing-screen-v3'
                         and m['state']=='COMPLETE'
                         and isinstance(m['checkpoint'],dict)
                         and m['checkpoint'].get('capture_bound') is True)]
                if len(current)!=(group['bound'] if group else 0):
                    raise Denied('BACKLOG_MULTIPLE_ASSESSMENTS')
                s=(current[0] if current else
                   matches[0] if group and group['total']==1 and len(matches)==1
                   and matches[0]['state']!='COMPLETE' else None)
                result=s['checkpoint'] if s and s['state']=='COMPLETE' else None
                unbound_legacy=bool(group) and not current and s is None
                if result:
                    from .observation_screening import observation_revision
                    config=result.get('config')
                    if not isinstance(config,dict):raise Denied('BACKLOG_SCREENING_CONFIG')
                    record_sha=digest(record);config_sha=digest(config)
                    base_revision=digest(dict(record_sha256=record_sha,config_sha256=config_sha))
                    # History is verified against its ORIGINAL frozen config,
                    # not re-screened or invalidated by today's threshold/code.
                    if (s['revision']!=observation_revision(base_revision,digest(capture)) or result.get('record_sha256')!=record_sha
                        or result.get('config_sha256')!=config_sha or result.get('capture_checkpoint_sha256')!=digest(capture)
                        or result.get('assessment_revision')!=s['revision'] or result.get('capture_bound') is not True
                        or result.get('source_sha256')!=capture['source_sha256']):raise Denied('BACKLOG_SCREENING_PROVENANCE')
                records.append(dict(council=capture['council'],reference=record['reference'],source_record_id=record['source_record_id'],
                    source_url=record['source_url'],fields=record['fields'],observed_at=capture.get('observed_at'),
                    capture_key=root['key'],capture_sha256=digest(capture),source_sha256=capture['source_sha256'],archive=capture['durable_archive'],
                    screening_key=s['key'] if s else None,
                    screening_state=('HISTORICAL_UNBOUND_REQUIRES_RESCREENING' if unbound_legacy else
                                     s['state'] if s else 'NOT_PREPARED'),
                    historical_screening_items=group['total'] if group else 0,
                    screening_outcome=routing_of(result)[1] if result else None,
                    screening_config_sha256=result.get('config_sha256') if result else None,
                    screening_matches_current_rule=result.get('config_sha256')==digest(rule.config()) if result else None,
                    processing_state=('HISTORICAL_RESCREENING_REQUIRED' if unbound_legacy else
                                      _screening_only_state(result) if result else 'AWAITING_SCREENING'),
                    application_admitted=None,extraction_complete=None,downstream_state='NOT_TRACKED_BY_INTAKE'))
    captures=[dict(capture_key=r['key'],council=r['subject']['council'],scope=r['subject'],
                   record_count=len((r['checkpoint'] or {}).get('records',[])),
                   explicit_zero=(r['checkpoint'] or {}).get('explicit_zero',False),
                   archive=(r['checkpoint'] or {}).get('durable_archive')) for r in roots if r['state']=='COMPLETE']
    return bounded(dict(records=records,failures=failures,captures=captures,next_cursor=roots[-1]['key'] if more else None,
                        more=more,coverage_advance=False,extraction_consumer_connected=False),2*1024**2)


def inactive_main():
    """No legacy fallback, dynamic plugin, administrative URL or hidden activation."""
    import json
    print(json.dumps(dict(status='BLOCKED',reason='EXPLICIT_INTAKE_PERIOD_REQUIRED',
                          database_connections=0,source_requests=0,application_writes=0)))
    return 2
