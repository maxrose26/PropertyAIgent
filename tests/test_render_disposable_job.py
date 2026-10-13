import unittest
import shlex
from pathlib import Path
from verification.direct_reference.render_disposable_job import SERVICE, pack, unpack, build_command
from verification.direct_reference.instrumented_probe import execution_environment_allowed


class DisposableJobTests(unittest.TestCase):
    def test_explicit_environment_gate(self):
        self.assertTrue(execution_environment_allowed('trafford', 'render-disposable', {'RENDER_SERVICE_ID': SERVICE}))
        self.assertFalse(execution_environment_allowed('salford', 'render-disposable', {'RENDER_SERVICE_ID': SERVICE}))
        self.assertFalse(execution_environment_allowed('trafford', 'render-disposable', {}))
        self.assertFalse(execution_environment_allowed('trafford', 'github-hosted', {'RENDER_SERVICE_ID': SERVICE}))

    def test_payload_integrity(self):
        root = Path(__file__).resolve().parents[1]
        encoded, digest = pack(root)
        self.assertEqual(len(unpack(encoded, digest)), 2)
        with self.assertRaisesRegex(ValueError, 'PAYLOAD_HASH'):
            unpack(encoded, '0' * 64)

    def test_clean_launcher(self):
        command = build_command(Path(__file__).resolve().parents[1])['startCommand']
        compile(shlex.split(command)[-1], '<bootstrap>', 'exec')
        self.assertIn('exec /usr/bin/env -i ', command)
        self.assertIn('python3 -I -c ', command)
        self.assertNotIn('GITHUB_ACTIONS=', command)
        self.assertNotIn('pip install', command)
        self.assertNotIn('DATABASE_URL=', command)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH=', command)


if __name__ == '__main__':
    unittest.main()
