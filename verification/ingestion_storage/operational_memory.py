"""Owner-local kernel limits:256MiB controller,1GiB source,1.5GiB total."""
import os,time
from pathlib import Path
from .memory_enforcement import MemoryUnavailable,values

class OperationalMemory:
    def observe(self):
        """Bounded, read-only diagnostics, never permission to proceed or close.

        Snapshot remains the execution/publication gate. Observation deliberately
        retains a partial readback even when that gate rejects an event or file.
        """
        result={'groups':{},'failures':[],'execution_authority':False}
        for name,path in [('aggregate',self.root),('controller',self.controller),('source',self.source)]:
            group={};result['groups'][name]=group
            for field in ('memory.max','memory.swap.max','memory.oom.group','memory.current','memory.peak','memory.events','cgroup.events','cgroup.procs'):
                try:
                    with (path/field).open() as stream:raw=stream.read(4097)
                    if len(raw)>4096:raise ValueError()
                    if field in ('memory.events','cgroup.events'):
                        allowed={'low','high','max','oom','oom_kill','oom_group_kill'} if field=='memory.events' else {'populated','frozen'}
                        parsed={}
                        for line in raw.splitlines():
                            key,value=line.split()
                            if key in allowed:
                                if key in parsed or not value.isdecimal():raise ValueError()
                                parsed[key]=int(value)
                        required={'max','oom','oom_kill'} if field=='memory.events' else {'populated'}
                        if not required<=parsed.keys():raise ValueError()
                        group[field]=parsed
                    elif field=='cgroup.procs':
                        parts=raw.split()
                        if len(parts)>128 or any(not p.isdecimal() for p in parts):raise ValueError()
                        group[field]=[int(p) for p in parts]
                    elif raw.strip()=='max' and field=='memory.max':group[field]='max'
                    else:
                        if not raw.strip().isdecimal():raise ValueError()
                        group[field]=int(raw.strip())
                except (OSError,ValueError):
                    result['failures'].append({'group':name,'field':field,'code':'KERNEL_FIELD_UNAVAILABLE_OR_MALFORMED'})
        result['status']='PARTIAL' if result['failures'] else 'OBSERVED'
        return result

    def __init__(self):
        lines=Path('/proc/self/cgroup').read_text().splitlines()
        if len(lines)!=1 or not lines[0].startswith('0::/'):raise MemoryUnavailable('CGROUP_V2_REQUIRED')
        relative=Path(lines[0][3:])
        if relative.name!='propertyaigent-operational-once.scope' or '..' in relative.parts:raise MemoryUnavailable('DEDICATED_OPERATIONAL_SCOPE')
        self.root=Path('/sys/fs/cgroup')/str(relative).lstrip('/')
        if self.root.is_symlink() or self.root.joinpath('cgroup.procs').read_text().split()!=[str(os.getpid())]:raise MemoryUnavailable('EXCLUSIVE_OPERATIONAL_SCOPE')
        self.check_root()
        if 'memory' not in self.root.joinpath('cgroup.controllers').read_text().split():raise MemoryUnavailable('MEMORY_DELEGATION_REQUIRED')
        self.controller=self.root/'controller';self.source=self.root/'source'
        self.controller.mkdir();self.controller.joinpath('cgroup.procs').write_text(str(os.getpid()))
        self.root.joinpath('cgroup.subtree_control').write_text('+memory')
        self.source.mkdir()
        for path,limit in [(self.controller,256*1024**2),(self.source,1024**3)]:
            path.joinpath('memory.max').write_text(str(limit));path.joinpath('memory.swap.max').write_text('0');path.joinpath('memory.oom.group').write_text('1')
        self.snapshot()

    def check_root(self):
        if self.root.joinpath('memory.max').read_text().strip()!=str(1536*1024**2) or self.root.joinpath('memory.swap.max').read_text().strip()!='0' or self.root.joinpath('memory.oom.group').read_text().strip()!='1':raise MemoryUnavailable('EXACT_AGGREGATE_MEMORY_LIMIT')

    def snapshot(self):
        self.check_root();result={}
        for name,path,limit in [('aggregate',self.root,1536*1024**2),('controller',self.controller,256*1024**2),('source',self.source,1024**3)]:
            if path.joinpath('memory.max').read_text().strip()!=str(limit) or path.joinpath('memory.swap.max').read_text().strip()!='0':raise MemoryUnavailable('MEMORY_ENFORCEMENT_LOST')
            events=values(path/'memory.events')
            result[name]=dict(peak_bytes=int(path.joinpath('memory.peak').read_text()),current_bytes=int(path.joinpath('memory.current').read_text()),events=events)
            if any(events.get(k) for k in ('max','oom','oom_kill')):raise MemoryUnavailable('MEMORY_LIMIT_HIT')
        return result

    def close(self):
        if values(self.source/'cgroup.events')['populated']:raise MemoryUnavailable('SOURCE_SURVIVORS')
        if self.controller.joinpath('cgroup.procs').read_text().split()!=[str(os.getpid())]:raise MemoryUnavailable('CONTROLLER_OWNED_SURVIVORS')
        evidence=self.snapshot()
        self.source.rmdir()
        # Parent scope has a child controller group: remove its subtree memory
        # controller only after moving the sole process back to the root.
        self.root.joinpath('cgroup.subtree_control').write_text('-memory')
        self.root.joinpath('cgroup.procs').write_text(str(os.getpid()))
        self.controller.rmdir()
        return dict(memory=evidence,owned_groups_removed=True,owned_survivors=0)
