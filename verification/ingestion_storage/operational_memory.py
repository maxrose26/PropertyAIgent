"""Owner-local kernel limits:256MiB controller,1GiB source,1.5GiB total."""
import os,time
from pathlib import Path
from .memory_enforcement import MemoryUnavailable,values

EVENTS=('low','high','max','oom','oom_kill','oom_group_kill')
# Allowlisted memory.stat fields (bytes). memory.current ~= anon+file+kernel+sock;
# the remaining fields are SUBSETS and must never be added to those four:
# shmem/file_mapped/file_dirty are part of file (tmpfs and shared memory are
# file-backed); slab_*/kernel_stack/pagetables/percpu are part of kernel.
STAT_FIELDS=('anon','file','kernel','sock','shmem','file_mapped','file_dirty',
    'slab_reclaimable','slab_unreclaimable','kernel_stack','pagetables','percpu')
STAT_CATEGORIES=dict(disjoint=['anon','file','kernel','sock'],
    subset_of={'shmem':'file','file_mapped':'file','file_dirty':'file','slab_reclaimable':'kernel',
        'slab_unreclaimable':'kernel','kernel_stack':'kernel','pagetables':'kernel','percpu':'kernel'})

class OperationalMemory:
    # Finalisation-only state: entered once after a memory failure, never left.
    finalisation_only=False;latched=None
    def observe(self):
        """Bounded, read-only diagnostics, never permission to proceed or close.

        Snapshot remains the execution/publication gate. Observation deliberately
        retains a partial readback even when that gate rejects an event or file.
        """
        result={'groups':{},'failures':[],'execution_authority':False,'stat_categories':STAT_CATEGORIES}
        for name,path in [('aggregate',self.root),('controller',self.controller),('source',self.source)]:
            group={};result['groups'][name]=group
            for field in ('memory.max','memory.swap.max','memory.oom.group','memory.current','memory.peak','memory.events','memory.stat','cgroup.events','cgroup.procs'):
                try:
                    bound=16384 if field=='memory.stat' else 4096
                    with (path/field).open() as stream:raw=stream.read(bound+1)
                    if len(raw)>bound:raise ValueError()
                    if field=='memory.stat':
                        parsed={}
                        for line in raw.splitlines():
                            key,value=line.split()
                            if key in STAT_FIELDS:
                                if key in parsed or not value.isdecimal():raise ValueError()
                                parsed[key]=int(value)
                        if not {'anon','file','shmem'}<=parsed.keys():raise ValueError()  # kernel needs Linux>=5.18
                        group[field]=parsed
                    elif field in ('memory.events','cgroup.events'):
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
        """Execution gate. Permanently closed once a memory failure is latched."""
        if self.finalisation_only:raise MemoryUnavailable('FINALISATION_ONLY')
        self.check_root();result={}
        for name,path,limit in [('aggregate',self.root,1536*1024**2),('controller',self.controller,256*1024**2),('source',self.source,1024**3)]:
            if path.joinpath('memory.max').read_text().strip()!=str(limit) or path.joinpath('memory.swap.max').read_text().strip()!='0':raise MemoryUnavailable('MEMORY_ENFORCEMENT_LOST')
            events=values(path/'memory.events')
            result[name]=dict(peak_bytes=int(path.joinpath('memory.peak').read_text()),current_bytes=int(path.joinpath('memory.current').read_text()),events=events)
            if any(events.get(k) for k in ('max','oom','oom_kill')):raise MemoryUnavailable('MEMORY_LIMIT_HIT')
        return result

    def groups(self):
        return [('aggregate',self.root,1536*1024**2),('controller',self.controller,256*1024**2),('source',self.source,1024**3)]

    def counters(self,path,field='memory.events'):
        try:
            events=values(path/field);return {k:events[k] for k in EVENTS}
        except (OSError,ValueError,KeyError):raise MemoryUnavailable('MEMORY_FIELD_UNAVAILABLE') from None

    def identity(self):
        result={}
        try:
            for name,path,_ in self.groups():
                if path.is_symlink():raise MemoryUnavailable('CGROUP_IDENTITY_CHANGED')
                st=os.stat(path,follow_symlinks=False);result[name]=[st.st_dev,st.st_ino]
            return dict(groups=result,own=Path('/proc/self/cgroup').read_text())
        except (OSError,ValueError):raise MemoryUnavailable('MEMORY_FIELD_UNAVAILABLE') from None

    def enforcement(self):
        """Exact limits, swap and group-OOM policy; owned process placement."""
        try:
            self.check_root()
            for name,path,limit in self.groups()[1:]:
                if (path.joinpath('memory.max').read_text().strip()!=str(limit) or path.joinpath('memory.swap.max').read_text().strip()!='0'
                    or path.joinpath('memory.oom.group').read_text().strip()!='1'):raise MemoryUnavailable('MEMORY_ENFORCEMENT_LOST')
            populated=values(self.source/'cgroup.events')['populated']
            procs=self.controller.joinpath('cgroup.procs').read_text().split()
        except (OSError,ValueError,KeyError):raise MemoryUnavailable('MEMORY_FIELD_UNAVAILABLE') from None
        if populated:raise MemoryUnavailable('SOURCE_SURVIVORS')
        if procs!=[str(os.getpid())]:raise MemoryUnavailable('CONTROLLER_OWNED_SURVIVORS')

    def latch(self):
        """Enter finalisation-only state after a memory failure; irreversible.

        Execution (snapshot) is closed before anything else is read. The baseline
        is recorded only once the source group is empty and enforcement is exact,
        so later counters can be compared; otherwise no baseline exists and
        finalisation_check refuses. Grants no execution authority.
        """
        if self.finalisation_only:raise MemoryUnavailable('FINALISATION_ONLY')
        self.finalisation_only=True
        self.enforcement()
        baseline=dict(events={name:self.counters(path) for name,path,_ in self.groups()},identity=self.identity())
        # Only a source-group event may be finalised: the publishing controller and the
        # aggregate itself (local counters) must never have been under memory pressure.
        if (any(baseline['events']['controller'][k] for k in ('max','oom','oom_kill','oom_group_kill'))
            or any(self.counters(self.root,'memory.events.local')[k] for k in ('max','oom','oom_kill','oom_group_kill'))):
            raise MemoryUnavailable('CONTROLLER_OR_AGGREGATE_MEMORY_EVENT')
        self.latched=baseline
        return dict(events=baseline['events'],execution_authority=False)

    def finalisation_check(self):
        """Publication/removal gate after a latched failure; never an execution gate.

        Refuses on lost or changed enforcement, changed group identity, a populated
        source, controller survivors, unreadable fields, or any counter differing
        from the latched baseline.
        """
        if not self.finalisation_only or self.latched is None:raise MemoryUnavailable('FINALISATION_BASELINE_UNAVAILABLE')
        self.enforcement()
        if self.identity()!=self.latched['identity']:raise MemoryUnavailable('CGROUP_IDENTITY_CHANGED')
        result={}
        for name,path,_ in self.groups():
            events=self.counters(path)
            if events!=self.latched['events'][name]:raise MemoryUnavailable('MEMORY_EVENT_AFTER_LATCH')
            try:peak,current=int(path.joinpath('memory.peak').read_text()),int(path.joinpath('memory.current').read_text())
            except (OSError,ValueError):raise MemoryUnavailable('MEMORY_FIELD_UNAVAILABLE') from None
            result[name]=dict(peak_bytes=peak,current_bytes=current,events=events,latched_events=self.latched['events'][name])
        return result

    def close(self):
        if values(self.source/'cgroup.events')['populated']:raise MemoryUnavailable('SOURCE_SURVIVORS')
        if self.controller.joinpath('cgroup.procs').read_text().split()!=[str(os.getpid())]:raise MemoryUnavailable('CONTROLLER_OWNED_SURVIVORS')
        evidence=self.finalisation_check() if self.finalisation_only else self.snapshot()
        self.source.rmdir()
        # Parent scope has a child controller group: remove its subtree memory
        # controller only after moving the sole process back to the root.
        self.root.joinpath('cgroup.subtree_control').write_text('-memory')
        self.root.joinpath('cgroup.procs').write_text(str(os.getpid()))
        self.controller.rmdir()
        result=dict(memory=evidence,owned_groups_removed=True,owned_survivors=0)
        if self.finalisation_only:result['finalisation']='LATCHED_COUNTERS_UNCHANGED'
        return result
