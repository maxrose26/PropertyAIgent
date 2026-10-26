"""Council-free, database-free runtime dependency check for the interpreter that will run a release.

docs/design/real-worker-proof-20261026/SPEC.md section 1. Nothing here contacts a council, a database or the network:
the static scan executes no code, and the import check runs in a child interpreter with a scrubbed environment
(no DATABASE_URL or credentials) over bound modules that only declare code. `app.db.session` is never imported.
"""
import ast
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / 'verification/ah_pg/requirements.lock'
FIRST_PARTY = ('app', 'verification')
NOT_IMPORTED = frozenset({'app.db.session'})
BOUND = 32          # entries reported per list
TIMEOUT_SECONDS = 60
OUTPUT_BYTES = 16384
ERROR_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}')

CHILD_SCRIPT = (
    "import importlib,json,sys\n"
    "root,names=sys.argv[1],json.loads(sys.argv[2]);sys.path.insert(0,root);failures=[]\n"
    "for name in names:\n"
    "    try:importlib.import_module(name)\n"
    "    except BaseException as error:failures.append([name,type(error).__name__])\n"
    "print(json.dumps(failures))\n")


def normalise(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def lock_pins(path=LOCK):
    """{normalised distribution: exact version} from `Name==version` lines; comments and blanks ignored."""
    pins = {}
    for line in Path(path).read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if '==' in line:
            name, version = line.split('==', 1)
            pins[normalise(name.strip())] = version.strip()
    return pins


def module_name(path):
    parts = list(Path(path).with_suffix('').parts)
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def first_party_file(dotted, root=ROOT):
    base = Path(root, *dotted.split('.'))
    for candidate in (base.with_suffix('.py'), base / '__init__.py'):
        if candidate.is_file():
            return candidate.relative_to(root)
    return None


class _Imports(ast.NodeVisitor):
    """Absolute dotted names imported by one module, split into eager (run when the module is imported, class bodies
    included) and lazy (inside a function body).

    Imports guarded by `try ... except ImportError` (or a bare/Exception handler) and `if TYPE_CHECKING:` are optional
    and skipped: the module is written to work without them."""

    def __init__(self, dotted, is_package):
        self.dotted, self.is_package = dotted, is_package
        self.eager, self.lazy, self.optional, self.depth = set(), set(), 0, 0

    def _function(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1
    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _function

    def visit_Try(self, node):
        guarded = any(handler.type is None or any(
            getattr(n, 'id', getattr(n, 'attr', '')) in {'ImportError', 'ModuleNotFoundError', 'Exception', 'BaseException'}
            for n in ast.walk(handler.type)) for handler in node.handlers)
        self.optional += guarded
        for child in node.body:
            self.visit(child)
        self.optional -= guarded
        for child in node.handlers + node.orelse + node.finalbody:
            self.visit(child)

    def visit_If(self, node):
        if any(getattr(n, 'id', getattr(n, 'attr', '')) == 'TYPE_CHECKING' for n in ast.walk(node.test)):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def _add(self, names):
        if not self.optional:
            (self.lazy if self.depth else self.eager).update(names)

    def visit_Import(self, node):
        self._add(alias.name for alias in node.names)

    def visit_ImportFrom(self, node):
        if node.level:
            package = self.dotted.split('.') if self.is_package else self.dotted.split('.')[:-1]
            package = package[:len(package) - (node.level - 1)] if node.level > 1 else package
            base = '.'.join(package + ([node.module] if node.module else []))
        else:
            base = node.module or ''
        if base:
            self._add([base] + [base + '.' + alias.name for alias in node.names if alias.name != '*'])


def scan(paths, root=ROOT):
    """(first-party modules that load, {third-party top-level name: first importer}).

    Model of what actually loads: the eager imports of the bound modules; plus the lazy (function-level) imports of the
    BOUND modules themselves, one hop; each expanded by its own eager imports. Lazy imports of other modules are not
    followed (a static scan cannot know reachability); the runtime proof covers them. Nothing is executed."""
    stdlib, cache = set(sys.stdlib_module_names), {}

    def parsed(dotted):
        if dotted not in cache:
            file = first_party_file(dotted, root)
            if file is None:
                cache[dotted] = None
            else:
                visitor = _Imports(dotted, file.name == '__init__.py')
                visitor.visit(ast.parse(Path(root, file).read_text(), filename=str(file)))
                cache[dotted] = visitor
        return cache[dotted]

    def split(names):
        first, other = set(), set()
        for name in names:
            top = name.split('.')[0]
            if top in FIRST_PARTY:
                if first_party_file(name, root):
                    first.add(name)
            elif top not in stdlib:
                other.add(top)
        return first, other

    bound = [module_name(p) for p in paths if str(p).endswith('.py') and Path(root, p).is_file()]
    closure, third, start = set(), {}, set(bound)
    for dotted in bound:                                  # one hop of lazy imports, bound modules only
        first, other = split(parsed(dotted).lazy)
        start |= first
        for name in other:
            third.setdefault(name, dotted)
    queue = sorted(start)
    while queue:                                          # eager closure
        dotted = queue.pop()
        if dotted in closure or parsed(dotted) is None:
            continue
        closure.add(dotted)
        for parent in dotted.split('.')[:-1]:             # package __init__ modules run on import
            if first_party_file(parent, root):
                queue.append(parent)
        first, other = split(parsed(dotted).eager)
        queue.extend(first)
        for name in other:
            third.setdefault(name, dotted)
    return sorted(closure), third


def _resolvable(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False        # a blocked or broken finder is a missing module


def _distribution_state(name, pinned):
    try:
        installed = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return dict(installed=None, pinned=pinned, state='MISSING')
    state = 'OK' if pinned is None or installed == pinned else 'VERSION_MISMATCH'
    return dict(installed=installed, pinned=pinned, state=state)


def import_check(modules, *, python=None, extra_env=None):
    """Import `modules` in a child interpreter; returns [[module, exception class name], ...]. Output is parsed strictly."""
    with tempfile.TemporaryDirectory(prefix='runtime-check-') as home:
        env = dict(PATH='/usr/bin:/bin', HOME=home, TMPDIR=home, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', LC_CTYPE='C.UTF-8')
        env.update(extra_env or {})
        try:
            done = subprocess.run([python or sys.executable, '-c', CHILD_SCRIPT, str(ROOT), json.dumps(modules)], cwd=ROOT, env=env,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            return [['<child>', 'ChildUnavailable']]
    raw = done.stdout[:OUTPUT_BYTES + 1]
    try:
        value = json.loads(raw.decode('ascii')) if done.returncode == 0 and len(raw) <= OUTPUT_BYTES else None
    except (UnicodeDecodeError, ValueError):
        value = None
    allowed = set(modules)
    if not (isinstance(value, list) and all(isinstance(x, list) and len(x) == 2 and x[0] in allowed and isinstance(x[1], str)
                                            and ERROR_NAME.fullmatch(x[1]) for x in value)):
        return [['<child>', 'ChildOutputMalformed']]
    return value


def check(paths, distributions, *, python=None, lock=LOCK, extra_env=None, root=ROOT):
    """Complete runtime verdict. `paths`: bound module files; `distributions`: bound distribution names."""
    pins = lock_pins(lock)
    report = dict(distributions={name: _distribution_state(name, pins.get(normalise(name))) for name in distributions})
    closure, third = scan(paths, root)
    report['third_party_missing'] = sorted(name for name in third if not _resolvable(name))[:BOUND]
    imported = [m for m in closure if m not in NOT_IMPORTED and m.split('.')[0] in FIRST_PARTY]
    report['import_failures'] = import_check(imported, python=python, extra_env=extra_env)[:BOUND]
    report['modules'] = dict(bound=len(paths), closure=len(closure), imported=len(imported), third_party=len(third))
    report['ok'] = (all(d['state'] == 'OK' for d in report['distributions'].values())
                    and not report['third_party_missing'] and not report['import_failures'])
    return report
