"""Linux offline test entrypoint: deny network syscalls before importing tests."""
import ctypes
import errno
import os
import socket
import sys

lib=ctypes.CDLL('libseccomp.so.2')
lib.seccomp_init.argtypes=[ctypes.c_uint32]
lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p]
lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
assert ctx
for name in ('socket','socketpair','connect','sendto','sendmsg','sendmmsg'):
    number=lib.seccomp_syscall_resolve_name(name.encode())
    assert number>=0
    assert lib.seccomp_rule_add(ctx,0x50000|errno.EPERM,number,0)==0
assert lib.seccomp_load(ctx)==0
lib.seccomp_release(ctx)
try:
    socket.socket()
except PermissionError:
    pass
else:
    raise RuntimeError('Offline network guard failed')
assert os.environ['DATABASE_URL']=='sqlite:///:memory:'
sys.path.insert(0,os.getcwd())
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
