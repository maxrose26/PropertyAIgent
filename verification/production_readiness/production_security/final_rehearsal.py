"""Exact-artifact PG17 rehearsal, only through final_guard.Authority.

Any migration failure is terminal. Never rewrites SQL or retries an altered artifact.
Synthetic insert policies are a separate disposable-only phase after dark verification.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from .final_guard import Authority,BOOTSTRAP,PASSWORD
from verification.production_readiness.native_exporter import export_catalog
from verification.production_readiness.catalog_verifier import compare,digest
from verification.production_readiness.native_rehearsal import claim_insert,event_insert,evidence_hash
P=Path(__file__).parent
R=P.parent
MIG='c01d6457b7e165dd968cc93d55d0112d04606a7f9f5a595f0d2fe5b316631386'
EXP='b08ffd876d817b0f092d58a1da93124ae4cda0d2fd8efc2412c57a5355fe51be'
AH=['ah_evidence_owner','ah_evidence_reader','ah_evidence_importer','ah_document_registrar']
ROLES=AH+['postgres','anon','authenticated','service_role','authenticator','ah_final_nobody',BOOTSTRAP]
AREAS=['fresh-install','verifier','roles-default-grants','column-grants','rls-policy','append-only','drift-repeatability','disable-rollback']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def integrity():
    if sha(P/'004_production_proposal.sql')!=MIG or sha(R/'expected_schema.json')!=EXP:
        raise ValueError('Approved artifact/schema hash mismatch')
    contract=json.loads((P/'final_contract.json').read_text())
    root=R.parents[1]
    for name,h in contract.items():
        if sha(root/name)!=h:raise ValueError('Runner input hash mismatch: '+name)
    return contract

def parents(c):
    return {'data':{t:c.execute('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY id').fetchall() for t in ('applications','sites','documents')},
    'acl':c.execute("SELECT relname,relacl::text FROM pg_class WHERE oid IN ('applications'::regclass,'sites'::regclass,'documents'::regclass) ORDER BY 1").fetchall(),
    'columns':c.execute("SELECT attrelid::regclass::text,attname,attacl::text FROM pg_attribute WHERE attrelid IN ('applications'::regclass,'sites'::regclass,'documents'::regclass) AND attnum>0 ORDER BY 1,2").fetchall(),
    'schema':c.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='public'").fetchall(),
    'defaults':c.execute("SELECT defaclnamespace::regnamespace::text,defaclobjtype,defaclacl::text FROM pg_default_acl WHERE defaclrole='postgres'::regrole ORDER BY 1,2").fetchall()}

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    checks=[];reports={a:{'status':'NOT_RUN','reason':'earlier gate not completed'} for a in AREAS};auth=None;phase='guard';installed=False
    def write(n,v):(out/n).write_text(json.dumps(v,indent=2,default=str)+'\n')
    def ok(name,**kw):checks.append(dict(case=name,status='PASS',**kw))
    def deny(c,name,sql,states=('42501',)):
        try:c.execute(sql)
        except auth.driver.Error as e:
            if e.sqlstate not in states:raise AssertionError(name+': wrong SQLSTATE '+str(e.sqlstate)) from e
            ok(name,sqlstate=e.sqlstate,message=str(e).splitlines()[0]);return
        raise AssertionError(name+': forbidden operation succeeded')
    try:
        integrity();ok('exact-artifact-and-tooling-hashes')
        root=R.parents[1]
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        if head!=os.environ.get('GITHUB_SHA') or subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():raise ValueError('Dirty/wrong-SHA checkout')
        auth=Authority(os.environ,root);ok('container-cluster-identity-and-PG17.6')
        from psycopg import sql
        with auth.connect(BOOTSTRAP) as c:
            version=c.execute('SELECT version()').fetchone()[0]
            write('versions.json',{'postgresql':version,'python':platform.python_version(),'psycopg':auth.driver.__version__,'run_id':os.environ['GITHUB_RUN_ID'],'commit_sha':head,'artifact_sha256':MIG,'expected_schema_sha256':EXP,'cluster':auth.service})
            if c.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(ROLES[:-1],)).fetchall():raise ValueError('Pre-existing fixture role')
            c.execute(sql.SQL('CREATE ROLE postgres LOGIN NOSUPERUSER INHERIT CREATEROLE CREATEDB REPLICATION BYPASSRLS PASSWORD {}').format(sql.Literal(PASSWORD)))
            c.execute('GRANT pg_read_all_data,pg_monitor,pg_signal_backend,pg_create_subscription TO postgres')
            c.execute('GRANT EXECUTE ON FUNCTION pg_control_system() TO postgres')
            for role in ('anon','authenticated','service_role','authenticator','ah_final_nobody'):
                c.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER {} NOCREATEDB NOCREATEROLE NOREPLICATION {}').format(sql.Identifier(role),sql.SQL('NOINHERIT' if role=='authenticator' else 'INHERIT'),sql.SQL('BYPASSRLS' if role=='service_role' else 'NOBYPASSRLS')))
            c.execute('GRANT anon,authenticated,service_role TO authenticator WITH INHERIT FALSE, SET TRUE')
            c.execute('GRANT anon,authenticated,authenticator,service_role TO postgres')
            c.execute('ALTER DATABASE postgres OWNER TO postgres')
            c.execute('CREATE DATABASE ah_final_reference OWNER postgres TEMPLATE template0')
        for db in ('postgres','ah_final_reference'):
            auth.register(db)
            with auth.connect(db,'postgres') as c:
                c.execute('GRANT USAGE ON SCHEMA public TO PUBLIC')
                c.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT TRUNCATE,REFERENCES,TRIGGER,MAINTAIN ON TABLES TO anon,authenticated,service_role')
                c.execute('CREATE TABLE applications(id SERIAL PRIMARY KEY, legacy_ah integer); CREATE TABLE sites(id SERIAL PRIMARY KEY, legacy_ah integer); CREATE TABLE documents(id SERIAL PRIMARY KEY, fixture text)')
                c.execute("INSERT INTO applications VALUES(1,30),(2,0); INSERT INTO sites VALUES(1,30); INSERT INTO documents VALUES(1,'SYNTHETIC ONLY')")
        ok('production-shaped-fixture-created')
        phase='preinstall-rejection'
        with auth.connect('postgres','postgres') as c:
            for label,change in [('partial-install','CREATE TABLE ah_source_claims(id integer)'),('wrong-parent-type','ALTER TABLE applications ALTER COLUMN id TYPE bigint')]:
                c.execute('BEGIN');c.execute(change)
                deny(c,label,(P/'004_production_proposal.sql').read_text(),('P0001',));c.execute('ROLLBACK')
        phase='fresh-install'
        with auth.connect('postgres','postgres') as c:
            before=parents(c);write('parent-baseline.json',before)
            try:c.execute((P/'004_production_proposal.sql').read_text(),prepare=False)
            except auth.driver.Error as e:
                c.execute('ROLLBACK')
                after=parents(c)
                newroles=c.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(AH,)).fetchall()
                newobjects=c.execute("SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND (starts_with(relname,'ah_') OR starts_with(relname,'ix_ah_'))").fetchall()
                rollback={'parents_unchanged':before==after,'new_roles':newroles,'new_objects':newobjects}
                write('failed-install-rollback.json',rollback)
                reports['fresh-install']={'status':'FAIL','sqlstate':e.sqlstate,'message':str(e),'rollback':rollback}
                if before==after and not newroles and not newobjects:ok('failed-install-atomic-rollback')
                raise
            installed=True
            if parents(c)!=before:raise AssertionError('Parent data/ACL/default changed')
            ok('fresh-install-parent-state-unchanged');reports['fresh-install']={'status':'PASS'}
            c.execute((P/'005_verify_security.sql').read_text(),prepare=False);ok('security-supplement')
        expected=json.loads((R/'expected_schema.json').read_text());payload={k:v for k,v in expected.items() if not k.startswith('_')};ddl=digest(payload)
        # Independent canonical schema JSON plus independently specified security, never copied target catalogue.
        phase='verifier'
        with auth.connect('ah_final_reference') as c:
            c.execute('GRANT USAGE,CREATE ON SCHEMA public TO ah_evidence_owner; GRANT REFERENCES(id) ON applications,sites,documents TO ah_evidence_owner')
            c.execute('SET ROLE ah_evidence_owner')
            c.execute('ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC')
            for obj in payload.values():
                c.execute(obj['ddl'])
                for index in obj['indexes']:c.execute(index)
            c.execute((R/'reference_security.sql').read_text())
            for t in ('ah_source_claims','ah_claim_events'):c.execute('ALTER TABLE '+t+' ENABLE ROW LEVEL SECURITY; ALTER TABLE '+t+' FORCE ROW LEVEL SECURITY')
            c.execute('RESET ROLE; REVOKE REFERENCES(id) ON applications,sites,documents FROM ah_evidence_owner; REVOKE USAGE,CREATE ON SCHEMA public FROM ah_evidence_owner')
        def snap(c,writable=False):
            if writable:return export_catalog(c,ROLES,MIG,ddl,allow_writable_snapshot=True)
            with c.transaction():
                c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                return export_catalog(c,ROLES,MIG,ddl)
        with auth.connect('ah_final_reference') as c:reference=snap(c)
        bound=copy.deepcopy(expected);bound['_native_verifier']={'reference_sha256':digest(reference),'migration_sha256':MIG,'server_version_num':170006,'role_names':ROLES}
        write('reference-catalogue.json',reference);write('bound-expected-schema.json',bound)
        with auth.connect() as c:
            actual=snap(c);write('catalogue.json',actual);v=compare(bound,actual,reference);write('verifier.json',v)
            if v['status']!='PASS':raise AssertionError('Catalogue difference: '+str(v['differences']))
            ok('full-native-catalogue-equality');reports['verifier']=v
            for section,area in [('roles','roles-default-grants'),('acl','column-grants'),('policies','rls-policy')]:reports[area]={'status':'PASS','catalogue_section':section}
        phase='drift-repeatability'
        with auth.connect('postgres','postgres') as c:
            deny(c,'second-install-rejected',(P/'004_production_proposal.sql').read_text(),('P0001',));c.execute('ROLLBACK')
        drifts=[('extra-column','ALTER TABLE ah_source_claims ADD COLUMN extra integer'),('wrong-type','ALTER TABLE ah_source_claims ALTER COLUMN scope_label TYPE text'),('missing-check','ALTER TABLE ah_source_claims DROP CONSTRAINT ah_stage'),('missing-index','DROP INDEX ix_ah_payload'),('missing-trigger','DROP TRIGGER ah_source_claims_deny_mutation ON ah_source_claims'),('column-grant','GRANT SELECT(passage_text) ON ah_source_claims TO anon'),('table-grant','GRANT SELECT ON ah_source_claims TO authenticated'),('sequence-grant','GRANT USAGE ON SEQUENCE ah_source_claims_id_seq TO anon'),('function-grant','GRANT EXECUTE ON FUNCTION ah_deny_mutation() TO PUBLIC'),('policy','CREATE POLICY drift ON ah_source_claims USING(true)'),('rls','ALTER TABLE ah_source_claims DISABLE ROW LEVEL SECURITY'),('default-grant','ALTER DEFAULT PRIVILEGES FOR ROLE ah_evidence_owner GRANT SELECT ON TABLES TO anon')]
        with auth.connect() as c:
            for name,q in drifts:
                c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ');c.execute(q)
                v=compare(bound,snap(c,True),reference);c.execute('ROLLBACK')
                if v['status']!='FAIL':raise AssertionError('Drift accepted: '+name)
                ok('drift-'+name,differences=v['differences'])
            for h in ('migration_sha256','expected_ddl_sha256'):
                bad=copy.deepcopy(actual);bad[h]='wrong'
                if compare(bound,bad,reference)['status']!='FAIL':raise AssertionError('Hash mismatch accepted')
                ok('drift-'+h)
        reports['drift-repeatability']={'status':'PASS','partial_install':'rejected before fresh install','second_install':'deliberately rejected without changes'}
        # All dark roles remain NOLOGIN; SET ROLE from private bootstrap tests effective rights without altering membership.
        for role in AH[1:]+['anon','authenticated','service_role','authenticator','ah_final_nobody']:
            with auth.connect() as c:
                c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
                for t in ('ah_source_claims','ah_claim_events'):
                    for q in ('SELECT * FROM '+t,'INSERT INTO '+t+' DEFAULT VALUES','UPDATE '+t+' SET id=id','DELETE FROM '+t,'TRUNCATE '+t,'ALTER TABLE '+t+' OWNER TO '+role):deny(c,role+':'+q,q)
                deny(c,role+':sequence',"SELECT nextval('ah_source_claims_id_seq')")
                deny(c,role+':bypass','ALTER ROLE '+role+' BYPASSRLS') if role in AH[1:] else None
        with auth.connect() as c:
            c.execute('BEGIN; GRANT SELECT,INSERT ON ah_source_claims TO ah_evidence_importer; GRANT USAGE ON SEQUENCE ah_source_claims_id_seq TO ah_evidence_importer; SET LOCAL ROLE ah_evidence_importer')
            try:claim_insert(c,'no-policy')
            except auth.driver.Error as e:
                if e.sqlstate!='42501' or 'row-level security' not in str(e).lower():raise
                ok('no-policy-rls-insert-denied',sqlstate=e.sqlstate)
            else:raise AssertionError('RLS permitted insert with no policy')
            finally:c.execute('ROLLBACK')
        phase='append-only'
        fixture=(R/'local_role_probe.sql').read_text().replace('ah_ci_reader','ah_evidence_reader').replace('ah_ci_importer','ah_evidence_importer').replace('ah_ci_registrar','ah_document_registrar')
        with auth.connect() as c:c.execute(fixture)
        with auth.connect() as c:
            c.execute('SET ROLE ah_evidence_importer')
            a=claim_insert(c);b=claim_insert(c,'two');ea=event_insert(c,a,'ACCEPT');eb=event_insert(c,b,'ACCEPT');event_insert(c,a,'SUPERSEDE',2,ea,b);event_insert(c,b,'WITHDRAW',2,eb);d=claim_insert(c,'three');event_insert(c,d,'CORRECT',related=b);ok('synthetic-append-history')
        with auth.connect() as c:
            c.execute('SET ROLE ah_evidence_reader')
            if c.execute('SELECT count(*) FROM ah_source_claims').fetchone()[0]!=3:raise AssertionError('Enabled bounded reader failed')
            deny(c,'reader-insert-denied','INSERT INTO ah_source_claims DEFAULT VALUES');ok('bounded-reader-positive')
        with auth.connect() as c:
            before=evidence_hash(c)
            for t in ('ah_source_claims','ah_claim_events'):
                for q in ('UPDATE '+t+' SET id=id','DELETE FROM '+t):deny(c,'trigger:'+q,q,('P0001',))
            deny(c,'fk-truncate','TRUNCATE ah_source_claims',('0A000',))
            deny(c,'trigger-truncate-pair','TRUNCATE ah_source_claims,ah_claim_events',('P0001',))
            deny(c,'trigger-truncate-events','TRUNCATE ah_claim_events',('P0001',))
            if evidence_hash(c)!=before:raise AssertionError('Mutation changed evidence')
            reports['append-only']={'status':'PASS','before':before,'after':evidence_hash(c)}
        phase='disable-rollback'
        with auth.connect() as writer,auth.connect() as c:
            before=evidence_hash(c);writer.execute('SET ROLE ah_evidence_importer; BEGIN');claim_insert(writer,'inflight')
            c.execute('BEGIN');deny(c,'inflight-disable-lock','LOCK TABLE ah_source_claims IN ACCESS EXCLUSIVE MODE',('55P03',));c.execute('ROLLBACK');writer.execute('ROLLBACK')
            c.execute('BEGIN; LOCK TABLE ah_source_claims,ah_claim_events IN ACCESS EXCLUSIVE MODE')
            c.execute('REVOKE ALL ON ah_source_claims,ah_claim_events FROM ah_evidence_reader,ah_evidence_importer; REVOKE ALL ON SEQUENCE ah_source_claims_id_seq,ah_claim_events_id_seq FROM ah_evidence_importer')
            for t,policies in [('ah_source_claims',['fixture_claim_read','fixture_claim_append']),('ah_claim_events',['fixture_event_read','fixture_event_append'])]:
                for policy in policies:c.execute('DROP POLICY '+policy+' ON '+t)
            c.execute('REVOKE INSERT ON documents FROM ah_document_registrar; COMMIT')
            if evidence_hash(c)!=before:raise AssertionError('Disable changed evidence')
            reports['disable-rollback']={'status':'PASS','before':before,'after':evidence_hash(c)}
        for role in AH[1:3]:
            with auth.connect() as c:
                c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
                deny(c,role+':disabled-read','SELECT * FROM ah_source_claims');deny(c,role+':disabled-write','INSERT INTO ah_source_claims DEFAULT VALUES')
        # Do not silently call partial coverage full acceptance.
        if any(v['status']!='PASS' for v in reports.values()):raise AssertionError('Incomplete native acceptance areas')
        write('overall.json',{'status':'PASS_NATIVE_NOT_PRODUCTION_APPROVAL','checks':len(checks)})
    except BaseException as e:
        write('overall.json',{'status':'FAILED_OR_BLOCKED','phase':phase,'error_type':type(e).__name__,'message':str(e),'sqlstate':getattr(e,'sqlstate',None),'artifact_unmodified':sha(P/'004_production_proposal.sql')==MIG})
        raise
    finally:
        write('checks.json',checks)
        for a,v in reports.items():write(a+'-report.json',v)
        cleanup={'service_stop':'workflow always-step required','production_access':False}
        if auth:
            try:
                with auth.connect(BOOTSTRAP) as c:
                    for db in ('ah_final_reference','postgres'):
                        if db in auth.allowed:c.execute('DROP DATABASE '+db+' WITH (FORCE)')
                cleanup['disposable_databases_dropped']=True
            except Exception as e:cleanup['error']=str(e)
        write('cleanup.json',cleanup)
        write('evidence-checksums.json',{f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='evidence-checksums.json'})
        if cleanup.get('error'):raise RuntimeError('Cleanup failed')

if __name__=='__main__':main(Path(sys.argv[1]))
