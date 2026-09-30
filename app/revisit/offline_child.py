"""Finite local recording branch of run_weekly.main; no live transport."""
import json
import os
from pathlib import Path
import signal
import time
from sqlalchemy.orm import Session
from app.db.ah_disposable_postgres import create_disposable_engine, require_engine
from app.pipeline.discovery_owner import verify_child
from app.pipeline.discovery_config import is_production_runtime
from app.revisit.storage import Store
from app.revisit.stage import run_recorded_stage
from app.revisit.idox import RecordedIdox


def require_offline_owner(engine):
    if is_production_runtime() or not verify_child():
        raise RuntimeError('mixed recording requires local admitted child')
    require_engine(engine)


def run(path, council_code):
    if is_production_runtime() or not verify_child():
        raise RuntimeError('mixed recording requires local admitted child')
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError('mixed recording manifest too large')
    spec = json.loads(path.read_text())
    engine = create_disposable_engine(spec['proof'])
    try:
        require_offline_owner(engine)
        from app.config import get_council
        from app.pipeline.run_weekly import stage_scrape
        from app.scrapers.idox_portal import extract_table_fields, ScrapedApplication
        from app.scrapers.unit_filter import qualify
        from app.db.models import ScrapeRun
        from sqlalchemy import select
        import datetime as dt
        store = Store(engine,council_code)
        with store.transaction() as (conn,run_id,owner):
            row = conn.execute(select(ScrapeRun.__table__).where(ScrapeRun.id==run_id)).mappings().one()
            start = row['started_at']
            if start.tzinfo is None:start=start.replace(tzinfo=dt.timezone.utc)
            remaining = start.timestamp()+json.loads(row['progress'])['limits']['effective_council_seconds']-time.time()-30
        if remaining <= 0:
            raise RuntimeError('no admitted budget after cleanup reserve')
        council=get_council(council_code)
        records={k:dict(status=v['status'],chunks=[bytes.fromhex(x) for x in v['chunks_hex']]) for k,v in spec['responses'].items()}
        discovery=RecordedIdox(records,time.monotonic()+min(10,remaining),requests=2,body_limit=4096,total_bytes=8192)
        discovery_started=time.monotonic()
        ledger=[]
        # Reserved discovery capacity before revisit work; explicit finite list.
        for url in spec['new_urls'][:2]:
            entry={'url':url,'outcome':'attempted'};ledger.append(entry)
            try:
                fields=extract_table_fields(discovery.read(url).decode())
                if not fields.get('Reference'):raise ValueError('missing recorded reference')
                q=qualify(fields.get('Proposal',''),council.unit_threshold)
                app=ScrapedApplication(fields['Reference'],fields,url,url,None,q.unit_count,q.category,q.classification,q.qualifies)
                with Session(engine) as session:
                    session.execute(__import__('sqlalchemy').text("SET LOCAL statement_timeout='5s'"))
                    session.execute(__import__('sqlalchemy').text("SET LOCAL lock_timeout='1s'"))
                    count=stage_scrape(session,None,council,'01/09/2026','30/09/2026','offline-mixed',recorded_applications=[app])
                entry.update(reference=app.reference,outcome='completed',qualifying=count)
            except (ValueError,RuntimeError) as exc:
                entry.update(outcome='partial',reason=str(exc))
        discovery_report=dict(attempted=len(ledger),completed=sum(x['outcome']=='completed' for x in ledger),
            deferred=spec['new_urls'][2:],ledger=ledger,requests=discovery.calls,bytes=discovery.bytes,
            elapsed_seconds=time.monotonic()-discovery_started)
        print('[discovery-progress] '+json.dumps({'mixed_discovery':discovery_report}),flush=True)

        def pause_after_fetch(ticket,response):
            if ticket['reference'] == spec.get('pause_reference') and ticket['stage']=='documents':
                (path.parent/'interrupted-ticket.json').write_text(json.dumps(ticket))
                print('[mixed-pause] '+str(os.getpid()),flush=True)
                # Real controller kills this PID. Original watchdog remains armed.
                while True:signal.pause()

        revisit=run_recorded_stage(engine,council_code,records,on_fetched=pause_after_fetch)
        print('[discovery-progress] '+json.dumps({'mixed_revisit':revisit}),flush=True)
        if spec.get('reject_ticket'):
            ticket=json.loads((path.parent/'interrupted-ticket.json').read_text())
            try:
                store.finish(ticket,dict(cursor=ticket['cursor'],next=None,documents=[]))
            except RuntimeError:
                print('[discovery-progress] '+json.dumps({'stale_ticket_rejected':True}),flush=True)
            else:raise AssertionError('stale ticket accepted')
        status='partial' if revisit['pending'] or discovery_report['deferred'] or any(x['outcome']!='completed' for x in ledger) else 'success'
        print('[run-health] status='+status+' scope=offline-mixed-recording',flush=True)
    finally:
        engine.dispose()
