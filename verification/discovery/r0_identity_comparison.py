"""Proposed protected fixed-80 identity-only read. Unregistered, not authorised.

No source reader, admission or B2 imports. No SQL/identity/destination CLI input.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from .route_validation import validate_route, route_audit

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'docs/design/stage4-r0-execution/recovery-preparation/comparison-80-manifest.json'
MANIFEST_SHA = 'cf31d3a5dd69da7c65348428473a0bb15cf38071caab41b5db76b6d5ea8845cd'
WORKFLOW = '.github/workflows/stage4-r0-identity-comparison-once.yml'
AUTHORITY = 'AUTHORISE_R0_FIXED_80_IDENTITY_COMPARISON_ONCE'


def identities():
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('COMPARISON_MANIFEST_REJECTED') from None
    rows = json.loads(raw)['identities']
    if (len(rows) != 80 or len({(x['council_code'], x['reference']) for x in rows}) != 80
            or sum(x['council_code'] == 'bolton' for x in rows) != 54
            or sum(x['council_code'] == 'bury' for x in rows) != 26):
        raise ValueError('COMPARISON_MANIFEST_REJECTED') from None
    return rows


def admit(env, sha, manifest_sha, authority):
    expected = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
        GITHUB_REPOSITORY='maxrose26/PropertyAIgent', GITHUB_EVENT_NAME='workflow_dispatch',
        GITHUB_REF='refs/heads/master', GITHUB_SHA=sha, GITHUB_WORKFLOW_SHA=sha,
        GITHUB_WORKFLOW_REF=f'maxrose26/PropertyAIgent/{WORKFLOW}@refs/heads/master',
        GITHUB_RUN_NUMBER='1', GITHUB_RUN_ATTEMPT='1')
    if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha)
            or manifest_sha != MANIFEST_SHA or authority != AUTHORITY
            or any(env.get(k) != v for k, v in expected.items())):
        raise ValueError('COMPARISON_ADMISSION_REJECTED') from None
    identities()


def statement(rows=None):
    # Parameter names are generated internally; literals never become SQL.
    rows = identities() if rows is None else rows; params = {}
    values = []
    for n, row in enumerate(rows):
        values.append(f'(:c{n}, :r{n})')
        params[f'c{n}'] = row['council_code']; params[f'r{n}'] = row['reference']
    sql = '''WITH requested(council_code, reference) AS (VALUES ''' + ','.join(values) + ''')
SELECT statement_timestamp() AS snapshot_timestamp, r.council_code, r.reference,
       COALESCE(m.matches, '[]'::jsonb) AS matches,
       COALESCE(m.n, 0) AS matching_rows_up_to_two
FROM requested r
LEFT JOIN LATERAL (
 SELECT jsonb_agg(jsonb_build_object('id', x.id, 'council_code', x.council_code,
        'reference', x.reference) ORDER BY x.id) AS matches, count(*) AS n
 FROM (SELECT a.id, a.council_code, a.reference FROM public.applications a
       WHERE a.council_code = r.council_code AND a.reference = r.reference
       ORDER BY a.id LIMIT 2) x
) m ON TRUE ORDER BY r.council_code, r.reference'''
    return sql, params


def query(connection, audit=None, *, exact_rows=None, output_bound=100_000):
    """One explicit read-only transaction; success/failure always ROLLBACK."""
    from sqlalchemy import text
    audit = {} if audit is None else audit
    begun = False
    try:
        connection.exec_driver_sql('BEGIN READ ONLY'); begun = True
        audit['transaction'] = 'READ_ONLY_BEGUN'
        connection.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
        connection.exec_driver_sql("SET LOCAL idle_in_transaction_session_timeout = '20s'")
        if connection.exec_driver_sql('SHOW transaction_read_only').scalar_one() != 'on':
            raise ValueError('READ_ONLY_NOT_CONFIRMED')
        audit['read_only_confirmed'] = True
        requested=identities() if exact_rows is None else exact_rows
        sql, params = statement(requested)
        rows = list(connection.execute(text(sql), params).mappings())
        expected = {(x['council_code'], x['reference']) for x in requested}
        if len(rows) != len(requested) or {(x['council_code'], x['reference']) for x in rows} != expected:
            raise ValueError('COMPARISON_RESULT_REJECTED')
        result = []
        stamps = set()
        for row in rows:
            matches = row['matches']; n = row['matching_rows_up_to_two']
            stamps.add(str(row['snapshot_timestamp']))
            if not isinstance(matches, list) or type(n) is not int or n not in (0, 1, 2) or len(matches) != n:
                raise ValueError('COMPARISON_RESULT_REJECTED')
            for match in matches:
                if (set(match) != {'id', 'council_code', 'reference'} or type(match['id']) is not int
                        or match['council_code'] != row['council_code'] or match['reference'] != row['reference']):
                    raise ValueError('COMPARISON_RESULT_REJECTED')
            if len({match['id'] for match in matches}) != n:
                raise ValueError('COMPARISON_RESULT_REJECTED')
            result.append(dict(council_code=row['council_code'], reference=row['reference'],
                matching_rows_up_to_two=n, matches=matches,
                outcome=('ABSENT', 'ONE_MATCH', 'DUPLICATE_DETECTED')[n]))
        if len(stamps) != 1:
            raise ValueError('COMPARISON_RESULT_REJECTED')
        out = dict(snapshot_timestamp=stamps.pop(), requested_identities=len(requested),
            comparison=result, transaction='READ_ONLY_ROLLED_BACK', production_writes=0,
            source_requests=0, admission_calls=0)
        if len(json.dumps(out).encode()) > output_bound:
            raise ValueError('OUTPUT_LIMIT')
        return out
    finally:
        if begun:
            audit['transaction'] = 'READ_ONLY_END_NOT_CONFIRMED'
            connection.exec_driver_sql('ROLLBACK')
            audit['transaction'] = 'READ_ONLY_ROLLED_BACK'


def run(raw):
    return run_exact(raw,None)

def run_exact(raw,exact_rows,*,output_bound=100_000):
    """Validate exact destination before engine creation; no exception text leaves."""
    if exact_rows is not None and (not isinstance(exact_rows,list) or not 1<=len(exact_rows)<=1000 or any(set(r)!={'council_code','reference'} or not isinstance(r['reference'],str) or not 1<=len(r['reference'])<=100 for r in exact_rows) or len({(r['council_code'],r['reference']) for r in exact_rows})!=len(exact_rows)):
        raise ValueError('EXACT_COHORT_REJECTED')
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    engine = None
    audit = dict(route_validation=route_audit(raw), transaction='NOT_STARTED',
                 production_writes=0, source_requests=0, admission_calls=0,
                 connection_attempts=0, connected=False, read_only_confirmed=False)
    try:
        url = validate_route(raw)
        engine = create_engine(url, poolclass=NullPool, isolation_level='AUTOCOMMIT',
            connect_args=dict(connect_timeout=5, sslmode='require',
                options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=20000'))
        audit['phase'] = 'CONNECTION_REQUESTED'
        audit['connection_attempts'] = 1
        with engine.connect() as connection:
            audit['connected'] = True
            audit['phase'] = 'READ_ONLY_COMPARISON_REQUESTED'
            result = query(connection, audit,exact_rows=exact_rows,output_bound=output_bound)
            audit.update(result)
        audit['result'] = 'COMPLETED'
    except Exception:
        audit.update(result='FAILED', error_code='COMPARISON_FAILED_NO_RETRY')
    finally:
        try:
            if engine is not None:
                engine.dispose()
            audit['engine_disposed'] = True
        except Exception:
            audit.update(result='FAILED', error_code='DISPOSAL_FAILED_NO_RETRY', engine_disposed=False)
    return audit


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--reviewed-sha', required=True); p.add_argument('--manifest-sha', required=True)
    p.add_argument('--authority', required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    admit(os.environ, args.reviewed_sha, args.manifest_sha, args.authority)
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() != args.reviewed_sha
            or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
            or args.output.exists()):
        raise ValueError('CHECKOUT_OR_OUTPUT_REJECTED') from None
    out = run(os.environ.pop('COMPARISON_DATABASE_URL', ''))
    out.update(sha=args.reviewed_sha, manifest_sha256=MANIFEST_SHA,
               run_id=os.environ['GITHUB_RUN_ID'], run_number=1, attempt=1)
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(out, sort_keys=True)+'\n')
    if out['result'] != 'COMPLETED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
