"""Linux document-only Chromium guardian; private bounded CDP pipes, no listener.

Executed by a generated trusted launcher, never imported by document JavaScript.
The network filter is installed before Chromium exec and inherited by descendants.
RSS limits are sampled fail-closed limits, not kernel cgroup memory ceilings.
"""
from __future__ import annotations
from contextlib import contextmanager
import array
import ctypes as C
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import signal
import socket
import stat
import struct
import sys
import time

FRAME_LIMIT = 32 * 1024 * 1024
QUEUE_LIMIT = 64 * 1024 * 1024
RENDERER_RSS_LIMIT = 512 * 1024 * 1024
PARENT_GROWTH_LIMIT = 256 * 1024 * 1024
COMBINED_GROWTH_LIMIT = 768 * 1024 * 1024
TEMP_LIMIT = 512 * 1024 * 1024
PROCESS_LIMIT = 32
REQUEST_LIMIT = 128
LIFETIME_LIMIT = 300
SAMPLE_SECONDS = .1

# Reviewed Chrome Headless Shell 153.0.8010.12 only. An unknown executable keeps
# the original fatal-denial policy; this pin never grants a native syscall.
STARTUP_CHROMIUM_SHA256 = 'ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e'
STARTUP_PROBES = frozenset({(16, 3, 0), (16, 526339, 15)})


def startup_executable_identity(executable):
    with executable.open('rb') as stream:
        before=os.fstat(stream.fileno())
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
        after=os.fstat(stream.fileno())
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if identity(before)!=identity(after) or identity(after)!=identity(executable.stat()):
        raise ContainmentError('Chromium executable changed during verification')
    return identity(after) if digest==STARTUP_CHROMIUM_SHA256 else None


class StartupProbes:
    """Finite audited EPERM classification, never a syscall permission."""
    def __init__(self,executable_identity):
        self.executable_identity=executable_identity;self.seen=set()

    def classify(self,notification,report,relay):
        probe=tuple(notification.data.args[:3])
        if (self.executable_identity is None or not relay.startup_probes_open or
            notification.data.arch!=0xc000003e or notification.data.nr!=41 or
            probe not in STARTUP_PROBES or probe in self.seen):return None
        try:
            status=Path(f'/proc/{notification.pid}/status').read_text()
            tgid=int(next(line.split()[1] for line in status.splitlines() if line.startswith('Tgid:')))
            root=proc_info(tgid)
            executable=Path(f'/proc/{notification.pid}/exe').stat()
            identity=(executable.st_dev,executable.st_ino,executable.st_size,executable.st_mtime_ns,executable.st_ctime_ns)
            if (tgid!=report['group_host'] or root['start']!=report['group_start'] or
                root['group']!=report['group_host'] or root['ppid']!=report['guardian_host'] or
                identity!=self.executable_identity):return None
        except (OSError,ValueError,StopIteration):return None
        self.seen.add(probe)
        return dict(tid=notification.pid,tgid=tgid,start=root['start'],family=probe[0],
                    type=probe[1],protocol=probe[2],result='EPERM',phase='before-first-browser-response')

class ContainmentError(RuntimeError):
    pass

class Filter(C.Structure):
    _fields_=[('code',C.c_ushort),('jt',C.c_ubyte),('jf',C.c_ubyte),('k',C.c_uint)]
class Program(C.Structure):
    _fields_=[('length',C.c_ushort),('filters',C.POINTER(Filter))]
class Data(C.Structure):
    _fields_=[('nr',C.c_int),('arch',C.c_uint),('ip',C.c_ulonglong),('args',C.c_ulonglong*6)]
class Notification(C.Structure):
    _fields_=[('id',C.c_ulonglong),('pid',C.c_uint),('flags',C.c_uint),('data',Data)]
class Response(C.Structure):
    _fields_=[('id',C.c_ulonglong),('val',C.c_longlong),('error',C.c_int),('flags',C.c_uint)]


def native_filter():
    if sys.platform!='linux' or os.uname().machine!='x86_64':
        raise ContainmentError('Unsupported native containment platform')
    # x86-64 only; explicitly reject x32/alternate audit architectures.
    allow=0x7fff0000;notify=0x7fc00000;deny=0x50000|errno.EPERM
    ins=[(0x20,0,0,4),(0x15,1,0,0xc000003e),(0x06,0,0,notify),
         (0x20,0,0,0),(0x45,0,1,0x40000000),(0x06,0,0,notify),
         # socket(): Unix ancillary services denied too; never create an endpoint.
         (0x15,0,4,41),(0x20,0,0,16),(0x15,0,1,socket.AF_UNIX),
         (0x06,0,0,deny),(0x06,0,0,notify),
         # Only connected STREAM/SEQPACKET pairs, no addressable DGRAM pairs.
         (0x15,0,9,53),(0x20,0,0,16),(0x15,1,0,socket.AF_UNIX),(0x06,0,0,notify),
         (0x20,0,0,24),(0x54,0,0,15),(0x15,2,0,socket.SOCK_STREAM),
         (0x15,1,0,socket.SOCK_SEQPACKET),(0x06,0,0,notify),(0x06,0,0,allow)]
    # connect/bind/listen, io_uring, fd/memory import, process-group/namespace escape.
    for syscall in (42,49,50,425,426,427,438,101,310,311,109,112,272,308):
        ins.extend([(0x15,0,1,syscall),(0x06,0,0,notify)])
    # clone3 has pointer-based flags; ENOSYS requests libc's inspectable clone fallback.
    ins.extend([(0x15,0,1,435),(0x06,0,0,0x50000|errno.ENOSYS),
                (0x15,0,3,56),(0x20,0,0,16),(0x45,0,1,0x7e028080),
                (0x06,0,0,notify)])
    ins.append((0x06,0,0,allow))
    filters=(Filter*len(ins))(*(Filter(*x) for x in ins));prog=Program(len(ins),filters)
    libc=C.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0)!=0:raise ContainmentError('Cannot set no_new_privs')
    fd=libc.syscall(317,1,8,C.byref(prog))  # seccomp SET_MODE_FILTER NEW_LISTENER
    if fd<0:raise ContainmentError('Native notification filter unavailable')
    return fd


def proc_info(host_pid):
    text=Path(f'/proc/{host_pid}/stat').read_text();tail=text[text.rfind(')')+2:].split()
    return dict(host_pid=int(text.split(' ',1)[0]),state=tail[0],ppid=int(tail[1]),group=int(tail[2]),start=int(tail[19]),rss=int(tail[21])*os.sysconf('SC_PAGE_SIZE'))


def signal_owned_group(report):
    """Never signal a recycled PID/group based only on a stale numeric ID."""
    try:
        root=proc_info(report['group_host'])
    except (FileNotFoundError,ProcessLookupError):
        root=None
    if root is not None and root['start']!=report['group_start']:
        raise ContainmentError('Renderer process identity changed')
    members=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():continue
        try:info=proc_info(int(entry.name))
        except (FileNotFoundError,ProcessLookupError):continue
        if info['group']==report['group_host']:members.append(info)
    if any(info['start']<report['group_start'] for info in members):
        raise ContainmentError('Renderer process group identity changed')
    if members:
        try:os.killpg(report['group'],signal.SIGKILL)
        except ProcessLookupError:pass


def own_host_pid():
    return int(Path('/proc/self/stat').read_text().split(' ',1)[0])


def descendants(host_pid):
    # Some supported Linux builds omit /proc/PID/task/TID/children. Build the
    # actual PPID graph from stat; never interpret a missing children file as 0.
    processes={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():continue
        try:processes[int(entry.name)]=proc_info(int(entry.name))
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:raise ContainmentError('Process resource accounting denied') from None
    found={};pending=[host_pid]
    while pending:
        pid=pending.pop()
        if pid in found:continue
        if pid not in processes:continue
        found[pid]=processes[pid]
        pending.extend(p for p,info in processes.items() if info['ppid']==pid)
        if len(found)>PROCESS_LIMIT:raise ContainmentError('Renderer process count exceeded')
    if host_pid not in found:raise ContainmentError('Supervisor resource accounting unavailable')
    return found


def audit_pipes():
    # Node implements child stdio pipes using unnamed connected Unix streams.
    # Only the trusted guardian retains them; Chromium receives fresh OS pipes.
    for fd in range(5):
        mode=os.fstat(fd).st_mode
        if stat.S_ISSOCK(mode):
            with socket.socket(fileno=os.dup(fd)) as channel:
                if channel.getsockopt(socket.SOL_SOCKET,socket.SO_DOMAIN)!=socket.AF_UNIX or channel.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM or channel.getpeername() not in ('',b''):
                    raise ContainmentError('Inherited external socket denied')
                peer=struct.unpack('3i',channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[0]
                if peer!=os.getppid():raise ContainmentError('Unexpected CDP channel peer')
        elif fd in (3,4) and not stat.S_ISFIFO(mode):
            raise ContainmentError('Private CDP channels required')
    close_except({0,1,2,3,4})


def close_except(keep):
    for name in os.listdir('/proc/self/fd'):
        fd=int(name)
        if fd not in keep:
            try:os.close(fd)
            except OSError:pass


class Relay:
    def __init__(self):
        self.startup_probes_open=True
        self.partial=[bytearray(),bytearray()];self.output=[bytearray(),bytearray()]
        self.pending={};self.seen=set();self.max_queue=0;self.max_frame=0;self.shutdown_requested=False
    def accept(self,direction,data):
        # Close before forwarding even a partial browser response/event. No
        # document content can be introduced by the sole startup getVersion.
        if direction==1 and data:self.startup_probes_open=False
        self.partial[direction].extend(data)
        while b'\0' in self.partial[direction]:
            position=self.partial[direction].index(0)
            if position>FRAME_LIMIT:raise ContainmentError('CDP frame limit exceeded')
            raw=bytes(self.partial[direction][:position]);del self.partial[direction][:position+1]
            try:
                message=json.loads(raw,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
            except (ValueError,UnicodeError):raise ContainmentError('Malformed CDP JSON') from None
            if not isinstance(message,dict):raise ContainmentError('Malformed CDP envelope')
            key=message.get('id');method=message.get('method')
            if direction==0:
                if self.seen or method!='Browser.getVersion':self.startup_probes_open=False
                if not isinstance(key,int) or isinstance(key,bool) or (key<=0 and not (key==-9999 and method=='Browser.close')) or key in self.seen or not isinstance(method,str):
                    raise ContainmentError('Stale or malformed CDP request')
                self.pending[key]=message.get('sessionId');self.seen.add(key)
                if method=='Browser.close':self.shutdown_requested=True
                if len(self.pending)>REQUEST_LIMIT or len(self.seen)>16384:raise ContainmentError('CDP request bound exceeded')
            elif key is not None:
                if not isinstance(key,int) or isinstance(key,bool) or key not in self.pending or message.get('sessionId')!=self.pending[key]:raise ContainmentError('Mismatched CDP response')
                del self.pending[key]
            elif not isinstance(method,str):raise ContainmentError('Malformed CDP event')
            self.max_frame=max(self.max_frame,len(raw));self.output[direction].extend(raw+b'\0')
        if len(self.partial[direction])>FRAME_LIMIT:raise ContainmentError('CDP frame limit exceeded')
        size=sum(map(len,self.partial+self.output));self.max_queue=max(self.max_queue,size)
        if size>QUEUE_LIMIT:raise ContainmentError('CDP queue bound exceeded')


def wait_clean_exit(child, deadline, check):
    """Shutdown is successful only with a clean exit; watchdogs stay active."""
    end=min(deadline,time.monotonic()+5)
    while time.monotonic()<end:
        check()
        exited,status=os.waitpid(child,os.WNOHANG)
        if exited==child:
            if status:raise ContainmentError('Document renderer crashed during shutdown')
            return
        time.sleep(.01)
    raise ContainmentError('Document renderer shutdown incomplete')


def parent_alive(config):
    try:info=proc_info(config['parent_host'])
    except (FileNotFoundError,ProcessLookupError):return False
    return info['start']==config['parent_start'] and info['state'] not in ('Z','X')


def owned_outputs(directory):
    journal=directory/'outputs.json'
    if not journal.exists():return []
    with journal.open('rb') as stream:raw=stream.read(1024*1024+1)
    if len(raw)>1024*1024:raise ContainmentError('Document output journal exceeded bound')
    value=json.loads(raw)
    if value.get('version')!=1 or not isinstance(value.get('files'),list) or len(value['files'])>128:
        raise ContainmentError('Invalid document output journal')
    for row in value['files']:
        if set(row)!={'target','backup','partial'}:raise ContainmentError('Invalid output ownership')
        target=Path(row['target']);partial=Path(row['partial'])
        if not target.is_absolute() or partial.parent!=target.parent or not partial.name.startswith('.document-'):
            raise ContainmentError('Invalid output path ownership')
        if row['backup'] is not None and Path(row['backup']).parent!=directory:
            raise ContainmentError('Invalid output backup ownership')
    return value['files']


@contextmanager
def output_lock(root,deadline):
    with (root/'outputs.lock').open('a+b') as lock:
        while True:
            try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise ContainmentError('Document output ownership timed out')
                time.sleep(.01)
        try:yield
        finally:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def remove_owned_job(directory,config, *, committed=False):
    """Trusted-parent ownership marker; never recursively delete an arbitrary path."""
    root=directory.parent
    if not config.get('remove_on_parent_loss'):return
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700 or not root.name.startswith('propertyaigent-document-'):
        raise ContainmentError('Document directory ownership invalid')
    if (root/'.document-owner').read_text()!=config['job']:raise ContainmentError('Document directory owner changed')
    with output_lock(root,time.monotonic()+5):
        outputs=owned_outputs(root)
        for row in outputs:
            target=Path(row['target']);Path(row['partial']).unlink(missing_ok=True)
            if not committed:
                if row['backup'] is None:target.unlink(missing_ok=True)
                else:shutil.copyfile(row['backup'],target)
        shutil.rmtree(root)
        if root.exists() or any(Path(row['partial']).exists() for row in outputs):raise ContainmentError('Document directory cleanup incomplete')


def stop_owned_writers(report, deadline):
    """Wait for the pinned guardian and its group before removing their files."""
    signal_owned_group(report)
    while time.monotonic()<deadline:
        try:guardian=proc_info(report['guardian_host'])
        except (FileNotFoundError,ProcessLookupError):guardian=None
        if guardian is not None and guardian['start']!=report['guardian_start']:
            raise ContainmentError('Guardian identity changed during file cleanup')
        guardian_alive=guardian is not None and guardian['state'] not in ('Z','X')
        if guardian_alive:
            try:os.kill(report['guardian'],signal.SIGTERM)
            except ProcessLookupError:pass
        try:os.killpg(report['group'],0);group_alive=True
        except ProcessLookupError:group_alive=False
        if not guardian_alive and not group_alive:return
        time.sleep(.01)
    raise ContainmentError('Document writers survived cleanup deadline')


def file_custodian(config_path):
    """Independent file owner survives the launcher's planned Browser.close exit."""
    directory=Path(config_path).parent;root=directory.parent
    config=json.loads(Path(config_path).read_text())
    if not config.get('remove_on_parent_loss'):raise ContainmentError('Unowned custodian job')
    info=proc_info(own_host_pid())
    ready=dict(job=config['job'],pid=os.getpid(),host=info['host_pid'],start=info['start'])
    (directory/'custodian-ready.next').write_text(json.dumps(ready));(directory/'custodian-ready.next').replace(directory/'custodian-ready.json')
    deadline=config['job_deadline'];buffer=bytearray();ack=None;state='unacknowledged'
    os.set_blocking(0,False)
    while True:
        # Consume the authenticated private pipe before testing directory absence.
        try:data=os.read(0,4097)
        except BlockingIOError:data=b''
        if data:
            buffer.extend(data)
            if len(buffer)>4096:raise ContainmentError('Custodian acknowledgement exceeded bound')
            if b'\n' in buffer:
                if ack is not None:raise ContainmentError('Repeated custodian acknowledgement')
                value=json.loads(buffer)
                if value!={'version':1,'job':config['job'],'state':value.get('state')} or value.get('state') not in ('commit','abort'):
                    raise ContainmentError('Invalid custodian acknowledgement')
                ack=value['state'];buffer.clear()
        alive=parent_alive(config)
        if not root.exists():
            state=ack or 'unacknowledged';break
        expired=time.monotonic()>=deadline-5
        if not alive or expired:
            # The abort marker stops future writes; the lock excludes in-flight
            # copies/replacements. Reserve the existing five seconds for cleanup.
            try:(root/'.document-aborted').touch()
            except FileNotFoundError:
                state=ack or 'unacknowledged';break
            status=directory/'status.json'
            if status.exists():
                report=json.loads(status.read_text())
                if report.get('job')!=config['job']:raise ContainmentError('Custodian process identity mismatch')
                stop_owned_writers(report,deadline)
            remove_owned_job(directory,config,committed=ack=='commit')
            state='commit' if ack=='commit' else 'rolled_back'
            break
        time.sleep(.02)
    # This is a file-removal receipt, not a claim that this process has exited.
    # Only the parent can establish the final closed postcondition after reaping.
    result=dict(version=1,job=config['job'],state=state,files_removed=not root.exists())
    try:os.write(1,json.dumps(result).encode()+b'\n')
    except BrokenPipeError:pass # Parent is gone; cleanup above is already complete.
    if state=='unacknowledged':raise ContainmentError('Document completion was not acknowledged')


def guardian(config_path,arguments):
    config=json.loads(Path(config_path).read_text());directory=Path(config_path).parent
    if config.get('version')!=1 or len(config.get('job',''))!=32:raise ContainmentError('Invalid job configuration')
    executable=Path(config['executable']);parent_host=int(config['parent_host']);parent_start=int(config['parent_start'])
    arguments=[a for a in arguments if not a.startswith('--user-data-dir=')]+['--user-data-dir='+str(directory/'profile')]
    if not executable.is_file() or not os.access(executable,os.X_OK):raise ContainmentError('Chromium executable unavailable')
    if any(a.startswith('--remote-debugging-port') for a in arguments) or '--remote-debugging-pipe' not in arguments:
        raise ContainmentError('Network CDP endpoint forbidden')
    startup_probes=StartupProbes(startup_executable_identity(executable))
    audit_pipes();libc=C.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0)!=0:raise ContainmentError('Cannot supervise descendants')  # subreaper
    control_parent,control_child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    command_read,command_write=os.pipe();response_read,response_write=os.pipe()
    start_read,start_write=os.pipe()
    relay=Relay();selector=selectors.DefaultSelector();native_fd=None
    child=None;group_created=False;stopping=[False]
    report=dict(version=1,job=config['job'],guardian=os.getpid(),guardian_host=own_host_pid(),guardian_start=proc_info(own_host_pid())['start'],failure=None,notifications=0,max_renderer_rss=0,max_parent_growth=0,max_combined_growth=0,max_temp_bytes=0,max_processes=0)
    def save():
        path=directory/'status.next';path.write_text(json.dumps(report));os.replace(path,directory/'status.json')
    signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True));signal.signal(signal.SIGINT,lambda *_:stopping.__setitem__(0,True))
    guardian_pid=os.getpid()
    try:
        child=os.fork()
        if child==0:
            try:
                # Install parent-death protection before the bootstrap barrier.
                if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=guardian_pid:os._exit(78)
                control_parent.close();os.close(start_write)
                if os.read(start_read,1)!=b'1':os._exit(78)
                os.close(start_read)
                os.dup2(command_read,3);os.dup2(response_write,4)
                null=os.open('/dev/null',os.O_RDWR)
                for standard in (0,1,2):os.dup2(null,standard)
                os.close(null)
                listener=native_filter()
                control_child.sendmsg([b'F'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[listener]))])
                control_child.close();os.close(listener);close_except({0,1,2,3,4})
                resource.setrlimit(resource.RLIMIT_FSIZE,(TEMP_LIMIT,TEMP_LIMIT))
                os.execve(str(executable),[str(executable),*arguments],{'HOME':str(directory),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TMPDIR':str(directory/'tmp')})
            except BaseException:
                os._exit(78)
        control_child.close();os.close(start_read);os.setpgid(child,child);group_created=True
        report['group']=child
        owned=[info for info in descendants(report['guardian_host']).values() if info['ppid']==report['guardian_host']]
        if len(owned)!=1:raise ContainmentError('Renderer process identity unavailable')
        report['group_host']=owned[0]['host_pid'];report['group_start']=owned[0]['start']
        save()
        os.write(start_write,b'1');os.close(start_write)
        os.close(command_read);os.close(response_write)
        deadline=config.get('job_deadline',time.monotonic()+LIFETIME_LIMIT)
        control_parent.settimeout(10)
        data,ancillary,flags,_=control_parent.recvmsg(1,socket.CMSG_SPACE(4))
        if data!=b'F' or flags or len(ancillary)!=1:raise ContainmentError('Native filter handoff failed')
        level,kind,raw=ancillary[0]
        if level!=socket.SOL_SOCKET or kind!=socket.SCM_RIGHTS or len(raw)!=4:raise ContainmentError('Invalid filter descriptor')
        native_fd=array.array('i',raw)[0];control_parent.close()
        for fd,direction in ((3,0),(response_read,1)):
            os.set_blocking(fd,False);selector.register(fd,selectors.EVENT_READ,('read',direction))
        selector.register(native_fd,selectors.EVENT_READ,('native',0))
        for fd in (command_write,4):os.set_blocking(fd,False)
        parent_baseline=proc_info(parent_host)['rss'];guardian_host=own_host_pid();driver_host=proc_info(guardian_host)['ppid'];driver_baseline=proc_info(driver_host)['rss'];sample=0;child_status=None
        def check_shutdown():
            nonlocal sample
            now=time.monotonic()
            if stopping[0] or now>=deadline:raise ContainmentError('Document shutdown cancelled or expired')
            if now<sample:return
            sample=now+SAMPLE_SECONDS
            parent=proc_info(parent_host)
            if parent['start']!=parent_start:raise ContainmentError('Document parent identity changed')
            processes=descendants(guardian_host);renderer_rss=sum(x['rss'] for p,x in processes.items() if p!=guardian_host)
            if config.get('custodian_host'):
                owner=proc_info(config['custodian_host'])
                if owner['start']!=config['custodian_start'] or owner['state'] in ('Z','X'):raise ContainmentError('File custodian identity lost')
                processes[owner['host_pid']]=owner
                report['max_custodian_rss']=max(report.get('max_custodian_rss',0),owner['rss'])
                if len(processes)>PROCESS_LIMIT:raise ContainmentError('Document process count exceeded')
            growth=max(0,parent['rss']-parent_baseline)+max(0,proc_info(driver_host)['rss']-driver_baseline);combined=growth+sum(x['rss'] for x in processes.values())
            size=0
            for path in list(directory.parent.rglob('*'))+[Path(row['partial']) for row in owned_outputs(directory.parent)]:
                try:
                    if path.is_file():size+=path.stat().st_size
                except FileNotFoundError:pass # A deleted file no longer consumes named storage.
            for name,value in [('max_renderer_rss',renderer_rss),('max_parent_growth',growth),('max_combined_growth',combined),('max_temp_bytes',size),('max_processes',len(processes))]:report[name]=max(report[name],value)
            if renderer_rss>RENDERER_RSS_LIMIT or growth>PARENT_GROWTH_LIMIT or combined>COMBINED_GROWTH_LIMIT:raise ContainmentError('Document memory bound exceeded')
            if size>TEMP_LIMIT:raise ContainmentError('Document temporary storage bound exceeded')
            save()
        report['native_ready']=True;save()
        while True:
            now=time.monotonic()
            if stopping[0]:raise ContainmentError('Document job cancelled')
            if now>=deadline:raise ContainmentError('Document process lifetime exceeded')
            check_shutdown()
            for key,_ in selector.select(.02):
                kind,direction=key.data
                if kind=='native':
                    notification=Notification()
                    if libc.ioctl(native_fd,0xc0502100,C.byref(notification))!=0:
                        report['notification_errno']=C.get_errno();report['shutdown_requested']=relay.shutdown_requested
                        # ENOENT can mean a canceled notification or filtered-task exit.
                        # Accept it only after trusted shutdown AND clean child exit;
                        # the finally block still kills/reaps the entire owned group.
                        if report['notification_errno']==errno.ENOENT and relay.shutdown_requested:
                            wait_clean_exit(child,deadline,check_shutdown)
                            return
                        raise ContainmentError('Native notification failure')
                    # Attribute while the notifying task is stopped, then deny.
                    startup_event=startup_probes.classify(notification,report,relay)
                    response=Response(notification.id,0,-errno.EPERM,0)
                    if libc.ioctl(native_fd,0xc0182101,C.byref(response))!=0:
                        raise ContainmentError('Native denial response failed')
                    report['notifications']+=1;report['syscall']=notification.data.nr;report['notification_pid']=notification.pid;report['syscall_arch']=notification.data.arch
                    if notification.data.nr==41:report['socket_family']=notification.data.args[0]
                    if startup_event is not None:
                        report.setdefault('startup_probe_denials',[]).append(startup_event)
                        save();continue
                    raise ContainmentError('Native document transport denied')
                data=os.read(key.fd,65536)
                if not data:
                    if kind=='read' and relay.shutdown_requested:
                        wait_clean_exit(child,deadline,check_shutdown)
                        return
                    raise ContainmentError('Document renderer pipe closed')
                relay.accept(direction,data)
            for direction,fd in ((0,command_write),(1,4)):
                if relay.output[direction]:
                    try:
                        count=os.write(fd,relay.output[direction][:65536]);del relay.output[direction][:count]
                    except BlockingIOError:pass
            result,status=os.waitpid(child,os.WNOHANG)
            if result:
                child_status=status
                if status or not relay.shutdown_requested:raise ContainmentError('Document renderer crashed')
                return
    except BaseException as exc:
        report['failure']=str(exc) if isinstance(exc,ContainmentError) else 'Document supervisor failure: '+type(exc).__name__
        print(report['failure'],file=sys.stderr,flush=True)
        raise
    finally:
        report['max_cdp_frame']=relay.max_frame;report['max_cdp_queue']=relay.max_queue
        if child is not None:
            try:
                if group_created:os.killpg(child,signal.SIGKILL)
                else:os.kill(child,signal.SIGKILL)
            except ProcessLookupError:pass
        cleanup_complete=False
        end=time.monotonic()+5
        while time.monotonic()<end:
            try:
                pid,_=os.waitpid(-1,os.WNOHANG)
                if pid==0:time.sleep(.01)
            except ChildProcessError:
                cleanup_complete=True;break
        else:report['failure']=report['failure'] or 'Document descendant cleanup incomplete'
        report['closed']=cleanup_complete
        try:save()
        finally:
            selector.close();control_parent.close();control_child.close()
            for fd in (command_read,command_write,response_read,response_write,start_read,start_write,native_fd):
                if fd is not None:
                    try:os.close(fd)
                    except OSError:pass
            if not config.get('custodian_host') and not parent_alive(config):remove_owned_job(directory,config)

if __name__=='__main__':
    try:
        if sys.argv[1]=='--custodian':file_custodian(sys.argv[2])
        else:guardian(sys.argv[1],sys.argv[2:])
    except BaseException as exc:
        print('Document guardian bootstrap failed: '+(str(exc) if isinstance(exc,ContainmentError) else type(exc).__name__),file=sys.stderr,flush=True)
        raise SystemExit(78)

# Parent API; the guardian subprocess does not invoke this context manager.
from contextlib import contextmanager
import secrets
import shlex
import threading
import subprocess

EXTRA_BROWSER_ARGS = ()  # Tests may supply fixture ICE flags; never grants network.
_document_slot = threading.BoundedSemaphore(1)


def collect_custodian(process):
    """Bound both receipt pipes and reap even a hung or malformed file owner."""
    output=bytearray();errors=bytearray();failure=None
    deadline=time.monotonic()+5
    try:
        for stream in (process.stdout,process.stderr):os.set_blocking(stream.fileno(),False)
        while True:
            for stream,buffer in ((process.stdout,output),(process.stderr,errors)):
                try:chunk=os.read(stream.fileno(),4097-len(buffer))
                except BlockingIOError:chunk=b''
                buffer.extend(chunk)
                if len(buffer)>4096:raise ContainmentError('Custodian receipt exceeded bound')
            if process.poll() is not None:
                # A final drain after exit includes output written just before exit.
                for stream,buffer in ((process.stdout,output),(process.stderr,errors)):
                    buffer.extend(os.read(stream.fileno(),4097-len(buffer)))
                    if len(buffer)>4096:raise ContainmentError('Custodian receipt exceeded bound')
                if process.returncode:raise ContainmentError('Document file custodian failed')
                return bytes(output)
            if time.monotonic()>=deadline-1:raise ContainmentError('Document file custodian did not finish')
            time.sleep(.01)
    finally:
        if process.poll() is None:
            process.kill()
            try:process.wait(timeout=max(.01,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:failure=ContainmentError('Custodian reaping failed; capacity quarantined')
        for stream in (process.stdin,process.stdout,process.stderr):
            if not stream.closed:
                try:stream.close()
                except BrokenPipeError:pass
        if failure:raise failure


def verify_cleanup(directory, report, process, partials):
    """Parent-owned final postconditions; failure quarantines document capacity."""
    if process.poll() is None or any(not stream.closed for stream in (process.stdin,process.stdout,process.stderr)):
        raise ContainmentError('Custodian or descriptors remain; capacity quarantined')
    if directory.parent.exists() or any(Path(path).exists() for path in partials):
        raise ContainmentError('Document files remain; capacity quarantined')
    if report is not None:
        try:guardian=proc_info(report['guardian_host'])
        except (FileNotFoundError,ProcessLookupError):guardian=None
        if guardian is not None and guardian['start']==report['guardian_start']:
            raise ContainmentError('Document guardian remains; capacity quarantined')
        for entry in Path('/proc').iterdir():
            if not entry.name.isdecimal():continue
            try:info=proc_info(int(entry.name))
            except (FileNotFoundError,ProcessLookupError):continue
            if info['group']==report['group_host'] and info['start']>=report['group_start']:
                raise ContainmentError('Document group remains; capacity quarantined')

@contextmanager
def protected_browser(browser_type, directory, *, remove_on_parent_loss=False):
    """One document process per application; unrelated scraper browser untouched."""
    if not _document_slot.acquire(blocking=False):raise ContainmentError('Document process capacity unavailable')
    directory=Path(directory)/'process'
    browser=None;stop=threading.Event();failures=[];monitor=None;last_known=[None];custodian=None;entered=False;acknowledged=False;custodian_result=None;slot_released=False;partials=set()
    job=secrets.token_hex(16);status_path=directory/'status.json';started=time.monotonic()
    def release_slot():
        nonlocal slot_released
        if not slot_released:_document_slot.release();slot_released=True
    def status():
        raw=status_path.read_bytes()
        if len(raw)>8192:raise ContainmentError('Supervisor status exceeded bound')
        value=json.loads(raw)
        if value.get('version')!=1 or value.get('job')!=job:raise ContainmentError('Stale supervisor status')
        last_known[0]=value
        return value
    def finish_files(committed):
        nonlocal acknowledged
        if custodian is None:return
        if directory.parent.exists():partials.update(row['partial'] for row in owned_outputs(directory.parent))
        if custodian.poll() is not None:raise ContainmentError('Document file custodian failed before acknowledgement')
        if not acknowledged:
            if committed:
                with output_lock(directory.parent,started+LIFETIME_LIMIT):
                    if (directory.parent/'.document-aborted').exists() or any(Path(row['partial']).exists() for row in owned_outputs(directory.parent)):
                        raise ContainmentError('Document outputs are not ready to commit')
            payload=dict(version=1,job=job,state='commit' if committed else 'abort')
            custodian.stdin.write(json.dumps(payload).encode()+b'\n');custodian.stdin.flush();custodian.stdin.close()
            acknowledged=True
    def wait_custodian():
        nonlocal custodian_result
        if custodian is None:return None
        if custodian_result is not None:return custodian_result
        try:raw=collect_custodian(custodian)
        finally:
            verify_cleanup(directory,last_known[0],custodian,partials)
            release_slot()
        try:value=json.loads(raw)
        except (ValueError,UnicodeError):raise ContainmentError('Malformed custodian completion') from None
        if not isinstance(value,dict):raise ContainmentError('Invalid custodian completion')
        if value.get('version')!=1 or value.get('job')!=job or not value.get('files_removed') or value.get('state') not in ('commit','abort','rolled_back'):
            raise ContainmentError('Invalid custodian completion')
        value['closed']=True
        custodian_result=value;return value
    status.finish_files=finish_files
    status.wait_custodian=wait_custodian
    def watch():
        known=None
        while not stop.wait(SAMPLE_SECONDS):
            try:
                if status_path.exists():
                    known=status()
                    if custodian is not None and custodian.poll() is not None:
                        failures.append('Document file custodian disappeared');signal_owned_group(known);return
                    if known.get('failure'):failures.append(known['failure']);return
                    if known.get('closed'):return
                    # Native guardian handles parent loss. Parent handles guardian loss.
                    try:
                        info=proc_info(known['guardian_host'])
                        if info['start']!=known['guardian_start']:raise ProcessLookupError()
                    except (FileNotFoundError,ProcessLookupError):
                        failures.append('Document guardian disappeared')
                        signal_owned_group(known)
                        return
                if time.monotonic()-started>LIFETIME_LIMIT:
                    failures.append('Document lifetime exceeded')
                    if known:
                        signal_owned_group(known)
                    return
            except BaseException as exc:
                failures.append('Document status supervision failed: '+type(exc).__name__)
                if known:
                    signal_owned_group(known)
                return
    try:
        directory.mkdir(mode=0o700)
        (directory/'tmp').mkdir(mode=0o700)
        if remove_on_parent_loss:
            if not directory.parent.name.startswith('propertyaigent-document-'):raise ContainmentError('Owned document directory required')
            marker=directory.parent/'.document-owner'
            with marker.open('x') as stream:stream.write(job)
        parent=proc_info(own_host_pid())
        config=dict(version=1,job=job,job_deadline=started+LIFETIME_LIMIT,remove_on_parent_loss=remove_on_parent_loss,executable=os.environ.get('PROPERTYAIGENT_DOCUMENT_CHROMIUM',browser_type.executable_path),parent_host=parent['host_pid'],parent_start=parent['start'])
        config_path=directory/'config.json';config_path.write_text(json.dumps(config));config_path.chmod(0o600)
        if remove_on_parent_loss:
            custodian=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--custodian',str(config_path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,env={'HOME':str(directory),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
            ready_path=directory/'custodian-ready.json';ready_deadline=min(started+30,config['job_deadline'])
            while not ready_path.exists():
                if custodian.poll() is not None or time.monotonic()>=ready_deadline:raise ContainmentError('Document file custodian did not initialise')
                time.sleep(.01)
            ready=json.loads(ready_path.read_text())
            if ready.get('job')!=job:raise ContainmentError('Custodian identity mismatch')
            config['custodian_host']=ready['host'];config['custodian_start']=ready['start']
            config_path.write_text(json.dumps(config))
        launcher=directory/'launch';launcher.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -I '+shlex.quote(str(Path(__file__).resolve()))+' '+shlex.quote(str(config_path))+' "$@"\n');launcher.chmod(0o700)
        monitor=threading.Thread(target=watch,name='document-guardian-monitor',daemon=True);monitor.start()
        browser=browser_type.launch(executable_path=str(launcher),headless=True,downloads_path=str(directory/'downloads'),args=['--no-sandbox','--no-zygote','--disable-background-networking',*EXTRA_BROWSER_ARGS],env={'HOME':str(directory),'PATH':'/usr/bin:/bin'},timeout=30000)
        current=status()
        if failures or current.get('failure') or not current.get('native_ready'):raise ContainmentError('Document containment did not initialise')
        entered=True
        yield browser, status
        current=status()
        if failures or current.get('failure') or not browser.is_connected():raise ContainmentError('Document containment failed')
    finally:
        try:
            if browser is not None:
                browser.close()
                final=status()
                if final.get('failure') or not final.get('closed'):raise ContainmentError(final.get('failure') or 'Document process cleanup failed')
        finally:
            # Covers launch failure and supervisor/status failure, including __enter__.
            try:
                known=last_known[0]
                if known is None and status_path.exists():known=status()
                if known is not None and not known.get('closed'):signal_owned_group(known)
            finally:
                stop.set()
                if monitor is not None:monitor.join(timeout=1)
                if custodian is None:release_slot()
                if custodian is not None and not entered:
                    try:finish_files(False)
                    finally:
                        if directory.parent.exists():remove_owned_job(directory,config)
                        wait_custodian()
