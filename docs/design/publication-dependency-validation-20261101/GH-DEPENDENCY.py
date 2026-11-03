"""INACTIVE fixed official gh dependency step. No GitHub authentication/API calls.
Only pinned public asset GET; offline checks and runtime receipt guard are local.
"""
import argparse, contextlib, hashlib, json, os, platform, resource, shutil
import signal, ssl, struct, subprocess, sys, tarfile, tempfile, time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler

VERSION='2.103.3'
URL='https://github.com/cli/cli/releases/download/v2.103.3/gh_2.103.3_linux_amd64.tar.gz'
TAR_SHA='4c806978ffce1cec70853302a56d70ac6da4f19bae7adca4e1a8ab00633dd91d'
TAR_SIZE=15031972
MAX_DOWNLOAD=16000000
MAX_BINARY=64*1024**2
MAX_EXPANDED=128*1024**2
MAX_MEMBERS=1024
RECEIPT_MAX=16384
MEMBER='gh_2.103.3_linux_amd64/bin/gh'
HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
class Refusal(Exception):pass

def need(v,code):
    if not v:raise Refusal(code)
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'

@contextlib.contextmanager
def deadline(seconds,code):
    start=time.monotonic();prior=signal.getitimer(signal.ITIMER_REAL);old=signal.getsignal(signal.SIGALRM)
    def expired(*_):raise Refusal(code)
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,min(seconds,prior[0]) if prior[0] else seconds)
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        if prior[0]:signal.setitimer(signal.ITIMER_REAL,max(.001,prior[0]-(time.monotonic()-start)),prior[1])

def admitted_url(value):
    x=urlsplit(value)
    need(x.scheme=='https' and x.hostname in HOSTS and x.port in (None,443) and not x.username and not x.password,'DOWNLOAD_ROUTE')
class Redirects(HTTPRedirectHandler):
    def __init__(self):self.count=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.count+=1;need(self.count<=3,'REDIRECT_LIMIT');admitted_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(path):
    admitted_url(URL)
    opener=build_opener(ProxyHandler({}),Redirects(),HTTPSHandler(context=ssl.create_default_context()))
    received=0
    try:
        with deadline(40,'DOWNLOAD_TIMEOUT'),opener.open(Request(URL,headers={'User-Agent':'PropertyAIgent-fixed-public-dependency'}),timeout=5) as response,Path(path).open('xb') as out:
            declared=response.headers.get('Content-Length')
            need(declared is None or int(declared)==TAR_SIZE,'DOWNLOAD_DECLARED_SIZE')
            while True:
                chunk=response.read(min(65536,TAR_SIZE+1-received))
                if not chunk:break
                received+=len(chunk);need(received<=TAR_SIZE and received<=MAX_DOWNLOAD,'DOWNLOAD_SIZE_LIMIT');out.write(chunk)
            out.flush();os.fsync(out.fileno())
    except Refusal:raise
    except BaseException:raise Refusal('DOWNLOAD_FAILED') from None
    need(received==TAR_SIZE,'DOWNLOAD_TRUNCATED')

def checked_binary(archive):
    f=Path(archive)
    need(f.is_file() and not f.is_symlink() and f.stat().st_size==TAR_SIZE and f.stat().st_size<=MAX_DOWNLOAD,'ARCHIVE_SIZE_OR_PATH')
    need(digest(f)==TAR_SHA,'ARCHIVE_SHA256')
    selected=None;count=0;expanded=0
    with tarfile.open(f,'r:gz') as tar:
        for entry in tar:
            count+=1;expanded+=entry.size
            path=PurePosixPath(entry.name)
            need(count<=MAX_MEMBERS and expanded<=MAX_EXPANDED and entry.offset_data+entry.size<=MAX_EXPANDED,'ARCHIVE_EXPANSION_LIMIT')
            need(not path.is_absolute() and '..' not in path.parts and '\\' not in entry.name and (entry.isfile() or entry.isdir()),'ARCHIVE_UNSAFE_MEMBER')
            if entry.name==MEMBER:
                need(selected is None and entry.isfile() and 0<entry.size<=MAX_BINARY,'BINARY_MEMBER')
                selected=entry
        need(selected is not None,'BINARY_MISSING')
        stream=tar.extractfile(selected);raw=stream.read(MAX_BINARY+1)
        need(len(raw)==selected.size and len(raw)<=MAX_BINARY,'BINARY_TRUNCATED')
    elf_check(raw)
    return raw

def elf_check(raw):
    need(len(raw)>=64 and raw[:7]==b'\x7fELF\x02\x01\x01','ELF_LINUX_AMD64')
    e_type,machine=struct.unpack_from('<HH',raw,16)
    offset=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54)
    need(e_type==2 and machine==62 and size==56 and 0<count<=32 and offset+size*count<=len(raw),'ELF_LINUX_AMD64')
    for i in range(count):
        kind=struct.unpack_from('<I',raw,offset+i*size)[0]
        need(kind not in (2,3),'ELF_DYNAMIC_LIBRARY_REFUSED')
    return dict(class_bits=64,cpu='x86_64',byte_order='little',pt_interp=False,pt_dynamic=False,external_libraries='NONE_BY_ELF_CHECK')

def version_check(exe):
    with tempfile.TemporaryDirectory(prefix='gh-version-private-') as home,tempfile.TemporaryFile() as output:
        def bound():resource.setrlimit(resource.RLIMIT_FSIZE,(4096,4096))
        try:
            r=subprocess.run([str(exe),'--version'],stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,timeout=5,preexec_fn=bound,env={'HOME':home,'GH_CONFIG_DIR':home,'PATH':str(Path(exe).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','GH_PROMPT_DISABLED':'1','GH_NO_UPDATE_NOTIFIER':'1'})
            output.seek(0);data=output.read(4097)
        except BaseException:raise Refusal('VERSION_CHECK_FAILED') from None
    need(r.returncode==0 and 0<len(data)<=4096,'VERSION_CHECK_FAILED')
    line=data.decode('ascii').splitlines()[0]
    import re
    need(re.fullmatch(r'gh version 2\.103\.3(?: \([0-9]{4}-[0-9]{2}-[0-9]{2}\))?',line) is not None,'VERSION_MISMATCH')
    return line

def install(archive,target_bin):
    target=Path(target_bin);need(target.is_dir() and not target.is_symlink(),'TARGET_BIN')
    exe=target/'gh';receipt=target/'gh-build-receipt.json';stage=target/'.gh-2.103.3-new'
    need(not any(x.exists() or x.is_symlink() for x in (exe,receipt,stage)),'TARGET_ALREADY_EXISTS')
    raw=checked_binary(archive)
    fd=os.open(stage,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(stage,0o755);line=version_check(stage)
        value=dict(kind='OFFICIAL_GH_BUILD_RECEIPT_V1',version=VERSION,archive_url=URL,archive_sha256=TAR_SHA,archive_bytes=TAR_SIZE,executable=str(exe.resolve()),executable_sha256=hashlib.sha256(raw).hexdigest(),mode='0755',receipt_mode='0644',elf=elf_check(raw),version_line=line)
        os.link(stage,exe,follow_symlinks=False);stage.unlink()
        fd=os.open(receipt,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
        os.chmod(receipt,0o644) # Nonsecret build metadata, readable across artifact users.
        fd=os.open(target,os.O_DIRECTORY|os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return value
    finally:
        if stage.exists():stage.unlink()

def target_bin():
    p=Path(sys.prefix).resolve()
    need(sys.prefix!=sys.base_prefix and p.name=='.venv' and (p/'bin').is_dir(),'RENDER_VENV_LAYOUT')
    return p/'bin'

def verify_runtime(target,expected_receipt_sha):
    import re
    need(re.fullmatch('[a-f0-9]{64}',expected_receipt_sha or '') is not None,'RECEIPT_BINDING')
    target=Path(target);receipt=target/'gh-build-receipt.json';exe=target/'gh'
    need(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size<=RECEIPT_MAX and (receipt.stat().st_mode&0o777)==0o644 and digest(receipt)==expected_receipt_sha,'RECEIPT_BINDING')
    v=json.loads(receipt.read_bytes())
    need(v['version']==VERSION and v['archive_sha256']==TAR_SHA and v['archive_bytes']==TAR_SIZE and v['executable']==str(exe.resolve()),'RECEIPT_CONTENT')
    need(exe.is_file() and not exe.is_symlink() and (exe.stat().st_mode&0o777)==0o755 and exe.stat().st_size<=MAX_BINARY and digest(exe)==v['executable_sha256'],'EXECUTABLE_BINDING')
    need(shutil.which('gh') is not None and Path(shutil.which('gh')).resolve()==exe.resolve(),'RUNTIME_PATH')
    elf_check(exe.read_bytes())
    return dict(status='PINNED_GH_RUNTIME_FILES_VERIFIED',version=VERSION,receipt_sha256=expected_receipt_sha,executable_sha256=v['executable_sha256'],network_requests=0)

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--archive');p.add_argument('--offline-check',action='store_true');p.add_argument('--verify-runtime',action='store_true');p.add_argument('--receipt-sha')
    def arguments_error(_):raise Refusal('ARGUMENTS')
    p.error=arguments_error
    a=p.parse_args();need(platform.system()=='Linux' and platform.machine()=='x86_64','LINUX_AMD64_REQUIRED')
    with deadline(60,'TOTAL_TIMEOUT'):
        if a.verify_runtime:
            need(not a.archive and not a.offline_check,'ARGUMENTS');v=verify_runtime(target_bin(),a.receipt_sha)
        elif a.offline_check:
            need(a.archive is not None,'ARGUMENTS')
            with deadline(15,'EXTRACTION_TIMEOUT'):raw=checked_binary(a.archive)
            v=dict(status='PINNED_ARCHIVE_ELF_VERIFIED_NO_INSTALL',executable_sha256=hashlib.sha256(raw).hexdigest())
        else:
            target=target_bin()
            with tempfile.TemporaryDirectory(prefix='gh-fixed-public-') as temporary:
                archive=Path(a.archive) if a.archive else Path(temporary)/'gh.tar.gz'
                if not a.archive:download(archive)
                with deadline(15,'INSTALL_TIMEOUT'):v=install(archive,target)
    raw=canonical(v);need(len(raw)<=RECEIPT_MAX,'RECEIPT_OUTPUT_LIMIT');print(raw.decode().strip())
if __name__=='__main__':
    try:main()
    except SystemExit as e:
        if e.code==0:raise
        print(json.dumps(dict(status='GH_DEPENDENCY_REFUSED',reason='ARGUMENTS',retry=False)));raise SystemExit(2)
    except BaseException as e:
        known=type(e) is Refusal
        print(json.dumps(dict(status='GH_DEPENDENCY_REFUSED',reason=e.args[0] if known else 'UNKNOWN',retry=False)))
        raise SystemExit(2)
