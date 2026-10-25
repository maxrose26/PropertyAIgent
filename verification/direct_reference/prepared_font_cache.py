"""Explicit, default-off prepared fontconfig cache for the probe's Chromium only.

Default mode uses nothing here. Prepared mode is selected only by passing both a cache
directory and the SHA256 of its MANIFEST.json. Before the browser is launched (so before any
navigation), the probe worker re-derives the browser identity, font directories, fontconfig
configuration and exact cache contents, and refuses on any difference with a fixed code; there
is no fallback. The browser then receives exactly one extra variable, FONTCONFIG_FILE, naming a
per-run copy of the system fonts.conf whose <cachedir> elements are replaced by the read-only
prepared directory, so effective font rules are unchanged and no cache can be written.

The probe worker runs inside the measured source cgroup, so validation and cache reads are
charged there. Trusted system path ancestors may be root-owned; the controlled cache directory and
its files must be owned by the current user, read-only, regular and never symlinks.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

FORMAT = 'PREPARED_FONT_CACHE_V1'
SYSTEM_CONFIG = Path('/etc/fonts/fonts.conf')
LOCAL_CONFIG = Path('/etc/fonts/local.conf')
CONF_D = Path('/etc/fonts/conf.d')
FONT_DIRS = (Path('/usr/share/fonts'), Path('/usr/local/share/fonts'))
MANIFEST = 'MANIFEST.json'
LIMITS = dict(manifest_bytes=256*1024, config_bytes=1024**2, conf_files=256,
              font_entries=20000, cache_files=512, cache_bytes=64*1024**2)
CODES = ('MISSING', 'MANIFEST_MISMATCH', 'STALE', 'INVALID', 'UNVERIFIED')
CACHE_NAME = re.compile(r'[0-9a-f]{32}-le64\.cache-11|CACHEDIR\.TAG')
SAFE_PATH = re.compile(r'/[A-Za-z0-9_./-]{1,511}')
CACHEDIR = re.compile(r'<cachedir[^>]*>[^<]*</cachedir>')
ABSOLUTE_DIR = re.compile(r'<dir\b[^>]*>\s*(/[^<]*?)\s*</dir>')
RELATIVE_CONF_D = '<include ignore_missing="yes">conf.d</include>'
ABSOLUTE_CONF_D = '<include ignore_missing="yes">/etc/fonts/conf.d</include>'


class PreparedFontCacheError(Exception):
    def __init__(self, code):
        if code not in CODES:
            code = 'UNVERIFIED'
        self.code = 'PREPARED_FONT_CACHE_' + code
        super().__init__(self.code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _read(path, bound, *, follow=True):
    flags = os.O_RDONLY | (0 if follow else os.O_NOFOLLOW)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PreparedFontCacheError('INVALID')
        raw = os.read(fd, bound + 1)
    finally:
        os.close(fd)
    if len(raw) > bound:
        raise PreparedFontCacheError('UNVERIFIED')
    return raw


def trusted_ancestors(path):
    """System ancestors: real directories owned by root or this user; shared ones must be sticky."""
    for parent in reversed(path.parents):
        st = os.lstat(parent)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, os.getuid())
                or (st.st_mode & 0o022 and not st.st_mode & stat.S_ISVTX)):
            raise PreparedFontCacheError('INVALID')


def controlled_cache(cache_dir, *, sealed=True):
    """Exact cache contents: this user's read-only regular files with fontconfig cache names."""
    st = os.lstat(cache_dir)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (sealed and st.st_mode & 0o222):
        raise PreparedFontCacheError('INVALID')
    names = sorted(os.listdir(cache_dir))
    if len(names) > LIMITS['cache_files'] + 1:
        raise PreparedFontCacheError('INVALID')
    files, total = {}, 0
    for name in names:
        path = cache_dir / name
        st = os.lstat(path)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o222
                or st.st_nlink != 1):
            raise PreparedFontCacheError('INVALID')
        if name == MANIFEST:
            continue
        if not CACHE_NAME.fullmatch(name):
            raise PreparedFontCacheError('INVALID')
        total += st.st_size
        if total > LIMITS['cache_bytes']:
            raise PreparedFontCacheError('INVALID')
        files[name] = dict(bytes=st.st_size, sha256=_sha(_read(path, LIMITS['cache_bytes'], follow=False)))
    return files


def headless_shell_executable(browsers_path, registry=None):
    """The executable Playwright runs for headless Chromium (not chromium.executable_path).

    Revision from Playwright's bundled browsers.json, resolved under the allowlisted
    PLAYWRIGHT_BROWSERS_PATH. Linux x64 layout only; anything else is UNVERIFIED.
    """
    try:
        if registry is None:
            import playwright
            registry = Path(playwright.__file__).parent / 'driver/package/browsers.json'
        entries = [b for b in json.loads(_read(registry, LIMITS['manifest_bytes']))['browsers']
                   if b.get('name') == 'chromium-headless-shell']
        if len(entries) != 1 or not re.fullmatch(r'[0-9]{1,8}', str(entries[0].get('revision'))):
            raise PreparedFontCacheError('UNVERIFIED')
        path = Path(browsers_path) / f"chromium_headless_shell-{entries[0]['revision']}/chrome-headless-shell-linux64/chrome-headless-shell"
        if not Path(browsers_path).is_absolute() or not stat.S_ISREG(os.stat(path).st_mode):
            raise PreparedFontCacheError('UNVERIFIED')
        return path
    except PreparedFontCacheError:
        raise
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        raise PreparedFontCacheError('UNVERIFIED') from None


def browser_identity(executable):
    path = Path(executable)
    st = os.stat(path)
    return dict(revision=path.parents[1].name, executable=path.name, bytes=st.st_size, mtime_ns=st.st_mtime_ns)


def font_fingerprint():
    entries = []
    for root in FONT_DIRS:
        if not os.path.lexists(root):
            entries.append([str(root), 'ABSENT'])
            continue
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            entries.append([directory, 'D', os.lstat(directory).st_mtime_ns])
            for name in sorted(filenames):
                st = os.lstat(os.path.join(directory, name))
                entries.append([os.path.join(directory, name), 'F', st.st_size, st.st_mtime_ns])
            if len(entries) > LIMITS['font_entries']:
                raise PreparedFontCacheError('UNVERIFIED')
    return dict(entries=len(entries), sha256=_sha(_canonical(entries)))


def config_fingerprint():
    """Hashes of fonts.conf, local.conf and conf.d. Refuses (INVALID) structures this mode does not
    fingerprint: a conf.d or local.conf cachedir or absolute font dir, or fonts.conf absolute font
    dirs other than FONT_DIRS (a rescan of an unfingerprinted dir would be a silent fallback)."""
    names = sorted(os.listdir(CONF_D))
    if len(names) > LIMITS['conf_files']:
        raise PreparedFontCacheError('UNVERIFIED')
    conf_d = []
    for name in names:
        raw = _read(CONF_D / name, LIMITS['config_bytes'])
        if b'<cachedir' in raw or ABSOLUTE_DIR.search(raw.decode('utf-8', 'replace')):
            raise PreparedFontCacheError('INVALID')
        conf_d.append([name, os.readlink(CONF_D / name) if os.path.islink(CONF_D / name) else None, _sha(raw)])
    system = _read(SYSTEM_CONFIG, LIMITS['config_bytes']).decode('utf-8')
    if set(ABSOLUTE_DIR.findall(system)) != {str(d) for d in FONT_DIRS}:
        raise PreparedFontCacheError('INVALID')
    local_raw = None
    if os.path.lexists(LOCAL_CONFIG):
        local_raw = _read(LOCAL_CONFIG, LIMITS['config_bytes'])
        if b'<cachedir' in local_raw or ABSOLUTE_DIR.search(local_raw.decode('utf-8', 'replace')):
            raise PreparedFontCacheError('INVALID')
    local = _sha(local_raw) if local_raw is not None else None  # one existence decision
    return dict(fonts_conf=_sha(system.encode('utf-8')), local_conf=local,  # hashes of the bytes checked above
                conf_d=_sha(_canonical(conf_d)), conf_d_files=len(conf_d))


def derived_config(cache_dir):
    """System fonts.conf with only <cachedir> elements replaced; conf.d include made absolute."""
    text = _read(SYSTEM_CONFIG, LIMITS['config_bytes']).decode('utf-8')
    if text.count(RELATIVE_CONF_D) != 1 or text.count('</fontconfig>') != 1 or not CACHEDIR.search(text):
        raise PreparedFontCacheError('INVALID')
    text = CACHEDIR.sub('', text).replace(RELATIVE_CONF_D, ABSOLUTE_CONF_D)
    return text.replace('</fontconfig>', f'\t<cachedir>{cache_dir}</cachedir>\n</fontconfig>').encode()


def describe(cache_dir, executable, *, sealed=True):
    return dict(format=FORMAT, cache_dir=str(cache_dir), browser=browser_identity(executable),
                fonts=font_fingerprint(), config=config_fingerprint(),
                derived_config_sha256=_sha(derived_config(cache_dir)),
                cache=controlled_cache(cache_dir, sealed=sealed))


def _location(cache_dir, manifest_sha256):
    if not isinstance(manifest_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', manifest_sha256):
        raise PreparedFontCacheError('INVALID')
    if not isinstance(cache_dir, (str, Path)) or not SAFE_PATH.fullmatch(str(cache_dir)) or '..' in Path(cache_dir).parts:
        raise PreparedFontCacheError('INVALID')
    return Path(cache_dir)


def verify(cache_dir, manifest_sha256, executable):
    """Return the derived config bytes, or refuse with a fixed code. Never falls back."""
    try:
        cache_dir = _location(cache_dir, manifest_sha256)
        if not os.path.lexists(cache_dir) or not os.path.lexists(cache_dir / MANIFEST):
            raise PreparedFontCacheError('MISSING')
        trusted_ancestors(cache_dir)
        raw = _read(cache_dir / MANIFEST, LIMITS['manifest_bytes'], follow=False)
        if _sha(raw) != manifest_sha256:
            raise PreparedFontCacheError('MANIFEST_MISMATCH')
        recorded = json.loads(raw)
        current = describe(cache_dir, executable)
        if recorded.get('format') != FORMAT or recorded.get('cache_dir') != str(cache_dir) or recorded.get('cache') != current['cache']:
            raise PreparedFontCacheError('INVALID')
        if any(recorded.get(key) != current[key] for key in ('browser', 'fonts', 'config', 'derived_config_sha256')):
            raise PreparedFontCacheError('STALE')
        config = derived_config(cache_dir)
        if _sha(config) != recorded['derived_config_sha256']:  # the exact bytes handed to the browser
            raise PreparedFontCacheError('STALE')
        return config
    except PreparedFontCacheError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise PreparedFontCacheError('UNVERIFIED') from None


def launch_env(cache_dir, manifest_sha256, executable, home, environ):
    """Browser-only environment: the caller's environment plus FONTCONFIG_FILE, nothing else."""
    config = verify(cache_dir, manifest_sha256, executable)
    try:
        path = Path(home) / 'prepared-fonts.conf'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        try:
            os.write(fd, config)
        finally:
            os.close(fd)
    except OSError:
        raise PreparedFontCacheError('UNVERIFIED') from None
    return {**environ, 'FONTCONFIG_FILE': str(path)}


def prepare(cache_dir, executable, render):
    """Development/test only: build a cache in a new empty directory, seal it, return the manifest SHA256.

    `render(extra_env)` must launch this browser once with the extra environment and render text.
    Preparation rescans every font, which warms the page cache outside any measured source group;
    later runs must therefore be classified by measured residency, never assumed cold.
    """
    cache_dir = Path(cache_dir)
    _location(cache_dir, '0' * 64)
    trusted_ancestors(cache_dir)
    cache_dir.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='prepared-font-config-') as work:
        config = Path(work) / 'prepare-fonts.conf'
        config.write_bytes(derived_config(cache_dir))
        render({'FONTCONFIG_FILE': str(config)})
    for path in cache_dir.iterdir():
        os.chmod(path, 0o444)
    raw = _canonical(describe(cache_dir, executable, sealed=False))
    manifest = cache_dir / MANIFEST
    manifest.write_bytes(raw)
    os.chmod(manifest, 0o444)
    os.chmod(cache_dir, 0o555)
    digest = _sha(raw)
    verify(cache_dir, digest, executable)
    return digest
