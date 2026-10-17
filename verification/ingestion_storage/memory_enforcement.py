"""Fail-closed cgroup-v2 containment for the finite storage worker.

No credentials, network, root fallback or arbitrary cgroup path configuration.
The owner invokes Python directly in a dedicated delegated systemd user scope.
Kernel memory charging includes descendants and is independent of virtual size.
"""
import os
from pathlib import Path
import time

LIMIT = 256 * 1024**2
SCOPE = 'propertyaigent-storage-memory-20261017.scope'


class MemoryUnavailable(RuntimeError):
    pass


def values(path):
    return {k: int(v) for k, v in (line.split() for line in path.read_text().splitlines())}


def owner_scope():
    lines = Path('/proc/self/cgroup').read_text().splitlines()
    if len(lines) != 1 or not lines[0].startswith('0::/'):
        raise MemoryUnavailable('MEMORY_ENFORCEMENT_UNAVAILABLE')
    relative = Path(lines[0][3:])
    if '..' in relative.parts or relative.name != SCOPE:
        raise MemoryUnavailable('DEDICATED_MEMORY_SCOPE_REQUIRED')
    root = Path('/sys/fs/cgroup') / str(relative).lstrip('/')
    if root.is_symlink() or not root.is_dir():
        raise MemoryUnavailable('MEMORY_ENFORCEMENT_UNAVAILABLE')
    if root.joinpath('cgroup.procs').read_text().split() != [str(os.getpid())]:
        raise MemoryUnavailable('EXCLUSIVE_MEMORY_SCOPE_REQUIRED')
    if 'memory' not in root.joinpath('cgroup.controllers').read_text().split():
        raise MemoryUnavailable('MEMORY_ENFORCEMENT_UNAVAILABLE')
    # Set by systemd before exec of the owner command, not by migrating an
    # already initialized Python process. This outer limit includes supervisor,
    # inherited interpreter pages, worker, gh and all descendants from birth.
    if (root.joinpath('memory.max').read_text().strip() != str(LIMIT)
            or root.joinpath('memory.swap.max').read_text().strip() != '0'
            or root.joinpath('memory.oom.group').read_text().strip() != '1'):
        raise MemoryUnavailable('OUTER_MEMORY_LIMIT_REQUIRED')
    for name in ('cgroup.procs', 'cgroup.subtree_control'):
        if not os.access(root / name, os.W_OK):
            raise MemoryUnavailable('MEMORY_DELEGATION_REQUIRED')
    if not os.access(root, os.W_OK):
        raise MemoryUnavailable('MEMORY_DELEGATION_REQUIRED')
    return root


class WorkerMemory:
    def __init__(self, path):
        self.path = path
        self.closed = False

    @classmethod
    def create(cls):
        root = owner_scope()
        # Only our exclusive scope is rearranged. Existing keyring/session
        # processes stay outside it. No shared user/session cgroup is changed.
        supervisor = root / 'supervisor'
        supervisor.mkdir()
        supervisor.joinpath('cgroup.procs').write_text(str(os.getpid()))
        root.joinpath('cgroup.subtree_control').write_text('+memory')
        return cls.create_under(root)

    @classmethod
    def create_under(cls, root):
        # Also used by disposable tests with an independently delegated root.
        if 'memory' not in root.joinpath('cgroup.subtree_control').read_text().split():
            raise MemoryUnavailable('MEMORY_DELEGATION_REQUIRED')
        path = root / 'worker'
        path.mkdir()
        try:
            path.joinpath('memory.max').write_text(str(LIMIT))
            path.joinpath('memory.swap.max').write_text('0')
            path.joinpath('memory.oom.group').write_text('1')
            group = cls(path)
            group.snapshot()
            if path.joinpath('cgroup.procs').read_text().strip():
                raise MemoryUnavailable('MEMORY_GROUP_NOT_EMPTY')
            return group
        except BaseException:
            path.rmdir()
            raise

    def enter(self):
        self.path.joinpath('cgroup.procs').write_text(str(os.getpid()))
        if str(os.getpid()) not in self.path.joinpath('cgroup.procs').read_text().split():
            raise MemoryUnavailable('MEMORY_ATTACHMENT_FAILED')

    def snapshot(self):
        if (self.path.joinpath('memory.max').read_text().strip() != str(LIMIT)
                or self.path.joinpath('memory.swap.max').read_text().strip() != '0'
                or self.path.joinpath('memory.oom.group').read_text().strip() != '1'
                or not self.path.joinpath('cgroup.kill').exists()):
            raise MemoryUnavailable('MEMORY_ENFORCEMENT_LOST')
        events = values(self.path / 'memory.events')
        outer = self.path.parent
        if (outer.joinpath('memory.max').read_text().strip() != str(LIMIT)
                or outer.joinpath('memory.swap.max').read_text().strip() != '0'
                or outer.joinpath('memory.oom.group').read_text().strip() != '1'):
            raise MemoryUnavailable('OUTER_MEMORY_ENFORCEMENT_LOST')
        outer_events = values(outer / 'memory.events')
        return dict(kernel_memory_peak_bytes=int(self.path.joinpath('memory.peak').read_text()),
                    kernel_memory_current_bytes=int(self.path.joinpath('memory.current').read_text()),
                    kernel_memory_oom=events['oom'], kernel_memory_oom_kill=events['oom_kill'],
                    kernel_memory_max_events=events['max'],
                    kernel_memory_populated=values(self.path / 'cgroup.events')['populated'],
                    outer_memory_peak_bytes=int(outer.joinpath('memory.peak').read_text()),
                    outer_memory_current_bytes=int(outer.joinpath('memory.current').read_text()),
                    outer_memory_max_events=outer_events['max'],
                    outer_memory_oom=outer_events['oom'], outer_memory_oom_kill=outer_events['oom_kill'])

    def close(self, deadline):
        # Do not make containment cleanup depend on successful accounting.
        try:
            forced = bool(values(self.path / 'cgroup.events')['populated'])
        except BaseException:
            forced = True
        if forced:
            self.path.joinpath('cgroup.kill').write_text('1')
        while values(self.path / 'cgroup.events')['populated']:
            if time.monotonic() >= deadline:
                raise MemoryUnavailable('MEMORY_CLEANUP_UNCERTAIN')
            time.sleep(.005)
        try:
            state = self.snapshot()
        except BaseException:
            state = dict(kernel_memory_accounting_uncertain=True)
        self.path.rmdir()
        self.closed = True
        return dict(**state, kernel_memory_forced_cleanup=forced,
                    kernel_memory_group_removed=True)
