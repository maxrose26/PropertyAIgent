"""Exact native filter x32-denial notification probe; no network dispatched."""
import array,ctypes as C,json,os,select,socket,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.security import document_process as dp
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=True)
parent,child=socket.socketpair();pid=os.fork()
if pid==0:
 try:
  parent.close();listener=dp.native_filter()
  child.sendmsg([b'F'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[listener]))]);child.close();os.close(listener)
  libc=C.CDLL(None,use_errno=True);result=libc.syscall(0x40000029,socket.AF_INET,socket.SOCK_STREAM,0)
  os._exit(0 if result==-1 and C.get_errno()==1 else 3)
 except BaseException:os._exit(4)
child.close();listener=None
try:
 parent.settimeout(3);data,ancillary,_,_=parent.recvmsg(1,socket.CMSG_SPACE(4));assert data==b'F'
 listener=array.array('i',ancillary[0][2])[0]
 ready=select.select([listener],[],[],3)[0]
 assert ready,'Native alternate-ABI denial notification unavailable'
 libc=C.CDLL(None,use_errno=True);notification=dp.Notification()
 assert libc.ioctl(listener,0xc0502100,C.byref(notification))==0
 assert notification.data.nr==0x40000029
 response=dp.Response(notification.id,0,-1,0);assert libc.ioctl(listener,0xc0182101,C.byref(response))==0
 waited,status=os.waitpid(pid,0);assert waited==pid and status==0
 (OUT/'result.json').write_text(json.dumps(dict(syscall=notification.data.nr,arch=notification.data.arch,notification=True,denied=True,child_exit=0)))
 print('DONE exact-filter alternate ABI denial')
finally:
 parent.close()
 if listener is not None:os.close(listener)
 try:os.kill(pid,9);os.waitpid(pid,0)
 except ProcessLookupError:pass
