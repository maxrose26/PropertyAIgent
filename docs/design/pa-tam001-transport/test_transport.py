"""Disposable command transport checks. No production destination or credentials."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import pty
import select
import shlex
import subprocess
import threading
import time
import unittest

ROOT = Path(__file__).parent


def command(url, digest, seconds=58):
    code = ('import urllib.request,hashlib,sys,signal; signal.signal(signal.SIGALRM,lambda *_:sys.exit("ARTIFACT_DOWNLOAD_TIMEOUT_NO_EXECUTION")); signal.alarm(5); '
            f'b=urllib.request.urlopen({url!r},timeout=5).read(32769); '
            f'hashlib.sha256(b).hexdigest()=={digest!r} or '
            'sys.exit("ARTIFACT_HASH_MISMATCH_NO_EXECUTION"); '
            'signal.alarm(0); exec(compile(b,"PA-TAM001-inspection.py","exec"))')
    return f'timeout --signal=TERM --kill-after=2s {seconds}s python3 -B -c {shlex.quote(code)}'


class Transport(unittest.TestCase):
    def run_payload(self, payload, digest=None, seconds=58, delay=0):
        requests = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if delay:
                    time.sleep(delay)
                self.send_response(200)
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except BrokenPipeError:
                    pass
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}/immutable-fixture.py'
        line = command(url, digest or hashlib.sha256(payload).hexdigest(), seconds)
        self.assertNotIn('\n', line)
        master, slave = pty.openpty()
        # Empty credential environment; noninteractive shell reading one newline.
        process = subprocess.Popen(['bash', '--noprofile', '--norc'], stdin=slave,
            stdout=slave, stderr=slave, env={'PATH': os.environ['PATH'], 'PS1': ''})
        os.close(slave)
        started = time.monotonic()
        output = b''
        try:
            os.write(master, (line + '; exit\n').encode())
            while time.monotonic() - started < 9:
                if select.select([master], [], [], .1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    output += chunk
                if process.poll() is not None:
                    break
            process.wait(timeout=1)
            elapsed = time.monotonic() - started
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            server.shutdown()
            server.server_close()
        self.assertEqual(requests, ['/immutable-fixture.py'])
        # PTY echoes submitted command. Only parse standalone JSON receipt lines.
        receipts = [json.loads(x) for x in output.decode().splitlines() if x.startswith('{')]
        return process.returncode, receipts, elapsed, output.decode()

    def test_exact_once_receipt(self):
        code, receipts, elapsed, _ = self.run_payload(b'print("{\\"fixture\\":\\"harmless\\",\\"executions\\":1}")\n')
        self.assertEqual(code, 0)
        self.assertEqual(receipts, [{'fixture': 'harmless', 'executions': 1}])
        self.assertLess(elapsed, 5)

    def test_hash_mismatch_does_not_execute(self):
        code, receipts, _, output = self.run_payload(b'print("{\\"executed\\":true}")\n', '0' * 64)
        self.assertNotEqual(code, 0)
        self.assertEqual(receipts, [])
        self.assertIn('ARTIFACT_HASH_MISMATCH_NO_EXECUTION', output)

    def test_oversize_body_refused(self):
        payload = b'#' * 32770 + b'\nprint("{\\"executed\\":true}")\n'
        code, receipts, _, _ = self.run_payload(payload)
        self.assertNotEqual(code, 0)
        self.assertEqual(receipts, [])

    def test_timeout_no_retry(self):
        code, receipts, elapsed, _ = self.run_payload(b'import time; time.sleep(30)\n', seconds=1)
        self.assertEqual(code, 124)
        self.assertEqual(receipts, [])
        self.assertLess(elapsed, 4)

    def test_download_deadline_before_any_execution(self):
        code, receipts, elapsed, output = self.run_payload(
            b'print("{\\"executed\\":true}")\n', delay=6)
        self.assertNotEqual(code, 0)
        self.assertEqual(receipts, [])
        self.assertLess(elapsed, 7)
        self.assertIn('ARTIFACT_DOWNLOAD_TIMEOUT_NO_EXECUTION', output)

    def test_real_script_refuses_wrong_destination_before_connection(self):
        code, receipts, _, _ = self.run_payload((ROOT / 'inspection.py').read_bytes())
        self.assertEqual(code, 0)  # inspection receipt, not exit code, is authoritative
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        self.assertEqual(receipt['reason'], 'SERVICE_MISMATCH')
        self.assertEqual(receipt['connections_attempted'], 0)
        self.assertEqual(receipt['statements_attempted'], 0)
        self.assertEqual(receipt['status'], 'STOP_REFUSED_NO_RETRY')


if __name__ == '__main__':
    unittest.main(verbosity=2)
