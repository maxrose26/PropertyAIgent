"""Dormant recorded-response integration into the existing admitted child."""
import json
import os
import time
from sqlalchemy import select, func
from app.db.models import ScrapeRun
from app.pipeline.discovery_config import is_production_runtime
from app.revisit.idox import RecordedIdox, Deferred
from app.revisit.schema import work
from app.revisit.storage import Store
from app.revisit.migration import verify


def run_recorded_stage(engine, council, recordings, *, on_fetched=None):
    if is_production_runtime():
        raise RuntimeError('recorded revisit integration is local-only')
    store = Store(engine, council)
    with store.transaction() as (conn, run_id, owner):
        verify(conn)
        row = conn.execute(select(ScrapeRun.__table__).where(ScrapeRun.id==run_id)).mappings().one()
        progress = json.loads(row['progress'] or '{}')
        seconds = progress.get('limits',{}).get('effective_council_seconds')
        if not isinstance(seconds, (int,float)) or seconds <= 0:
            return {'outcome':'deferred','reason':'remaining admitted budget unavailable'}
        # started_at precedes launching child, so this conservatively understates
        # its remaining supervisor allowance. No watchdog extension.
        import datetime as dt
        started = row['started_at']
        if started.tzinfo is None:
            started = started.replace(tzinfo=dt.timezone.utc)
        remaining = started.timestamp()+seconds-time.time()-30
    if remaining <= 0:
        return {'outcome':'deferred','reason':'cleanup/council budget reserved'}
    adapter = RecordedIdox(recordings, time.monotonic()+min(10,remaining))
    store.recover()
    completed = 0
    ledger = []
    started_slice = time.monotonic()
    # One reserved small slice, after ordinary discovery in run_weekly. Existing
    # full council watchdog and least-recently-attempted order remain unchanged.
    for _ in range(2):
        if time.monotonic() >= adapter.deadline:
            break
        ticket = store.reserve()
        if ticket is None:
            break
        entry = dict(reference=ticket['reference'], stage=ticket['stage'],
                     cursor=ticket['cursor'], attempt_id=ticket['attempt_id'])
        ledger.append(entry)
        try:
            result = adapter.fetch(ticket)
            if on_fetched is not None:
                on_fetched(ticket, result)
            with store.transaction() as (conn, _, __):
                if conn.execute(select(func.count()).select_from(work)).scalar_one()+2*len(result.get('edges',[])) > 32:
                    raise Deferred('frontier allocation exhausted')
            entry['outcome'] = store.finish(ticket,result)
            completed += 1
        except Deferred as exc:
            store.partial(ticket,str(exc),deferred=True)
            entry.update(outcome='deferred', reason=str(exc))
            break
        except (RuntimeError,ValueError) as exc:
            store.partial(ticket,str(exc))
            entry.update(outcome='partial', reason=str(exc))
    with store.transaction() as (conn, _, __):
        pending = conn.execute(select(func.count()).select_from(work).where(work.c.council==council,work.c.outcome!='complete')).scalar_one()
    return dict(outcome='partial' if pending else 'complete', completed_responses=completed,
                pending=pending, requests=adapter.calls, received_bytes=adapter.bytes,
                attempted=len(ledger), ledger=ledger, elapsed_seconds=time.monotonic()-started_slice,
                coverage='only seeded application/stage/routes; recorded transport')


def maybe_run_recorded_stage(engine, council):
    """No configured recording means dormant; no seed, migration or portal work."""
    path = os.getenv('PROPERTYAIGENT_REVISIT_RECORDING')
    if not path:
        return {'outcome':'dormant'}
    if is_production_runtime():
        raise RuntimeError('recorded revisit integration is local-only')
    from pathlib import Path
    file = Path(path)
    if file.stat().st_size > 65536:
        raise ValueError('recording manifest too large')
    raw = json.loads(file.read_text())
    recordings = {k:dict(status=v['status'],chunks=[bytes.fromhex(x) for x in v['chunks_hex']]) for k,v in raw.items()}
    return run_recorded_stage(engine,council,recordings)
