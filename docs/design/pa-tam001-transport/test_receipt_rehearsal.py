"""No production access. Close a real PTY, then read completion independently."""
import hashlib
import json
import os
from pathlib import Path
import pty
import subprocess
import tempfile
import time
import unittest


class ReceiptTransport(unittest.TestCase):
    def test_disconnect_readback_and_duplicate_refusal(self):
        script = Path(__file__).with_name('receipt-rehearsal.py').resolve()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'rehearsal-disconnect-20261117'
            master, slave = pty.openpty()
            process = subprocess.Popen(['python3', '-B', str(script), 'start', str(root)],
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
                env={'PATH': os.environ['PATH']})
            os.close(slave)
            process.wait(timeout=3)
            acknowledgement = os.read(master, 8192)
            os.close(master)
            self.assertEqual(process.returncode, 0)
            self.assertIn(b'REHEARSAL_ACCEPTED', acknowledgement)
            self.assertFalse((root / 'completion.json').exists())
            deadline = time.monotonic() + 8
            while not (root / 'completion.json').exists() and time.monotonic() < deadline:
                time.sleep(.05)
            result = subprocess.run(['python3', '-B', str(script), 'read', str(root)],
                                    capture_output=True, text=True, check=True)
            ack, done = map(json.loads, result.stdout.splitlines())
            self.assertEqual(done['id'], ack['id'])
            self.assertEqual(done['ack_sha256'], hashlib.sha256((root/'ack.json').read_bytes()).hexdigest())
            self.assertEqual(done['database_connections'], 0)
            self.assertEqual(done['sql_statements'], 0)
            before = (root/'completion.json').read_bytes()
            duplicate = subprocess.run(['python3', '-B', str(script), 'start', str(root)], capture_output=True)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertEqual(before, (root/'completion.json').read_bytes())
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root/'completion.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
