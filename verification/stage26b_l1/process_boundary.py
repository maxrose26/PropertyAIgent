"""Short-lived, bounded child supervision; never targets the shared web process."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time
import psutil

OUTPUT_LIMIT=65536

class ProcessFailure(RuntimeError): pass

def _stop_owned(child, owned, recorded):
    """Freeze the known child before enumerating descendants; identity-check signals.

    Native Chromium guardians are separately grouped. Killing only the Python
    worker's process group would not prove their release, so verify descendants.
    """
    if child.poll() is None:
        try: os.kill(child.pid,signal.SIGSTOP)
        except ProcessLookupError: pass
    try:
        root=psutil.Process(child.pid)
        if root.create_time()!=owned: raise ProcessFailure('child identity changed')
        descendants=[(p.pid,p.create_time()) for p in root.children(recursive=True)]
    except psutil.NoSuchProcess: descendants=[]
    descendants=list(set(descendants)|set(recorded.items()))
    if child.poll() is None:
        child.kill()
    child.wait(timeout=2)
    # Allow existing parent-loss custodians to perform their own cleanup first.
    until=time.monotonic()+2
    while time.monotonic()<until:
        live=[]
        for pid,created in descendants:
            try:
                p=psutil.Process(pid)
                if p.create_time()==created and p.status()!=psutil.STATUS_ZOMBIE:live.append(p)
            except psutil.NoSuchProcess: pass
        if not live:return
        time.sleep(.02)
    for p in live:
        try:p.kill()
        except psutil.NoSuchProcess:pass
    _,remaining=psutil.wait_procs(live,timeout=2)
    if any(p.is_running() and p.status()!=psutil.STATUS_ZOMBIE for p in remaining):
        raise ProcessFailure('owned descendant remains')

def supervise(command, *, cwd, seconds=165, output_limit=OUTPUT_LIMIT):
    """Bounded stdout/stderr, independent monotonic parent deadline, no secrets.

    Caller supplies a trusted pinned command, not an arbitrary URL/remote shell.
    This is not a perfect OS sandbox for Python; browser containment is separate.
    """
    if not 0<seconds<=165 or not 0<output_limit<=OUTPUT_LIMIT:
        raise ValueError('Process bounds cannot be expanded')
    from app.security.document_process import own_host_pid
    if os.getpid()!=own_host_pid():
        raise ProcessFailure("PROCESS_NAMESPACE_UNVERIFIED")
    started=time.monotonic();child=None;owned=None;selector=selectors.DefaultSelector()
    output={'stdout':bytearray(),'stderr':bytearray()};failure=None;recorded={}
    with tempfile.TemporaryDirectory(prefix='propertyaigent-l1-') as private:
        env={'PATH':'/usr/bin:/bin','HOME':private,'TMPDIR':private,'PYTHONUNBUFFERED':'1'}
        try:
            child=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            try: owned=psutil.Process(child.pid).create_time()
            except psutil.NoSuchProcess:
                if child.poll() is None: raise ProcessFailure("CHILD_IDENTITY_UNVERIFIED")
            for name,stream in (('stdout',child.stdout),('stderr',child.stderr)):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,name)
            while selector.get_map():
                if owned is not None:
                    try:
                        root=psutil.Process(child.pid)
                        if root.create_time()!=owned:raise ProcessFailure("CHILD_IDENTITY_CHANGED")
                        for descendant in root.children(recursive=True):recorded[descendant.pid]=descendant.create_time()
                    except psutil.NoSuchProcess:pass
                remaining=seconds-(time.monotonic()-started)
                if remaining<=0:raise ProcessFailure('TIMEOUT')
                for key,_ in selector.select(min(.05,remaining)):
                    block=os.read(key.fileobj.fileno(),65536)
                    if not block:selector.unregister(key.fileobj);continue
                    output[key.data].extend(block)
                    if sum(map(len,output.values()))>output_limit:raise ProcessFailure('OUTPUT_OVERFLOW')
            if child.wait(timeout=max(.001,seconds-(time.monotonic()-started)))!=0:
                raise ProcessFailure('CHILD_FAILED')
            # A child that exits while retaining descendants/pipes would not reach
            # EOF above, and therefore hits the deadline rather than false success.
            for pid,created in recorded.items():
                try:
                    process=psutil.Process(pid)
                    if process.create_time()==created and process.status()!=psutil.STATUS_ZOMBIE:
                        raise ProcessFailure("DESCENDANT_REMAINS")
                except psutil.NoSuchProcess:pass
            result=json.loads(output['stdout'])
            if not isinstance(result,dict):raise ProcessFailure('MALFORMED_ARTIFACT')
            return result
        except subprocess.TimeoutExpired:
            failure=ProcessFailure('TIMEOUT');raise failure
        except (json.JSONDecodeError,UnicodeDecodeError):
            failure=ProcessFailure('MALFORMED_ARTIFACT');raise failure
        finally:
            if child is not None:
                if owned is not None: _stop_owned(child,owned,recorded)
                else: child.wait(timeout=2)
                for stream in (child.stdout,child.stderr):stream.close()
            selector.close()
