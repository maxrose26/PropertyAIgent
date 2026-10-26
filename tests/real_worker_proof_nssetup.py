"""Runs inside the proof namespace (user + network + mount) via nsenter: loopback up, then the hosts and CA-bundle overlays.

Bind mounts are visible only inside this namespace; nothing on the host (nor the interpreter's real certifi file) is modified."""
import fcntl
import socket
import struct
import subprocess
import sys

hosts, bundle, certifi_path = sys.argv[1:4]
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    fcntl.ioctl(s, 0x8914, struct.pack('16sH', b'lo', 0x41))        # SIOCSIFFLAGS: IFF_UP | IFF_RUNNING
for source, target in ((hosts, '/etc/hosts'), (bundle, certifi_path)):
    subprocess.run(['mount', '--bind', source, target], check=True)
print('ready', flush=True)
