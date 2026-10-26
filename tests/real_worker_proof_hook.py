"""Interpreter hook for the real-worker proof (tests/test_real_worker_proof.py).

Installed ONLY into an overlay venv created by that test; never into a real environment.
1. `blocked.txt` (next to this file): top-level names whose import raises ModuleNotFoundError. This is the missing-dependency control.
2. Only inside the proof's own network namespace (recognised by the hosts overlay marker line), Playwright launches also pass
   `--ignore-certificate-errors`: Chromium uses its built-in NSS roots and cannot be given the fixture CA by a file overlay.
   This is the single deviation from production on the Rochdale route; commands, environments and process layers are untouched.
"""
import importlib.abc
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = '# real-worker-proof fixture hosts'


def blocked_names():
    try:
        return {line.strip() for line in (HERE / 'blocked.txt').read_text().splitlines() if line.strip()}
    except OSError:
        return set()


class Block(importlib.abc.MetaPathFinder):
    def __init__(self, names):
        self.names = names

    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in self.names:
            raise ModuleNotFoundError(f'No module named {name!r}', name=name)


class PatchPlaywright(importlib.abc.MetaPathFinder):
    busy = False

    def find_spec(self, name, path=None, target=None):
        if name != 'playwright.async_api' or self.busy:
            return None
        self.busy = True
        try:
            spec = importlib.util.find_spec(name)
        finally:
            self.busy = False
        if spec is None or spec.loader is None:
            return None
        loader, original = spec.loader, spec.loader.exec_module

        def exec_module(module):
            original(module)
            launch = module.BrowserType.launch

            async def patched(self, *args, **kwargs):
                kwargs['args'] = list(kwargs.get('args') or []) + ['--ignore-certificate-errors']
                return await launch(self, *args, **kwargs)
            module.BrowserType.launch = patched
        loader.exec_module = exec_module
        return spec


def install():
    names = blocked_names()
    if names:
        sys.meta_path.insert(0, Block(names))
    try:
        marked = MARKER in Path('/etc/hosts').read_text()
    except OSError:
        marked = False
    if marked:
        sys.meta_path.insert(0, PatchPlaywright())


install()
