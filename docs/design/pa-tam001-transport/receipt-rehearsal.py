"""Harmless transport rehearsal only. No database, environment reads or network."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def save(path, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    fd = os.open(str(path) + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(path) + '.tmp', path)


def main():
    action, directory = sys.argv[1:]
    root = Path(directory)
    if action == 'read':
        for name in ('ack.json', 'completion.json'):
            p = root / name
            print(p.read_text() if p.is_file() else json.dumps({'missing': name}))
        return
    if action == 'start':
        os.umask(0o077)
        root.mkdir(mode=0o700)  # Existing ID always refuses, never replays.
        source = Path(__file__).read_bytes()
        save(root / 'ack.json', {'id': root.name, 'kind': 'REHEARSAL_ACCEPTED',
             'script_sha256': hashlib.sha256(source).hexdigest(), 'database_connections': 0})
        with (root / 'worker.log').open('xb') as log:
            subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                              'finish', str(root.resolve())], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True, close_fds=True)
        print((root / 'ack.json').read_text(), flush=True)
        return
    if action != 'finish':
        raise SystemExit('UNSUPPORTED_ACTION')
    signal.alarm(10)
    time.sleep(3)
    save(root / 'completion.json', {'id': root.name, 'kind': 'REHEARSAL_COMPLETED',
         'database_connections': 0, 'sql_statements': 0, 'fixture': 'harmless',
         'ack_sha256': hashlib.sha256((root / 'ack.json').read_bytes()).hexdigest()})


if __name__ == '__main__':
    main()
