"""Owner pilot configuration readback. Never activates access or starts a job.

The configured secret stays inside the existing web process. Only bounded,
nonsecret capability facts are logged; no exception messages are exported.
"""
import hashlib
import json
import os
from pathlib import Path
import time

SERVICE = 'crn-d9sv93vavr4c73f98rb0'
ROOT_SHA = '700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7'

def configuration_readback(environ=None, *, connect=None, session=None):
    env = os.environ if environ is None else environ
    out = dict(version='OWNER_INTAKE_CONFIGURATION_V1', database_configured=bool(env.get('DATABASE_URL')),
               render_key_configured=bool(env.get('PROPERTYAIGENT_INTAKE_RENDER_API_KEY')),
               database_mutations=0, provider_mutations=0, requests=0, database_closed=False)
    started = time.monotonic()
    try:
        from sqlalchemy.engine import make_url
        from psycopg import connect as native_connect
        u = make_url(env.get('DATABASE_URL', 'sqlite://'))
        if u.get_backend_name() not in ('postgres', 'postgresql'):
            out['database_status'] = 'CONFIGURED_POSTGRES_REQUIRED'
        elif (u.host != 'aws-0-eu-west-2.pooler.supabase.com' or u.port not in (5432,6543)
              or u.database != 'postgres' or not (u.username or '').endswith('.zcikcfgpblzuzpanpdqd')):
            out['database_status'] = 'CONFIGURED_REVIEWED_PROJECT_ROUTE_REQUIRED'
        else:
            ca = Path(__file__).with_name('owner_intake_ca.crt')
            if hashlib.sha256(ca.read_bytes()).hexdigest() != ROOT_SHA:
                raise ValueError()
            out['database_port'] = u.port
            with (connect or native_connect)(host=u.host, port=u.port, dbname=u.database,
                    user=u.username, password=u.password, sslmode='verify-full', sslrootcert=str(ca),
                    connect_timeout=5, gssencmode='disable', prepare_threshold=None, autocommit=True,
                    options='-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000') as c:
                c.execute('BEGIN READ ONLY')
                try:
                    row = c.execute("SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,pg_has_role(current_user,'pg_read_all_stats','USAGE') FROM pg_roles WHERE rolname=current_user").fetchone()
                    out['database_identity'] = dict(zip(('current_user','session_user','superuser','create_role','create_database','bypass_rls','read_all_stats'),row))
                    out['database_status'] = 'SERVER_IDENTITY_VERIFIED'
                    out['session_mode_owner_route'] = u.port == 5432 and row[:2] == ('postgres','postgres')
                    out['evidence_table_present'] = c.execute("SELECT to_regclass('public.ingestion_run_evidence') IS NOT NULL").fetchone()[0]
                finally:
                    c.execute('ROLLBACK')
            out['database_closed'] = c.closed
    except Exception as exc:
        out['database_status'] = 'CONFIGURATION_READBACK_REFUSED'
        state = getattr(exc,'sqlstate',None)
        if state in ('42501','28P01','28000','57014'): out['database_sqlstate'] = state
    if env.get('PROPERTYAIGENT_INTAKE_RENDER_API_KEY'):
        s = None
        try:
            import requests
            s = session or requests.Session(); s.trust_env = False
            out['requests'] = 1
            with s.get('https://api.render.com/v1/services/'+SERVICE,
                       headers={'Authorization':'Bearer '+env['PROPERTYAIGENT_INTAKE_RENDER_API_KEY'],'Accept':'application/json'},
                       timeout=(3,5), allow_redirects=False, stream=True) as r:
                out['render_http_status'] = r.status_code
                if r.status_code == 200:
                    raw = bytearray()
                    for chunk in r.iter_content(4096):
                        raw.extend(chunk)
                        if len(raw)>32768 or time.monotonic()-started>=40: raise ValueError()
                    v=json.loads(raw)
                    out['render_status']='EXACT_SERVICE_READ_VERIFIED' if v.get('id')==SERVICE else 'SERVICE_BINDING_REFUSED'
                    out['scraper_suspended']=v.get('suspended')=='suspended'
                    out['scraper_auto_deploy_off']=v.get('autoDeploy')=='no'
                else: out['render_status']='HTTP_REFUSED'
        except Exception:
            out['render_status']='READBACK_UNCERTAIN'
        finally:
            if s is not None: s.close()
    out['elapsed_ms']=min(60000,int((time.monotonic()-started)*1000))
    return out

def startup_configuration_readback():
    """One server startup readback; no page-load schema or lifecycle effect."""
    if os.environ.get('PROPERTYAIGENT_INTAKE_RENDER_API_KEY'):
        print('PROPERTYAIGENT_PILOT_CAPABILITY_READBACK '+json.dumps(configuration_readback(),sort_keys=True),flush=True)
