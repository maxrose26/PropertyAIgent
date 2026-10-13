"""Build a reviewed inline one-off command; never calls Render or installs packages."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import zlib

SERVICE = 'crn-d9sv93vavr4c73f98rb0'
FILES = ('verification/direct_reference/instrumented_probe.py',
         'verification/direct_reference/arcus_http_probe.py')
MAX_PAYLOAD = 128 * 1024


def pack(root):
    files = {name: (root / name).read_text() for name in FILES}
    raw = json.dumps(files, sort_keys=True).encode()
    if len(raw) > MAX_PAYLOAD:
        raise ValueError('PAYLOAD_TOO_LARGE')
    return base64.b64encode(zlib.compress(raw)).decode(), hashlib.sha256(raw).hexdigest()


def unpack(encoded, expected):
    decoder = zlib.decompressobj()
    raw = decoder.decompress(base64.b64decode(encoded, validate=True), MAX_PAYLOAD + 1)
    if len(raw) > MAX_PAYLOAD or not decoder.eof or decoder.unused_data:
        raise ValueError('PAYLOAD_BOUND')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('PAYLOAD_HASH')
    files = json.loads(raw)
    if set(files) != set(FILES) or not all(isinstance(v, str) for v in files.values()):
        raise ValueError('PAYLOAD_FILES')
    return files


def build_command(root):
    encoded, digest = pack(root)
    # This bootstrap runs only after env -i. No repository imports from the old artifact.
    bootstrap = '''import base64,hashlib,json,os,pathlib,sys,tempfile,zlib
if sys.version_info < (3,10): raise SystemExit('PYTHON_CAPABILITY_MISSING')
import psutil
from playwright.sync_api import sync_playwright
cache_setting=os.environ['PLAYWRIGHT_BROWSERS_PATH']
# Playwright's existing Render configuration uses 0 for package-local browsers.
if cache_setting != '0' and not pathlib.Path(cache_setting).is_dir():
    raise SystemExit('CHROMIUM_CACHE_MISSING')
# Version-compatible executable launch is checked inside the owned supervisor.
blob=base64.b64decode(__ENCODED__,validate=True)
dec=zlib.decompressobj()
raw=dec.decompress(blob,131073)
if len(raw)>131072 or not dec.eof or dec.unused_data: raise SystemExit('PAYLOAD_BOUND')
if hashlib.sha256(raw).hexdigest()!=__DIGEST__: raise SystemExit('PAYLOAD_HASH')
files=json.loads(raw)
if set(files)!=set(__FILES__) or not all(isinstance(v,str) for v in files.values()): raise SystemExit('PAYLOAD_FILES')
with tempfile.TemporaryDirectory(prefix='stage4-render-') as directory:
    root=pathlib.Path(directory)
    for name,content in files.items():
        target=root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content)
    os.chdir(root)
    sys.path.insert(0,str(root))
    from verification.direct_reference.instrumented_probe import supervised
    result=supervised('trafford',root/'audit.json','render-disposable')
raise SystemExit(result)
'''.replace('__ENCODED__', repr(encoded)).replace('__DIGEST__', repr(digest)).replace('__FILES__', repr(FILES))
    # Shell checks the existing service before replacing itself; only cache location and
    # executable search path survive. No database/model/Render credentials reach Python.
    command = ('test "$RENDER_SERVICE_ID" = ' + shlex.quote(SERVICE) + ' && exec /usr/bin/env -i '
               'PATH="$PATH" HOME=/tmp TMPDIR=/tmp LANG=C.UTF-8 PYTHONNOUSERSITE=1 '
               'PYTHONDONTWRITEBYTECODE=1 RENDER_SERVICE_ID=' + shlex.quote(SERVICE) + ' '
               'PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}" '
               'python3 -I -c ' + shlex.quote(bootstrap))
    return {'service_id': SERVICE, 'startCommand': command, 'payload_sha256': digest,
            'case': 'trafford', 'production_eligible': False}


if __name__ == '__main__':
    print(json.dumps(build_command(Path(__file__).resolve().parents[2]), indent=2))
