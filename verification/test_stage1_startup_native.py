"""Real seccomp tests require the native-capable disposable verification environment."""
import json
from pathlib import Path
import pytest
from app.security import document_process as dp

def frame(value):
    return json.dumps(value).encode()+b"\0"

@pytest.mark.parametrize('case',[
    'finite-pair','repeat','wrong-root','wrong-executable','wrong-parent','late',
    'different-protocol','different-type','inet','inet6','packet','unix'])
def test_real_seccomp_startup_denial_boundaries(case):
    """Real filtered subprocess/notifications; no native socket can succeed.

    Positive classifier identity is injected for this Python surrogate only;
    digest rejection above and real Chromium document checks cover binding.
    """
    import array,ctypes as C,errno,os,select,signal,socket
    first=(16,3,0)
    probes={'finite-pair':[first,(16,526339,15)],'repeat':[first,first],
        'different-protocol':[(16,3,2)],'different-type':[(16,2,0)],
        'inet':[(2,1,0)],'inet6':[(10,2,0)],'packet':[(17,3,0)],'unix':[(1,1,0)]}.get(case,[first])
    parent,child=socket.socketpair();start_read,start_write=os.pipe()
    pid=os.fork();listener=None;reaped=False
    if pid==0:
        try:
            parent.close();os.close(start_write);os.setpgid(0,0);listener=dp.native_filter()
            child.sendmsg([b'F'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[listener]))])
            child.close();os.close(listener)
            assert os.read(start_read,1)==b'1';os.close(start_read)
            libc=C.CDLL(None,use_errno=True)
            for args in probes:
                result=libc.syscall(41,*args)
                if result!=-1 or C.get_errno()!=errno.EPERM:os._exit(6)
            if case not in ('finite-pair','unix'):signal.pause()
            os._exit(0)
        except BaseException:os._exit(7)
    child.close();os.close(start_read)
    try:
        parent.settimeout(3);data,ancillary,_,_=parent.recvmsg(1,socket.CMSG_SPACE(4));assert data==b'F'
        listener=array.array('i',ancillary[0][2])[0]
        info=dp.proc_info(pid);s=Path(f'/proc/{pid}/exe').stat()
        identity=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        policy=dp.StartupProbes(None if case=='wrong-executable' else identity)
        report=dict(group_host=pid,group_start=info['start'],guardian_host=os.getpid())
        if case=='wrong-root':report['group_host']=os.getpid()
        if case=='wrong-parent':report['guardian_host']=-1
        relay=dp.Relay();relay.accept(0,frame({'id':1,'method':'Browser.getVersion'}))
        if case=='late':relay.accept(1,frame({'id':1,'result':{}}))
        os.write(start_write,b'1')
        libc=C.CDLL(None,use_errno=True);fatal=False
        if case!='unix':
            for index,args in enumerate(probes):
                assert select.select([listener],[],[],3)[0]
                n=dp.Notification();assert libc.ioctl(listener,0xc0502100,C.byref(n))==0
                assert tuple(n.data.args[:3])==args
                event=policy.classify(n,report,relay)
                expected=case=='finite-pair' or (case=='repeat' and index==0)
                assert (event is not None)==expected
                response=dp.Response(n.id,0,-errno.EPERM,0)
                assert libc.ioctl(listener,0xc0182101,C.byref(response))==0
                if not expected:
                    os.kill(pid,signal.SIGKILL);fatal=True;break
        waited,status=os.waitpid(pid,0);reaped=True;assert waited==pid
        if fatal:assert os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL
        else:assert status==0 # Child verified EPERM for every call, including AF_UNIX.
    finally:
        parent.close();os.close(start_write)
        if listener is not None:os.close(listener)
        if not reaped:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(pid,0)
