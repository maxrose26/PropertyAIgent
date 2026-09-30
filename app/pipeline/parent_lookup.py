"""Bounded durable parent-reference continuation (specification 019).

This table describes attempts, never planning truth. Found applications remain
in the existing Application model; their qualification rules are unchanged.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import time
from collections import Counter
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from app.db.models import Application, ParentLookupWork
from app.pipeline.lookup_outcome import Outcome, LookupResult, reference_key


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def positive_limit(name, default):
    value = int(os.getenv('PROPERTYAIGENT_DISCOVERY_' + name, default))
    if value <= 0:
        raise ValueError('discovery limits must be positive')
    return value


def populate(session, council, extract):
    """Narrow projection; fixed citation snapshot, no document or ORM universe."""
    refs, citations, fingerprints, counts = {}, 0, {}, Counter()
    for ident, proposal in session.execute(select(Application.id, Application.proposal).where(
            Application.council_code == council).order_by(Application.id).execution_options(yield_per=100)):
        raw = extract(proposal or '')
        if not raw:
            continue
        citations += 1
        key = reference_key(raw)
        if len(key) > 255:
            raise ValueError('parent reference exceeds identity storage bound')
        counts[key] += 1
        refs.setdefault(key, raw)
        fingerprints.setdefault(key, hashlib.sha256()).update(f'{ident}:{proposal}\n'.encode())
    existing = {w.reference_key: w for w in session.scalars(select(ParentLookupWork).where(
        ParentLookupWork.council_code == council))}
    for key, raw in refs.items():
        exists = existing.get(key)
        if exists is None:
            try:
                with session.begin_nested():
                    session.add(ParentLookupWork(council_code=council, reference_key=key, raw_reference=raw,
                        work_metadata=json.dumps({'adapter_version': 1, 'citation_fingerprint': fingerprints[key].hexdigest()})))
                    session.flush()
            except IntegrityError:
                pass  # council/reference uniqueness resolves a competing insert
        else:
            metadata = {'adapter_version': 1, 'citation_fingerprint': fingerprints[key].hexdigest()}
            previous = json.loads(exists.work_metadata or '{}')
            if metadata != previous and exists.last_outcome != 'in_flight':
                exists.next_eligible_at = None
                exists.reason = 'source_or_adapter_changed'
                exists.work_metadata = json.dumps(metadata)
    session.commit()
    return refs, citations, counts


def due_query(council, now):
    return select(ParentLookupWork).where(
        ParentLookupWork.council_code == council,
        ParentLookupWork.resolved_application_id.is_(None),
        ParentLookupWork.last_outcome.is_distinct_from('in_flight'),
        ParentLookupWork.next_eligible_at.is_(None) | (ParentLookupWork.next_eligible_at <= now),
    ).order_by(func.coalesce(ParentLookupWork.last_started_at, ParentLookupWork.first_seen_at),
               ParentLookupWork.reference_key)


def reserve(session, work, run_id, now):
    changed = session.execute(update(ParentLookupWork).where(
        ParentLookupWork.id == work.id,
        ParentLookupWork.total_attempts == work.total_attempts,
        ParentLookupWork.last_started_at == work.last_started_at,
        ParentLookupWork.resolved_application_id.is_(None),
        ParentLookupWork.last_outcome.is_distinct_from('in_flight'),
    ).values(last_started_at=now, last_outcome='in_flight', owner_scrape_run_id=run_id,
             total_attempts=ParentLookupWork.total_attempts + 1))
    if changed.rowcount != 1:
        session.rollback()
        raise RuntimeError('parent reservation owner conflict')
    session.commit()


def finish(session, work, run_id, result, now, parent_id=None):
    due = None if result.outcome == Outcome.FOUND else now + dt.timedelta(
        days=1 if result.outcome == Outcome.TRANSIENT_FAILURE else 7)
    if result.retry_after_seconds is not None and due is not None:
        due = max(due, now + dt.timedelta(seconds=result.retry_after_seconds))
    changed = session.execute(update(ParentLookupWork).where(
        ParentLookupWork.id == work.id, ParentLookupWork.owner_scrape_run_id == run_id,
        ParentLookupWork.last_outcome == 'in_flight',
    ).values(last_outcome=result.outcome.value, last_completed_at=now, next_eligible_at=due,
             resolved_application_id=parent_id, reason=result.reason[:100]))
    if changed.rowcount != 1:
        session.rollback()
        raise RuntimeError('parent result owner conflict')
    session.commit()


def fan_out(session, council, extract, qualify):
    """Repeatable after a crash; one child transaction, no portal request."""
    resolved = dict(session.execute(select(ParentLookupWork.reference_key, ParentLookupWork.resolved_application_id).where(
        ParentLookupWork.council_code == council.code, ParentLookupWork.resolved_application_id.is_not(None))).all())
    last_id, updated = 0, 0
    qualifications = {}
    while True:
        batch = session.execute(select(Application.id, Application.proposal).where(
            Application.council_code == council.code, Application.id > last_id,
            Application.unit_confirmation_status.is_(None) | (Application.unit_confirmation_status == 'undetermined')
        ).order_by(Application.id).limit(100)).all()
        if not batch: break
        for ident, proposal in batch:
            last_id = ident
            raw = extract(proposal or '')
            parent_id = resolved.get(reference_key(raw)) if raw else None
            if not parent_id: continue
            if parent_id not in qualifications:
                proposal = session.scalar(select(Application.proposal).where(Application.id == parent_id))
                qualifications[parent_id] = qualify(proposal or '', council.unit_threshold)
            q = qualifications[parent_id]
            if (q.unit_count is not None and q.unit_count < council.unit_threshold) or q.classification == 'Excluded - non-residential':
                values = dict(unit_confirmation_status='confirmed_disqualified',
                    opportunity_classification=f'Excluded - parent {raw} confirmed {q.unit_count} unit(s)' if q.unit_count is not None else f'Excluded - parent {raw} is non-residential')
            elif q.unit_count is not None:
                values = dict(estimated_unit_count=q.unit_count, unit_confirmation_status='confirmed_qualifying',
                    opportunity_classification=f'Confirmed - {q.unit_count} units (via parent {raw})')
            else: continue
            changed = session.execute(update(Application).where(Application.id == ident,
                Application.unit_confirmation_status.is_(None) | (Application.unit_confirmation_status == 'undetermined')).values(**values).execution_options(synchronize_session=False))
            if changed.rowcount:
                # Keep any already-loaded citing object consistent without an
                # extra SELECT or second ORM UPDATE; the conditional SQL won.
                from sqlalchemy.orm.attributes import set_committed_value
                loaded = session.identity_map.get(session.identity_key(Application, ident))
                if loaded is not None:
                    for field, value in values.items():
                        set_committed_value(loaded, field, value)
            session.commit()  # retain independently durable child progress
            updated += changed.rowcount
    return updated


def run_parent_stage(session, page, council, health=None, breaker=None, lookup=None,
                     clock=time.monotonic, sleep=time.sleep, now=utcnow):
    from app.pipeline.run_weekly import extract_parent_reference, qualify, _upsert_scraped_application
    from app.diagnostics.memory import cgroup_memory, log_memory
    from app.scrapers import arcus_portal, idox_portal
    import requests
    limit = positive_limit('PARENT_ITEMS', 25)
    attempts_limit = positive_limit('PARENT_ATTEMPTS', 30)
    deadline = clock() + positive_limit('PARENT_SECONDS', 180)
    run_id = int(os.environ['PROPERTYAIGENT_RUN_ID']) if os.getenv('PROPERTYAIGENT_RUN_ID') else None
    if os.getenv('RENDER') == 'true' and not run_id:
        raise RuntimeError('parent stage requires admitted council run')
    if run_id:
        from app.db.models import ScrapeRun
        row = session.get(ScrapeRun, run_id)
        expected_owner = json.loads(os.environ.get('PROPERTYAIGENT_OWNER', '{}'))
        if (row is None or row.council_code != council.code or row.status != 'running'
            or json.loads(row.progress or '{}').get('owner', {}).get('invocation') != expected_owner.get('invocation')
            or not expected_owner.get('invocation')):
            raise RuntimeError('parent council run ownership mismatch')
    keys, citations, citation_counts = populate(session, council.code, extract_parent_reference)
    stats = Counter(citations=citations, distinct_citations=len(keys), duplicate_citations=citations-len(keys), duplicate_requests_suppressed=0)
    parents = {}
    for ref, ident in session.execute(select(Application.reference, Application.id).where(Application.council_code == council.code)):
        parents.setdefault(reference_key(ref), []).append(ident)
    for work in session.scalars(select(ParentLookupWork).where(ParentLookupWork.council_code == council.code)):
        ids = parents.get(work.reference_key, [])
        if work.last_outcome == 'in_flight':
            raise RuntimeError('parent owner must be reconciled before selection')
        if len(ids) == 1:
            work.resolved_application_id = ids[0]
            work.last_outcome = 'found'
            stats['reused_found'] += 1
        elif len(ids) > 1:
            work.resolved_application_id = None
            work.last_outcome = 'ambiguous_identity'
            work.next_eligible_at = now() + dt.timedelta(days=7)
            work.reason = 'duplicate_database_identity'
    session.commit()
    snapshot = now()
    worklist = list(session.scalars(due_query(council.code, snapshot).limit(limit)))
    selected = [w.id for w in worklist]
    selection_trace = [{'id': w.id, 'queue_at': (w.last_started_at or w.first_seen_at).isoformat(),
                        'next_eligible_at': w.next_eligible_at.isoformat() if w.next_eligible_at else None,
                        'reference_key': w.reference_key, 'attempts_before': w.total_attempts} for w in worklist]
    queue = [(w, 0, 0) for w in worklist]
    outcomes, attempted_ids, durations = Counter(), [], []
    reason = 'item_budget'
    with requests.Session() as http:
        from app.scrapers.idox_portal import HEADERS
        http.headers.update(HEADERS)
        for work, retry, ready in queue:
            memory = cgroup_memory()
            if clock() >= deadline: reason = 'time_budget'; break
            if stats['attempts'] >= attempts_limit: reason = 'attempt_budget'; break
            if breaker and breaker.is_open:
                reason = 'circuit'
                if health: health.record_portal_unavailable('parent-lookup')
                break
            if memory and memory[0] / memory[1] >= .70: reason = 'soft_memory'; break
            if ready > clock():
                if ready >= deadline: continue
                sleep(ready-clock())
            if clock() >= deadline:
                reason = 'time_budget'
                break
            memory = cgroup_memory()
            if memory and memory[0] / memory[1] >= .70:
                reason = 'soft_memory'
                break
            reserve(session, work, run_id, now())
            start = clock()
            if retry == 0:
                stats['duplicate_requests_suppressed'] += max(0, citation_counts[work.reference_key]-1)
            log_memory('parent_lookup.before', council=council.code, breakdown=True, extra={'work_id': work.id, 'identity_map': len(session.identity_map)})
            if lookup:
                result = lookup(work.raw_reference)
            elif council.doc_system == 'arcus':
                result = arcus_portal.lookup_parent(page, council, work.raw_reference)
            else:
                result = idox_portal.lookup_parent(page, http, council, work.raw_reference)
            stats['attempts'] += 1
            stats['retries'] += retry
            attempted_ids.append(work.id)
            durations.append(round(clock()-start, 3))
            parent_id = None
            if result.outcome == Outcome.FOUND:
                app = result.application
                if not app or reference_key(app.reference or '') != work.reference_key:
                    result = LookupResult(Outcome.AMBIGUOUS_IDENTITY, reason='detail_reference_mismatch')
                else:
                    q = qualify(app.fields.get('Proposal', ''), council.unit_threshold)
                    excluded = (q.unit_count is not None and q.unit_count < council.unit_threshold) or q.classification == 'Excluded - non-residential'
                    parent = _upsert_scraped_application(session, council, app, batch_id=None,
                        unit_confirmation_status='confirmed_disqualified' if excluded else 'confirmed_qualifying')
                    session.flush()
                    parent_id = parent.id
                    stats['fetched'] += 1
            finish(session, work, run_id, result, now(), parent_id)
            outcomes[result.outcome.value] += 1
            if breaker:
                if result.outcome != Outcome.TRANSIENT_FAILURE: breaker.record_success()
                elif result.host_failure: breaker.record_failure(requests.ConnectionError(result.reason), stage='parent-lookup')
            if result.outcome == Outcome.TRANSIENT_FAILURE and retry == 0:
                queue.append((work, 1, clock()+max(5, result.retry_after_seconds or 0)))
            log_memory('parent_lookup.after', council=council.code, breakdown=True, extra={'work_id': work.id, 'identity_map': len(session.identity_map)})
    stats['children_updated'] = fan_out(session, council, extract_parent_reference, qualify)
    pending = session.scalar(select(func.count()).select_from(due_query(council.code, snapshot).order_by(None).subquery()))
    cooldown = session.scalar(select(func.count(ParentLookupWork.id)).where(ParentLookupWork.council_code == council.code, ParentLookupWork.resolved_application_id.is_(None), ParentLookupWork.next_eligible_at > snapshot))
    if health:
        health.parents_deferred += pending
        for w in worklist:
            if w.id in attempted_ids:
                health.record_parent_lookup(succeeded=w.last_outcome != 'transient_failure')
    report = dict(stats, outcomes=dict(outcomes), distinct_attempted=len(set(attempted_ids)),
        attempted_ids=attempted_ids, durations_seconds=durations, deferred=pending,
        deferred_reason=reason if pending else None, selected_ids=selected, selection_trace=selection_trace,
        cooldown_deferred=cooldown,
        elapsed_lookup_seconds=round(sum(durations), 3),
        achieved_references_per_second=len(set(attempted_ids))/sum(durations) if sum(durations) else None,
        projected_eligible_lookup_seconds=pending*sum(durations)/len(set(attempted_ids)) if attempted_ids else None,
        projection_basis='fixed currently eligible cohort; excludes outages, cooldown and new arrivals',
        identity_map_size=len(session.identity_map))
    print('[discovery-progress] ' + json.dumps({'parents': report}), flush=True)
    return stats['fetched']
