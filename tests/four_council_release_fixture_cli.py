"""Standalone whole-wrapper rehearsal. Synthetic sources/API; optional real kernel.

No production registration, account, SQL, council route or external API is used.
Native mode is admitted only by the existing dedicated memory scope in offline CI.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from verification.discovery import four_council_release as r
from verification.ingestion_storage.operational_publication import GitHub, canonical
from tests.test_discovery_four_council_release import API, Memory, audit, registration
from tests.test_discovery_three_council_isolation import local_audit, registration as successor_registration

MEMORY_FAULTS=('memory-reclaim','memory-enforcement-lost','memory-survivor')


def reclaim(root):
    """Real kernel limit event, no OOM: reclaimable page cache written inside the source group.

    Hosted CI only (local pressure tests are paused). Writes are bounded at the group's own
    memory.max + 512MiB (V1 1GiB: 192 chunks, unchanged; V2 1.5GiB: 256); V2 also stops at 40s
    elapsed. The V1 profile's behaviour is unchanged."""
    group=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip()[3:].lstrip('/')
    assert group.name=='source'
    limit=int((group/'memory.max').read_text())
    assert limit in (1024**3,1536*1024**2)
    chunk=b'\1'*(8*1024**2);started=time.monotonic()
    with open(root/'reclaim.bin','wb') as stream:
        for _ in range((limit+512*1024**2)//len(chunk)):  # stops at the first max event
            if limit!=1024**3 and time.monotonic()-started>40:break  # V2 only; no event: the assertions fail
            # Synced chunks leave clean, immediately reclaimable page cache: the kernel event under
            # test is reclaim at the limit, not writeback stalls (hosted run 39953419679 attempt 2).
            stream.write(chunk);stream.flush();os.fdatasync(stream.fileno())
            if int(dict(line.split() for line in (group/'memory.events').read_text().splitlines())['max']):break
    time.sleep(30)  # the unchanged controller gate must detect the event and kill the group


def real_chromium(selection=None,evidence=None):
    """Council-free real Chromium: inline content only, every request aborted, no host resolvable.

    Launch options come from the production browser_launch_options(), so a prepared font cache is
    validated and read inside this (source-group) process."""
    import asyncio
    from playwright.async_api import async_playwright
    from verification.direct_reference.instrumented_probe import browser_launch_options
    async def run():
        async with async_playwright() as playwright:
            browser=await playwright.chromium.launch(headless=True,args=['--host-resolver-rules=MAP * ~NOTFOUND','--no-proxy-server'],**browser_launch_options(selection))
            context=await browser.new_context(service_workers='block',accept_downloads=False)
            await context.route('**/*',lambda route:route.abort())
            page=await context.new_page()
            await page.set_content('<!doctype html><title>fixture</title><table>'+''.join(f'<tr><td>{i}</td><td>row {i}</td></tr>' for i in range(2000))+'</table>')
            rows=await page.evaluate('document.querySelectorAll("tr").length')
            import psutil
            mapped=set()
            for process in psutil.Process().children(recursive=True):  # this run's browser only
                try:mapped.update(l.split()[-1] for l in Path(f'/proc/{process.pid}/maps').read_text().splitlines() if '.cache-11' in l)
                except OSError:pass
            await browser.close();return rows,sorted(mapped)
    rows,mapped=asyncio.run(run())
    assert rows==2000
    if evidence is not None:
        home=Path(os.environ['HOME'])
        evidence.write_text(json.dumps(dict(mode='prepared' if selection else 'default',mapped=mapped,
            home_fontconfig=sorted(str(x.relative_to(home)) for x in home.rglob('*') if 'fontconfig' in x.parts))))


def mincore_residency(path):
    """(bytes, resident bytes) of one file via mincore on a private mapping; no page is faulted in."""
    import ctypes,mmap
    size=os.stat(path).st_size
    if size==0:return 0,0
    libc=ctypes.CDLL(None,use_errno=True);page=os.sysconf('SC_PAGE_SIZE')
    with open(path,'rb') as stream:
        m=mmap.mmap(stream.fileno(),size,access=mmap.ACCESS_COPY)
        try:
            vec=(ctypes.c_ubyte*((size+page-1)//page))();c=ctypes.c_char.from_buffer(m)
            try:
                if libc.mincore(ctypes.c_void_p(ctypes.addressof(c)),ctypes.c_size_t(size),vec):raise OSError(ctypes.get_errno(),'mincore')
                return size,min(size,sum(v&1 for v in vec)*page)
            finally:del c
        finally:m.close()


def residency(sets,measure=mincore_residency):
    """Read-only page-cache residency with explicit coverage. Pre-registered classes:
    COLD: every set completely measured and at most 2% resident; WARM: completely measured and
    every set at least 90%; PARTIAL: completely measured otherwise; INCOMPLETE: any missing root,
    empty set, walk error, unreadable file or failed measurement (never COLD or WARM).
    File symlinks are measured once at their resolved target."""
    result={}
    for name,root in sets.items():
        entry=dict(files=0,measured=0,failed=0,bytes=0,resident=0,errors=[])
        result[name]=entry
        files=[] if not root.exists() else [root] if root.is_file() else []
        if not root.exists():entry['errors'].append('ROOT_MISSING')
        elif not files:
            for directory,dirnames,names in os.walk(root,onerror=lambda e:entry['errors'].append('WALK_ERROR')):
                if any(os.path.islink(os.path.join(directory,d)) for d in dirnames):
                    entry['errors'].append('SYMLINKED_DIR')  # its files would be silently uncovered
                files.extend(Path(directory)/n for n in names)
        seen=set()
        for path in files:
            entry['files']+=1
            try:
                real=os.path.realpath(path)
                if real in seen:entry['measured']+=1;continue
                size,resident=measure(Path(real));seen.add(real)
                entry['measured']+=1;entry['bytes']+=size;entry['resident']+=resident
            except (OSError,ValueError) as error:  # ValueError: e.g. file truncated before mmap
                entry['failed']+=1
                if len(entry['errors'])<8:entry['errors'].append(type(error).__name__)
        if entry['files']==0:entry['errors'].append('EMPTY')
        entry['errors']=entry['errors'][:8]
        entry['coverage']=round(entry['measured']/entry['files'],4) if entry['files'] else 0.0
        entry['fraction']=round(entry['resident']/entry['bytes'],4) if entry['bytes'] else None
        entry['complete']=not entry['errors'] and entry['failed']==0 and entry['measured']==entry['files']>0 and entry['bytes']>0
    complete=bool(result) and all(v['complete'] for v in result.values())
    fractions=[v['fraction'] for v in result.values() if v['fraction'] is not None]
    if not complete or len(fractions)!=len(result):cls='INCOMPLETE'
    elif max(fractions)<=.02:cls='COLD'
    elif min(fractions)>=.90:cls='WARM'
    else:cls='PARTIAL'
    return dict(sets=result,complete=complete,**{'class':cls})


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--native',action='store_true');p.add_argument('--successor',action='store_true');p.add_argument('--fault',choices=['none','unknown','cancel','cancel-startup','unavailable','local-all','local-0','local-1','local-2','memory-failure','reporting-failure','publication-failure','real-chromium',*MEMORY_FAULTS],default='none');p.add_argument('--worker',type=int);p.add_argument('--browser-fixture',action='store_true');p.add_argument('--output',type=Path)
    p.add_argument('--prepared-font-cache');p.add_argument('--prepared-font-cache-sha256')
    p.add_argument('--execution-budget-v2',action='store_true');a=p.parse_args()
    assert a.successor or not a.execution_budget_v2
    budget_name='BROWSER_SOURCE_V2' if a.execution_budget_v2 else None
    budget_args=['--execution-budget-v2'] if a.execution_budget_v2 else []
    assert (a.prepared_font_cache is None)==(a.prepared_font_cache_sha256 is None)
    selection=(a.prepared_font_cache,a.prepared_font_cache_sha256) if a.prepared_font_cache else None
    font_args=['--prepared-font-cache',a.prepared_font_cache,'--prepared-font-cache-sha256',a.prepared_font_cache_sha256] if selection else []
    def source_value(index):
        if a.successor and a.fault in ('local-all',f'local-{index-1}'):
            return local_audit(index,'selector' if index==3 else 'sort',**({'execution_budget':budget_name} if budget_name and index==1 else {}))
        value=audit(index,complete=not(a.fault=='unknown' and index==(1 if a.successor else 0)))
        if budget_name and index==1:  # the budgeted probe declares its budget and fixed stage timings
            value.update(execution_budget=budget_name,stage_timings={'NAVIGATION':1200,'READY':900,'CRITERIA':400,'SEGMENT':[300]})
        return value
    if a.worker is not None:
        if a.native and not a.browser_fixture:r.owner_source_context(budget_name)
        if a.native and a.fault in MEMORY_FAULTS and a.worker==1:reclaim(Path(os.environ['TMPDIR']))
        if a.browser_fixture and a.fault=='real-chromium':real_chromium(selection,a.root/'browser-evidence.json')
        if a.fault in ('cancel','cancel-startup','memory-failure'):
            nested=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True)
            (a.root/'nested.json').write_text(json.dumps(dict(pid=nested.pid)))
            time.sleep(30)
        if a.native and a.worker==1 and not a.browser_fixture:
            from verification.direct_reference import instrumented_probe as probe
            original_popen=subprocess.Popen
            def fixture_browser(command,**kwargs):
                assert command[2]=='verification.direct_reference.instrumented_probe'
                output=command[command.index('--output')+1]
                replacement=[sys.executable,'-m','tests.four_council_release_fixture_cli','--root',str(a.root),'--worker','1','--output',output,'--browser-fixture']
                if a.successor:replacement+=['--successor','--fault',a.fault]
                if '--execution-budget' in command:  # added by the production supervised() pass-through
                    assert command[command.index('--execution-budget')+1]==budget_name;replacement+=budget_args
                if '--prepared-font-cache' in command:  # added by the production supervised() pass-through
                    i=command.index('--prepared-font-cache');replacement+=command[i:i+4]
                return original_popen(replacement,**kwargs)
            with patch.object(probe.subprocess,'Popen',fixture_browser):
                probe.supervised('discovery_rochdale_ui_window',a.output,execution_mode='four-council-owner-local',window=('2026-10-08','2026-10-14'),retain_proof=True,**({'prepared_font_cache':selection} if selection else {}),**({'execution_budget':budget_name} if budget_name else {}))
            return 0
        value=source_value(a.worker)
        r.write_new(a.output,canonical(value));return 0
    a.root.mkdir(parents=True,exist_ok=True)
    reg=(successor_registration() if a.successor else registration())
    if budget_name:reg=r.render(reg['release_id'],reg['revision'],reg['tree'],reg['evidence_head'],reg['issued_at'],reg['expires_at'],released=True,version=r.SUCCESSOR_V2_VERSION)
    reg.update(revision=r.git('rev-parse','HEAD'),tree=r.git('rev-parse','HEAD^{tree}'))
    api=API(reg);original=api.runner;head_reads=[0]
    def transport(command,**kwargs):
        if command[3]=='GET' and '/git/ref/' in command[4]:
            head_reads[0]+=1
            if a.fault=='cancel-startup' and head_reads[0]>=5:api.ref_moved=True
            if a.fault=='cancel' and (a.root/'nested.json').exists():api.ref_moved=True
        if a.fault=='unavailable' and '/contents/' in command[4]:raise TimeoutError('synthetic unavailable control')
        if a.fault=='publication-failure' and command[3]=='POST' and command[4].endswith('/git/blobs'):
            import base64
            raw=base64.b64decode(json.loads(kwargs['input'])['content'])
            if b'result_before_final_publication' in raw:raise TimeoutError('synthetic lost publication acknowledgement')
        return original(command,**kwargs)
    original_source=r.Source;original_memory=r.OperationalMemory
    survivor_group=[]  # exact source group that received the memory-survivor process
    class FixtureSource(original_source):
        def run(self,index,check):
            if a.fault=='memory-failure':
                from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
                def fail():raise MemoryUnavailable('MEMORY_LIMIT_HIT')
                self.memory.snapshot=fail
            if a.fault=='memory-survivor':
                latch=self.memory.latch;memory=self.memory
                def survivor_after_latch():
                    value=latch()
                    def attach():
                        with open(memory.source/'cgroup.procs','w') as stream:stream.write(str(os.getpid()))
                    # Detached (double fork): not a controller child, so the populated-source
                    # check itself must refuse. Killed via the recorded group's cgroup.kill after
                    # the run; its 60s lifetime stays below the scope's RuntimeMaxSec backstop.
                    survivor_group.append(memory.source)
                    subprocess.run([sys.executable,'-c','import os,time\nif os.fork()==0:\n    time.sleep(60)'],preexec_fn=attach,start_new_session=True,check=True)
                    return value
                self.memory.latch=survivor_after_latch
            try:return super().run(index,check)
            except r.SourceFailure:
                if a.fault=='memory-enforcement-lost':(self.memory.source/'memory.max').write_text(str(2*1024**3))
                raise
        def command(self,index,out):
            # The production command carries the budget; the fixture worker inherits it from there.
            production=super().command(index,out)
            assert ('--execution-budget' in production)==bool(budget_name)
            return [sys.executable,'-m','tests.four_council_release_fixture_cli','--root',str(a.root),'--worker',str(index),'--output',str(out),'--fault',a.fault]+(['--native'] if a.native else [])+(['--successor'] if a.successor else [])+font_args+budget_args
    class SyntheticSource:
        # Contract simulation for hosts with mismatched /proc. The native mode
        # below runs real Popen/preexec/cgroup cancellation, not this substitute.
        def __init__(self,memory,registration,root):self.root=root;self.memory=memory
        def run(self,index,check):
            if a.fault=='memory-failure':
                from verification.ingestion_storage.memory_enforcement import MemoryUnavailable
                def fail():raise MemoryUnavailable('MEMORY_LIMIT_HIT')
                self.memory.snapshot=fail
                raise r.SourceFailure(r.failure_detail(MemoryUnavailable('MEMORY_LIMIT_HIT'),'SOURCE_MEMORY_CHECK'),dict(source_group_closed=True,child_reaped=True,failures=[]))
            check();return source_value(index),dict(source_group_closed=True,supervised_seconds=.01)
    if a.fault=='real-chromium':
        # Local browser package only; the fixture page is inline and every request is aborted.
        (a.root/'.cache').mkdir(exist_ok=True)
        (a.root/'.cache/ms-playwright').symlink_to(os.environ.get('PLAYWRIGHT_BROWSERS_PATH',str(Path.home()/'.cache/ms-playwright')))
        # Residency before the measured run (read-only; nothing is warmed by measuring).
        import playwright
        from verification.direct_reference.prepared_font_cache import headless_shell_executable
        sets=dict(browser=headless_shell_executable(str((a.root/'.cache/ms-playwright').resolve())).parent,
                  driver=Path(playwright.__file__).parent/'driver',fonts=Path('/usr/share/fonts'),
                  **({'prepared_cache':Path(selection[0])} if selection else {}))
        (a.root/'residency-before.json').write_text(json.dumps(residency(sets)))
    os.environ['HOME']=str(a.root)
    for key in list(os.environ):
        if any(k in key.upper() for k in ('DATABASE','SUPABASE','OPENAI','ANTHROPIC')):os.environ.pop(key)
    reg_path=a.root/'registration.json';reg_path.write_bytes(canonical(reg))
    original_emit=r.Journal.emit
    def emit(journal,event,payload):
        if a.fault=='reporting-failure' and event=='result_before_final_publication':raise OSError('synthetic reporting failure')
        return original_emit(journal,event,payload)
    original_validate=r.validate
    original_read=Path.read_text
    def read(path,*args,**kwargs):
        value=original_read(path,*args,**kwargs)
        if str(path)=='/proc/self/stat' and not a.native:return str(os.getpid())+' '+value.split(' ',1)[1]
        return value
    def memory(**limits):
        # V1 keeps the unchanged no-argument call; V2 passes its exact keyword limits.
        assert bool(limits)==bool(budget_name)
        return original_memory(**limits) if a.native else Memory(a.root)
    def github(emit,check,**kwargs):return GitHub(emit,check,runner=transport,**kwargs)
    with patch.object(r.Journal,'emit',emit),patch.object(r,'Source',FixtureSource if a.native else SyntheticSource),patch.object(r,'OperationalMemory',memory),patch.object(r,'GitHub',github),patch.object(r,'validate',lambda value:original_validate(value,checkout=a.native)),patch.object(Path,'read_text',read):
        fake_process=type('Process',(),{'children':lambda self,recursive:[]})()
        context=patch('psutil.Process',lambda:fake_process) if not a.native else __import__('contextlib').nullcontext()
        with context,patch.object(sys,'argv',['fixed-release','run','--registration',str(reg_path),'--registration-sha256',r.sha(reg_path.read_bytes()),'--enable-reviewed-source-only-stop-treatment']):
            try:code=r.main()
            finally:
                state=a.root/'.local/state/propertyaigent'/reg['release_id']
                (state/'reclaim.bin').unlink(missing_ok=True)
                for group in survivor_group:(group/'cgroup.kill').write_text('1')
    final=a.root/'.local/state/propertyaigent'/reg['release_id']/'final-result.json'
    value=json.loads(final.read_bytes())
    assert value['database_connections']==value['application_writes']==0
    assert code==(0 if a.fault=='none' or (a.fault=='real-chromium' and not value['containment_observation'].get('groups',{}).get('source',{}).get('memory.events',{}).get('max')) else 1)
    source_memory=value['containment_observation'].get('groups',{}).get('source',{})
    if a.native and 'memory.max' in source_memory:  # exact selected ceilings, whatever the outcome
        groups=value['containment_observation']['groups']
        expected=(1536*1024**2,2048*1024**2) if budget_name else (1024**3,1536*1024**2)
        enforcement_lost=a.fault=='memory-enforcement-lost'  # this fault rewrites source memory.max
        assert enforcement_lost or source_memory['memory.max']==expected[0]
        assert groups['aggregate']['memory.max']==expected[1] and groups['controller']['memory.max']==256*1024**2
    if a.fault=='none' or (a.fault=='real-chromium' and not source_memory.get('memory.events',{}).get('max')):
        assert len(value['results'])==(3 if a.successor else 4) and value['cleanup']=='CLOSED'
    browser_evidence=json.loads((a.root/'browser-evidence.json').read_text()) if a.fault=='real-chromium' and (a.root/'browser-evidence.json').exists() else None
    if a.fault=='real-chromium' and not source_memory.get('memory.events',{}).get('max'):
        assert browser_evidence is not None and browser_evidence['mode']==('prepared' if selection else 'default')
        if selection:  # functional cache use inside the source group; nothing written to the per-run HOME
            assert browser_evidence['mapped'] and all(m.startswith(selection[0]+'/') for m in browser_evidence['mapped'])
            assert browser_evidence['home_fontconfig']==[]
        else:assert browser_evidence['home_fontconfig'] and not browser_evidence['mapped']  # default rebuild
    if a.fault=='unknown':assert len(value['results'])==1 and len(value['not_attempted'])==(2 if a.successor else 3)
    if a.fault.startswith('local-'):
        assert a.successor and len(value['results'])==3 and not value['not_attempted']
        assert value['status']=='OBSERVATIONS_FINISHED_WITH_GAPS' and value['accounting_complete']
        assert value['cleanup']=='CLOSED' and value['final_publication']=='VERIFIED'
    if a.fault=='memory-failure':
        assert value['failure']['stage']=='SOURCE_MEMORY_CHECK' and value['reason']=='MEMORY_LIMIT_HIT'
        assert value['cleanup']=='UNCERTAIN' and value['child_socket_closure']=='CLOSED'
        assert value['owned_group_closure']=='CLOSED' and not value['accounting_complete']
        # Native: the real kernel shows no event after the latch, so finalisation exports
        # and removes groups. The contract double has no latch, so export stays held.
        assert value['local_evidence_packet']['status']=='PRESERVED' and value['final_publication']==('VERIFIED' if a.native else 'UNCERTAIN_OR_HELD')
        assert value['finalisation']['state']==('FINALISATION_ONLY' if a.native else 'NOT_LATCHED')
        assert len(value['not_attempted'])==2 and not value['results']
    elif a.fault in MEMORY_FAULTS or (a.fault=='real-chromium' and source_memory.get('memory.events',{}).get('max')):
        assert a.native and a.successor and code==1
        # A real kernel event is detected by whichever in-source gate polls first; both call snapshot().
        assert value['failure']['stage'] in ('SOURCE_MEMORY_CHECK','SOURCE_CONTROL_CHECK')
        assert {k:v for k,v in value['failure'].items() if k!='stage'}==dict(code='MEMORY_LIMIT_HIT',kind='MEMORY',message_exported=False)
        events=source_memory['memory.events'];assert events['max']>0 and events['oom']==events['oom_kill']==0
        assert value['source_outcome']=='UNVERIFIED' and value['accounting_status']=='PARTIAL_SOURCE_USAGE_UNKNOWN'
        assert value['source_usage']==dict(requests=None,mixed_bytes=None,worker_seconds=None)
        assert len(value['not_attempted'])==2 and not value['results'] and len(value['accounting']['reservations'])==1
        assert value['cleanup']=='UNCERTAIN' and value['status']=='STOP_RECONCILE_NO_RETRY'
        if a.fault in ('memory-reclaim','real-chromium'):
            assert value['finalisation']['state']=='FINALISATION_ONLY' and value['finalisation']['latched_counters']['source']['max']==events['max']
            assert value['final_publication']=='VERIFIED' and value['owned_group_closure']=='CLOSED'
            assert value['owned_cleanup']['owned_groups_removed'] and value['owned_cleanup']['finalisation']=='LATCHED_COUNTERS_UNCHANGED'
        else:
            assert value['final_publication']=='UNCERTAIN_OR_HELD' and value['owned_group_closure']=='NOT_VERIFIED'
            expected=(('MEMORY_FAILURE_LATCH','MEMORY_ENFORCEMENT_LOST') if a.fault=='memory-enforcement-lost' else ('FINAL_PUBLICATION','SOURCE_SURVIVORS'))
            assert any((x['stage'],x['code'])==expected for x in value['reporting_failures'])
            if a.fault=='memory-survivor':
                assert any((x['stage'],x['code'])==('FINAL_CONTAINMENT_CHECK','SOURCE_SURVIVORS') for x in value['reporting_failures'])
                assert value['child_socket_closure']=='CLOSED'  # refused by the kernel group check, not psutil
    elif a.fault=='reporting-failure':
        assert value['final_publication']=='VERIFIED' and value['cleanup']=='CLOSED'
        assert any(x['stage']=='FINAL_AUDIT_EVENT' for x in value['reporting_failures'])
    elif a.fault=='publication-failure':
        assert value['final_publication']=='UNCERTAIN_OR_HELD' and value['cleanup']=='UNCERTAIN'
        assert value['local_evidence_packet']['status']=='PRESERVED' and value['owned_group_closure']=='CLOSED'
    if a.native and a.fault not in ('memory-enforcement-lost','memory-survivor'):assert value['owned_cleanup']['owned_groups_removed'] and value['process_cleanup']=='CLOSED'
    (a.root/'rehearsal.json').write_bytes(canonical(value))
    print(json.dumps(dict(rehearsal='NATIVE_CGROUP_FIXTURE' if a.native else 'CONTRACT_SIMULATION',fault=a.fault,verified=True,
        source_memory={k:source_memory.get(k) for k in ('memory.peak','memory.current','memory.events','memory.stat')},
        **({'browser_evidence':browser_evidence,'residency_before':json.loads((a.root/'residency-before.json').read_text())} if a.fault=='real-chromium' else {}))))
    return 0

if __name__=='__main__':sys.exit(main())
