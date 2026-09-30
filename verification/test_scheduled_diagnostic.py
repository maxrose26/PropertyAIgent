"""Standard-library subprocess checks; no external runtime or DB required."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 40


class DiagnosticTests(unittest.TestCase):
    def run_probe(self, changes=None, phase='identity', offset=0):
        now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset)
        env = dict(PATH=os.environ['PATH'], RENDER='true',
            RENDER_SERVICE_ID='crn-d9sv93vavr4c73f98rb0', RENDER_SERVICE_TYPE='cron',
            RENDER_GIT_COMMIT=SHA, RENDER_INSTANCE_ID='unknown-instance',
            PROPERTYAIGENT_DISCOVERY_ACTIVATED='0', PROPERTYAIGENT_DISCOVERY_DISABLED='1',
            PROPERTYAIGENT_DISCOVERY_MODE='disabled', DATABASE_URL='DO-NOT-PRINT-OR-CONNECT')
        env.update(changes or {})
        begin = time.monotonic()
        result = subprocess.run([sys.executable, '-m', 'scripts.p0a_scheduled_diagnostic',
            '--phase', phase, '--expected-sha', SHA,
            '--not-before', (now-dt.timedelta(seconds=10)).isoformat(),
            '--expires', (now+dt.timedelta(seconds=60)).isoformat()],
            cwd=ROOT, env=env, capture_output=True, timeout=7)
        self.assertLess(time.monotonic()-begin, 7)
        self.assertNotIn(b'DO-NOT-PRINT', result.stdout + result.stderr)
        self.assertEqual(result.stderr, b'')
        record = json.loads(result.stdout)
        self.assertFalse(record['database_access'])
        return result.returncode, record

    def test_uncertain_identity_stops_before_database(self):
        code, record = self.run_probe()
        self.assertEqual(code, 3)
        self.assertFalse(record['scheduled_origin_verified'])

    def test_wrong_context_sha_and_configuration(self):
        for key, value in [('RENDER', 'false'), ('RENDER_SERVICE_ID', 'other'),
            ('RENDER_SERVICE_TYPE', 'worker'), ('RENDER_GIT_COMMIT', 'b'*40),
            ('RENDER_INSTANCE_ID', 'shl-temporary'), ('RENDER_INSTANCE_ID', ''),
            ('PROPERTYAIGENT_DISCOVERY_ACTIVATED', '1'),
            ('PROPERTYAIGENT_DISCOVERY_DISABLED', '0'),
            ('PROPERTYAIGENT_DISCOVERY_MODE', 'bounded'),
            ('PROPERTYAIGENT_DISCOVERY_DISABLED', 'invalid')]:
            with self.subTest(key=key):
                self.assertEqual(self.run_probe({key:value})[0], 2)

    def test_early_and_expired(self):
        for offset in [-180, 180]:
            self.assertEqual(self.run_probe(offset=offset)[0], 2)

    def test_database_phase_unavailable(self):
        self.assertEqual(self.run_probe(phase='identity-db')[0], 2)

    def test_no_database_dependency_or_discovery_execution(self):
        source = (ROOT/'scripts/p0a_scheduled_diagnostic.py').read_text()
        for forbidden in ['psycopg', 'sqlalchemy', 'run_daily_councils', 'run_weekly',
                          'init_db', 'load_dotenv', 'subprocess', 'socket']:
            self.assertNotIn(forbidden, source)

    def test_real_alarm_terminates_blocked_operation(self):
        code = "from scripts import p0a_scheduled_diagnostic as d; import signal,time; signal.signal(signal.SIGALRM,d.expired_signal); signal.setitimer(signal.ITIMER_REAL,0.2); time.sleep(20)"
        start = time.monotonic()
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, timeout=2)
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 124)
        self.assertLess(elapsed, 2)
        print(f"alarm_termination_seconds={elapsed:.6f}")

    def test_unknown_argument_does_not_echo_input(self):
        result = subprocess.run([sys.executable, '-m', 'scripts.p0a_scheduled_diagnostic',
            '--DO-NOT-PRINT'], cwd=ROOT, capture_output=True, timeout=7)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b'DO-NOT-PRINT', result.stdout + result.stderr)
        self.assertEqual(result.stderr, b'')

    def test_blocked_logging_is_nonblocking(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('probe', ROOT/'scripts/p0a_scheduled_diagnostic.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from unittest.mock import patch
        with patch.object(module.os, 'set_blocking'), patch.object(module.os, 'write', side_effect=BlockingIOError):
            self.assertFalse(module.emit({'outcome':'test'}))

if __name__ == '__main__':
    unittest.main()
