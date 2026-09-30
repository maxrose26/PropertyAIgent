"""Runner-only disposable infrastructure. Never imported by application code."""
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import psycopg
from psycopg import sql
from app.db.ah_disposable_postgres import filesystem_proof, create_disposable_engine


def write_proof(path, value):
    with open(path, 'x', opener=lambda p, flags: os.open(p,flags,0o600)) as f:
        json.dump(value,f,indent=2)


def initial_proof(root, host_netns, pg_bin):
    root=Path(root).resolve()
    lines=(root/'pgdata/postmaster.pid').read_text().splitlines()
    control=subprocess.check_output([str(Path(pg_bin)/'pg_controldata'),str(root/'pgdata')],text=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    system_id=re.search(r'Database system identifier:\s*(\d+)',control).group(1)
    m=dict(run_id=uuid.uuid4().hex,root=str(root),system_identifier=system_id,port=55439,
           host_netns=host_netns,netns=os.readlink('/proc/self/ns/net'),server_pid=int(lines[0]),server_start=int(lines[2]))
    write_proof(root/'cluster.json',m)
    # Check filesystem and connected cluster identity before ANY database/role/schema DDL.
    with verified_admin(m,'postgres') as c:
        role='ah_writer_'+m['run_id'][:16]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(role)))
    return m


def verified_admin(m,database):
    filesystem_proof(m)
    if database!='postgres' and not re.fullmatch('ah_case_[0-9a-f]{32}',database):
        raise ValueError('Unexpected administrative database')
    c=psycopg.connect(host='127.0.0.1',port=m['port'],user='ah_cluster_owner',dbname=database,connect_timeout=5,autocommit=True)
    try:
        row=c.execute("SELECT (SELECT system_identifier::text FROM pg_control_system()), current_setting('data_directory'), inet_server_addr()::text, inet_server_port(), floor(extract(epoch FROM pg_postmaster_start_time()))::bigint, current_user, current_database()").fetchone()
        if row!=(m['system_identifier'],str(Path(m['root'])/'pgdata'),'127.0.0.1/32',m['port'],m['server_start'],'ah_cluster_owner',database):
            raise ValueError('Administrative cluster identity mismatch')
        return c
    except BaseException:
        c.close(); raise


def provision_case(root):
    root=Path(root)
    m=json.loads((root/'cluster.json').read_text())
    m.update(database='ah_case_'+uuid.uuid4().hex,role='ah_writer_'+m['run_id'][:16])
    db,role=sql.Identifier(m['database']),sql.Identifier(m['role'])
    with verified_admin(m,'postgres') as c:
        c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(db))
        c.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(db))
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(db,role))
        m['database_oid']=c.execute('SELECT oid FROM pg_database WHERE datname=%s',(m['database'],)).fetchone()[0]
    with verified_admin(m,m['database']) as c:
        c.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
        c.execute(sql.SQL('GRANT USAGE, CREATE ON SCHEMA public TO {}').format(role))
        c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION pg_control_system() TO {}').format(role))
    path=root/(m['database']+'.json')
    write_proof(path,m)
    engine=create_disposable_engine(path)
    engine._ah_test_manifest=path  # Test locator only; never treated as authority.
    return engine,m


def destroy_case(engine,m):
    engine.dispose()
    with verified_admin(m,'postgres') as c:
        c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(m['database'])))
