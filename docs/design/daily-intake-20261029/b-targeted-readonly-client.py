"""Fixed psql invocation for b-targeted-readonly.sql; not a lifecycle/repair controller.

Inactive until separately approved. Stdlib only. Output is private evidence,
never an automatic B approval. Remote closure after forced exit is UNKNOWN.
"""
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

SQL_SHA = '03ad0a79b0d0d21ec213d72a67be406f0fdeabe748d40e064274075efbc00f62'
HOST = 'aws-0-eu-west-2.pooler.supabase.com'
USER = 'postgres.zcikcfgpblzuzpanpdqd'
LIMIT = 65536


def capture(command, environment, *, seconds=60, ceiling=LIMIT):
    """One process, combined pipe, finite bytes; TERM at deadline-2, KILL at -1."""
    start = time.monotonic()
    p = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    data = bytearray()
    reason = None
    term = None
    eof = False
    try:
        with selectors.DefaultSelector() as poll:
            poll.register(p.stdout, selectors.EVENT_READ)
            while not eof or p.poll() is None:
                now = time.monotonic()
                if reason is None and now-start >= seconds-2:
                    reason = 'DEADLINE'
                if reason and term is None:
                    term = now
                    try: os.killpg(p.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                if term is not None and now-term >= 1:
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                if now-start >= seconds-.2:
                    reason = reason or 'CLOSURE_UNCERTAIN'
                    break
                for key, _ in poll.select(.025):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        poll.unregister(key.fileobj)
                        eof = True
                    else:
                        remaining = ceiling-len(data)
                        data.extend(chunk[:remaining])
                        if len(chunk)>remaining: reason = 'OUTPUT_OVERFLOW'
        p.stdout.close()
        if p.poll() is None:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        try: code = p.wait(timeout=.1)
        except subprocess.TimeoutExpired: code = None
    finally:
        # Also reap on local exceptions/cancellation. This is not remote proof.
        if p.poll() is None:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            try: p.wait(timeout=.1)
            except subprocess.TimeoutExpired: pass
        p.stdout.close()
    return bytes(data), dict(exit_code=code, reason=reason,
        client_closed=code is not None, output_bytes=len(data),
        remote_closure='NOT_ACKNOWLEDGED' if reason or code else 'NORMAL_PSQL_EXIT',
        classification='INCOMPLETE' if reason or code else 'OBSERVATIONS_REQUIRE_REVIEW')


def main():
    os.umask(0o077)
    sql = Path(__file__).with_name('b-targeted-readonly.sql')
    if hashlib.sha256(sql.read_bytes()).hexdigest()!=SQL_SHA:
        raise SystemExit('STOP: SQL_HASH')
    executable = shutil.which('psql')
    if not executable: raise SystemExit('STOP: psql required')
    print('Requires separate approval. Destination: '+HOST+':5432 / postgres / '+USER)
    address = str(ipaddress.IPv4Address(input('Reviewed IPv4: ').strip()))
    ca = Path(input('Reviewed CA file absolute path: ').strip())
    if not ca.is_absolute() or not ca.is_file(): raise SystemExit('STOP: CA_FILE')
    if input('Approved existing database identity (must be postgres): ').strip()!='postgres':
        raise SystemExit('STOP: IDENTITY')
    output = Path(input('NEW private evidence directory: ').strip()).expanduser()
    output.mkdir(mode=0o700)
    password = getpass.getpass('Existing inspection password (hidden): ')
    if not password or any(c in password for c in '\r\n\x00'):
        raise SystemExit('STOP: PASSWORD_FORMAT')
    with tempfile.TemporaryDirectory(prefix='property-b-pass-') as private:
        passfile = Path(private)/'pgpass'
        escape = lambda s: s.replace('\\','\\\\').replace(':','\\:')
        passfile.write_text(':'.join(map(escape,[HOST,'5432','postgres',USER,password]))+'\n')
        passfile.chmod(0o600)
        del password
        environment = {'PATH':'/usr/bin:/bin', 'HOME':private, 'LANG':'C.UTF-8',
            'PGHOST':HOST, 'PGHOSTADDR':address, 'PGPORT':'5432', 'PGDATABASE':'postgres',
            'PGUSER':USER, 'PGPASSFILE':str(passfile), 'PGSSLMODE':'verify-full',
            'PGGSSENCMODE':'disable',
            'PGSSLROOTCERT':str(ca), 'PGCONNECT_TIMEOUT':'5', 'PGAPPNAME':'propertyaigent-b-targeted-readonly',
            'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=10000'}
        data, status = capture([executable,'-X','-w','--csv','-v','ON_ERROR_STOP=1',
                                '-P','pager=off','-f',str(sql)],environment,ceiling=LIMIT-1024)
    # Evidence cap includes this status record, not just psql bytes.
    summary = (json.dumps(status,sort_keys=True)+'\n').encode()
    if len(data)+len(summary)>LIMIT:
        status.update(classification='INCOMPLETE',reason='COMBINED_EXPORT_OVERFLOW')
        summary=(json.dumps(status,sort_keys=True)+'\n').encode()
        data=data[:LIMIT-len(summary)]
    (output/'psql-output.txt').write_bytes(data)
    (output/'status.json').write_bytes(summary)
    print(status['classification']+'; inspect private evidence locally.')
    return 2 if status['classification']=='INCOMPLETE' else 0


if __name__=='__main__': raise SystemExit(main())
