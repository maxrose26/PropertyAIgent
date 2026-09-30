"""Transactional revisit persistence under the unchanged real P0-A child owner."""
import hashlib
import json
import os
import time
from contextlib import contextmanager
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from app.db.models import ScrapeRun
from app.db.ah_disposable_postgres import require_connection, require_engine
from app.pipeline.discovery_owner import verify_child, terminal_evidence
from app.pipeline.lookup_outcome import reference_key
from app.revisit.schema import work, attempts, versions, observations, relationships


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(council, reference):
    council, reference = council.strip().casefold(), reference_key(reference)
    if not council or not reference or len(council) > 100 or len(reference) > 255:
        raise ValueError('invalid scoped identity')
    return council, reference


class Store:
    def __init__(self, engine, council):
        self.engine, self.council = engine, council

    @contextmanager
    def transaction(self):
        owner = verify_child()
        if not owner:
            raise RuntimeError('revisit requires admitted child descriptor')
        run_id = int(os.environ['PROPERTYAIGENT_RUN_ID'])
        require_engine(self.engine)  # reject ordinary engines before connecting
        with self.engine.begin() as conn:
            require_connection(conn)
            conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            conn.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
            row = conn.execute(select(ScrapeRun.__table__).where(ScrapeRun.id == run_id).with_for_update()).mappings().one()
            recorded = json.loads(row['progress'] or '{}').get('owner', {})
            if row['status'] != 'running' or row['council_code'] != self.council or any(
                    recorded.get(k) != owner.get(k) for k in ('version','invocation','service','instance','boot','pid','pid_start')):
                raise RuntimeError('revisit run/owner mismatch')
            yield conn, run_id, owner

    @staticmethod
    def seed_in(conn, council, reference):
        council, reference = identity(council, reference)
        for stage, route in [('documents','register'), ('relationships','citation_search')]:
            conn.execute(insert(work).values(council=council, reference=reference, stage=stage,
                route=route, cursor='start', generation=0, due=0, failures=0, outcome='pending')
                .on_conflict_do_nothing(constraint='uq_revisit_work'))

    def seed(self, reference):
        with self.transaction() as (conn, _, __):
            self.seed_in(conn, self.council, reference)

    def recover(self):
        count = 0
        with self.transaction() as (conn, run_id, owner):
            rows = conn.execute(select(work).where(work.c.council == self.council,
                work.c.owner_run.is_not(None), work.c.owner_run != run_id).with_for_update()).mappings().all()
            for row in rows:
                old = conn.execute(select(ScrapeRun.progress).where(ScrapeRun.id == row['owner_run'])).scalar_one()
                proof = terminal_evidence(json.loads(old or '{}').get('owner'), owner)
                if not proof:
                    raise RuntimeError('no terminal owner proof')
                conn.execute(update(attempts).where(attempts.c.work_id == row['id'],
                    attempts.c.generation == row['generation'], attempts.c.outcome == 'in_flight')
                    .values(outcome='interrupted', finished=time.time(), report={'terminal_evidence': proof}))
                conn.execute(update(work).where(work.c.id == row['id']).values(
                    owner_run=None, owner_invocation=None, generation=row['generation']+1,
                    outcome='partial', reason='interrupted; successor verified', due=time.time()))
                count += 1
        return count

    def reserve(self, now=None):
        now = time.time() if now is None else now
        with self.transaction() as (conn, run_id, owner):
            row = conn.execute(select(work).where(work.c.council == self.council,
                work.c.owner_run.is_(None), work.c.outcome != 'complete', work.c.due <= now)
                .order_by(work.c.last_attempt.asc().nullsfirst(), work.c.id).limit(1)
                .with_for_update(skip_locked=True)).mappings().first()
            if row is None:
                return None
            gen = row['generation'] + 1
            conn.execute(update(work).where(work.c.id == row['id']).values(generation=gen,
                owner_run=run_id, owner_invocation=owner['invocation'], last_attempt=now, outcome='in_flight'))
            attempt_id = conn.execute(insert(attempts).values(work_id=row['id'], generation=gen,
                run_id=run_id, started=now, outcome='in_flight').returning(attempts.c.id)).scalar_one()
            return dict(row, generation=gen, owner_run=run_id, owner_invocation=owner['invocation'], attempt_id=attempt_id)

    def finish(self, ticket, response, now=None):
        now = time.time() if now is None else now
        serial = json.dumps(response, sort_keys=True, default=lambda b: {'bytes_sha256': digest(b)})
        token = digest(serial.encode())
        with self.transaction() as (conn, run_id, owner):
            row = conn.execute(select(work).where(work.c.id == ticket['id']).with_for_update()).mappings().one()
            prior = conn.execute(select(attempts).where(attempts.c.id == ticket['attempt_id'])).mappings().one()
            if (ticket['owner_run'], ticket['owner_invocation']) != (run_id, owner['invocation']):
                raise RuntimeError('stale worker owner')
            if prior['response_token'] == token and prior['outcome'] == 'complete':
                return 'duplicate'
            if (row['generation'], row['owner_run'], row['owner_invocation']) != (ticket['generation'], run_id, owner['invocation']):
                raise RuntimeError('stale reservation')
            if response.get('cursor') != row['cursor'] or 'next' not in response:
                raise ValueError('cursor/coverage mismatch')
            if response['next'] == row['cursor']:
                raise ValueError('cursor loop')
            for doc in response.get('documents', []):
                if identity(doc['council'], doc['reference']) != (row['council'], row['reference']):
                    raise ValueError('document scope mismatch')
                body = doc['body']
                if not isinstance(body, bytes) or len(body) > 4096:
                    raise ValueError('unverified/oversize body')
                content = dict(council=row['council'], reference=row['reference'], url=doc['url'], digest=digest(body), body=body)
                conn.execute(insert(versions).values(**content).on_conflict_do_nothing(constraint='uq_revisit_content'))
                version_id = conn.execute(select(versions.c.id).where(versions.c.council==row['council'],
                    versions.c.reference==row['reference'], versions.c.url==doc['url'], versions.c.digest==content['digest'])).scalar_one()
                provenance = {k:v for k,v in doc.items() if k != 'body'}
                provenance['review'] = 'unreviewed'
                conn.execute(insert(observations).values(attempt_id=ticket['attempt_id'], version_id=version_id,
                    item=digest(doc['url'].encode()), observed=now, provenance=provenance))
            for edge in response.get('edges', []):
                target = identity(edge['council'], edge['reference'])
                verified = target[0] == row['council'] and edge.get('confidence') == 'verified_reference' and bool(edge.get('citation')) and edge['type'] in {'variation','discharge','reserved_matters','amendment','supersedes'}
                conn.execute(insert(relationships).values(attempt_id=ticket['attempt_id'],
                    item=digest(json.dumps(edge,sort_keys=True).encode()), source_council=row['council'],
                    source_reference=row['reference'], target_council=target[0], target_reference=target[1],
                    kind=edge['type'], route=row['route'], confidence='verified_reference' if verified else 'candidate',
                    review='unreviewed', citation=edge.get('citation'), observed=now))
                if verified:
                    self.seed_in(conn, *target)
            outcome = 'complete' if response['next'] is None else 'partial'
            values = dict(cursor=response['next'], outcome=outcome, owner_run=None, owner_invocation=None,
                          reason='route checked' if outcome == 'complete' else 'continuation pending', failures=0, due=now)
            if outcome == 'complete':
                values['last_success'] = now
            conn.execute(update(work).where(work.c.id == row['id']).values(**values))
            conn.execute(update(attempts).where(attempts.c.id == ticket['attempt_id']).values(
                finished=now, outcome='complete', response_token=token,
                report={'coverage':outcome,'documents':len(response.get('documents',[])), 'edges':len(response.get('edges',[]))}))
            return outcome

    def partial(self, ticket, reason, *, deferred=False, retry_after=0):
        with self.transaction() as (conn, run_id, owner):
            row = conn.execute(select(work).where(work.c.id==ticket['id']).with_for_update()).mappings().one()
            if (row['generation'],row['owner_run'],row['owner_invocation']) != (ticket['generation'],run_id,owner['invocation']):
                raise RuntimeError('stale reservation')
            failures = row['failures'] + (not deferred)
            delay = 0 if deferred else max(min(86400 * 2**min(failures-1,3),604800),retry_after)
            conn.execute(update(work).where(work.c.id==row['id']).values(outcome='deferred' if deferred else 'partial',
                reason=reason[:500], owner_run=None, owner_invocation=None, failures=failures, due=time.time()+delay))
            conn.execute(update(attempts).where(attempts.c.id==ticket['attempt_id']).values(
                outcome='deferred' if deferred else 'partial', finished=time.time(), report={'reason':reason[:500]}))
