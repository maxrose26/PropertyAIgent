"""Default-off prepared fontconfig cache: validation, refusal codes and probe wiring.

File-backed fakes of the system font configuration, font directories and browser executable;
no browser is started. Real-browser compatibility is covered by
tests/test_prepared_font_cache_browser.py (skipped where no browser is installed).
"""
import asyncio
import json
import os
from pathlib import Path
import pytest
from verification.direct_reference import prepared_font_cache as pfc
from verification.direct_reference import instrumented_probe as probe_module

FONTS_CONF = '''<?xml version="1.0"?>
<fontconfig>
	<dir>/usr/share/fonts</dir>
	<dir prefix="xdg">fonts</dir>
	<match target="pattern"><test qual="any" name="family"><string>mono</string></test>
		<edit name="family" mode="assign" binding="same"><string>monospace</string></edit></match>
	<include ignore_missing="yes">conf.d</include>
	<cachedir>/var/cache/fontconfig</cachedir>
	<cachedir prefix="xdg">fontconfig</cachedir>
	<!-- the following element will be removed in the future -->
	<cachedir>~/.fontconfig</cachedir>
	<config><rescan><int>30</int></rescan></config>
</fontconfig>
'''
CACHE_FILES = ('0bd3dc0958fa2205aaaa8ebb13e2872b-le64.cache-11', '3830d5c3ddfd5cd38a049b759396e72e-le64.cache-11', 'CACHEDIR.TAG')


@pytest.fixture
def system(tmp_path, monkeypatch):
    etc = tmp_path / 'etc/fonts'; (etc / 'conf.d').mkdir(parents=True)
    avail = tmp_path / 'conf.avail'; avail.mkdir()
    (etc / 'fonts.conf').write_text(FONTS_CONF)
    (avail / '10-hinting.conf').write_text('<fontconfig/>')
    (etc / 'conf.d/10-hinting.conf').symlink_to(avail / '10-hinting.conf')
    fonts = tmp_path / 'fonts'; (fonts / 'truetype').mkdir(parents=True)
    (fonts / 'truetype/a.ttf').write_bytes(b'font-a')
    exe = tmp_path / 'browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell'
    exe.parent.mkdir(parents=True); exe.write_bytes(b'browser')
    monkeypatch.setattr(pfc, 'SYSTEM_CONFIG', etc / 'fonts.conf')
    monkeypatch.setattr(pfc, 'LOCAL_CONFIG', etc / 'local.conf')
    monkeypatch.setattr(pfc, 'CONF_D', etc / 'conf.d')
    monkeypatch.setattr(pfc, 'FONT_DIRS', (fonts, tmp_path / 'absent-fonts'))
    return dict(tmp=tmp_path, etc=etc, fonts=fonts, exe=exe, avail=avail)


def sealed(system, name='prepared'):
    cache_dir = system['tmp'] / name
    seen = {}
    def render(extra):
        seen.update(extra)
        for f in CACHE_FILES:(cache_dir / f).write_bytes(f.encode())
    digest = pfc.prepare(cache_dir, system['exe'], render)
    return cache_dir, digest, seen


def refuses(code, cache_dir, digest, exe):
    with pytest.raises(pfc.PreparedFontCacheError) as caught:
        pfc.verify(cache_dir, digest, exe)
    assert caught.value.code == 'PREPARED_FONT_CACHE_' + code


def unseal(path):
    os.chmod(path, 0o755 if path.is_dir() else 0o644)


# --- derived configuration ----------------------------------------------------

def test_derived_config_replaces_only_cachedirs_and_keeps_rules(system):
    cache_dir, digest, seen = sealed(system)
    config = pfc.verify(cache_dir, digest, system['exe']).decode()
    assert config.count('<cachedir') == 1 and f'<cachedir>{cache_dir}</cachedir>' in config
    assert '<include ignore_missing="yes">/etc/fonts/conf.d</include>' in config and '>conf.d<' not in config
    kept = [l for l in FONTS_CONF.splitlines() if '<cachedir' not in l and '>conf.d<' not in l]
    assert all(l in config.splitlines() for l in kept)  # every other line, incl. rules, verbatim
    assert Path(seen['FONTCONFIG_FILE']).name == 'prepare-fonts.conf' and set(seen) == {'FONTCONFIG_FILE'}


@pytest.mark.parametrize('change', ['no_conf_d', 'two_conf_d', 'no_cachedir'])
def test_unexpected_system_config_structure_is_invalid(system, change):
    text = {'no_conf_d': FONTS_CONF.replace('<include ignore_missing="yes">conf.d</include>', ''),
            'two_conf_d': FONTS_CONF.replace('</fontconfig>', '<include ignore_missing="yes">conf.d</include></fontconfig>'),
            'no_cachedir': '\n'.join(l for l in FONTS_CONF.splitlines() if '<cachedir' not in l)}[change]
    (system['etc'] / 'fonts.conf').write_text(text)
    with pytest.raises(pfc.PreparedFontCacheError, match='PREPARED_FONT_CACHE_INVALID'):
        pfc.derived_config(system['tmp'] / 'x')


# --- refusal codes --------------------------------------------------------------

def test_valid_cache_and_browser_only_env(system):
    cache_dir, digest, _ = sealed(system)
    home = system['tmp'] / 'home'; home.mkdir()
    env = pfc.launch_env(cache_dir, digest, system['exe'], home, {'PATH': '/usr/bin:/bin', 'HOME': str(home)})
    assert set(env) == {'PATH', 'HOME', 'FONTCONFIG_FILE'} and env['FONTCONFIG_FILE'] == str(home / 'prepared-fonts.conf')
    assert (home / 'prepared-fonts.conf').stat().st_mode & 0o777 == 0o400
    assert (home / 'prepared-fonts.conf').read_bytes() == pfc.derived_config(cache_dir)


def test_missing_directory_or_manifest(system):
    cache_dir, digest, _ = sealed(system)
    refuses('MISSING', system['tmp'] / 'absent', digest, system['exe'])
    unseal(cache_dir); os.chmod(cache_dir / pfc.MANIFEST, 0o644); (cache_dir / pfc.MANIFEST).unlink()
    refuses('MISSING', cache_dir, digest, system['exe'])


def test_manifest_hash_mismatch(system):
    cache_dir, digest, _ = sealed(system)
    refuses('MANIFEST_MISMATCH', cache_dir, ('0' if digest[0] != '0' else '1') + digest[1:], system['exe'])


@pytest.mark.parametrize('change', ['font_added', 'font_touched', 'fonts_conf', 'conf_d_added', 'local_conf', 'browser_replaced'])
def test_changed_fonts_configuration_or_browser_is_stale(system, change):
    cache_dir, digest, _ = sealed(system)
    if change == 'font_added':(system['fonts'] / 'truetype/b.ttf').write_bytes(b'font-b')
    elif change == 'font_touched':os.utime(system['fonts'] / 'truetype/a.ttf', ns=(1, 1))
    elif change == 'fonts_conf':(system['etc'] / 'fonts.conf').write_text(FONTS_CONF.replace('<int>30</int>', '<int>31</int>'))
    elif change == 'conf_d_added':(system['etc'] / 'conf.d/99-extra.conf').write_text('<fontconfig/>')
    elif change == 'local_conf':(system['etc'] / 'local.conf').write_text('<fontconfig/>')
    else:system['exe'].write_bytes(b'browser-v2')
    refuses('STALE', cache_dir, digest, system['exe'])


@pytest.mark.parametrize('change', ['extra_file', 'content_changed', 'symlink_file', 'writable_file', 'writable_dir', 'bad_name', 'hardlink'])
def test_cache_contents_must_match_exactly(system, change):
    cache_dir, digest, _ = sealed(system)
    unseal(cache_dir)
    first = cache_dir / CACHE_FILES[0]
    if change == 'extra_file':(cache_dir / 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-le64.cache-11').write_bytes(b'x');os.chmod(cache_dir / 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-le64.cache-11', 0o444)
    elif change == 'content_changed':unseal(first);first.write_bytes(b'changed');os.chmod(first, 0o444)
    elif change == 'symlink_file':unseal(first);first.unlink();first.symlink_to(system['fonts'] / 'truetype/a.ttf')
    elif change == 'writable_file':unseal(first)
    elif change == 'bad_name':(cache_dir / 'notes.txt').write_bytes(b'x');os.chmod(cache_dir / 'notes.txt', 0o444)
    elif change == 'hardlink':os.link(first, system['tmp'] / 'outside-link')
    if change != 'writable_dir':os.chmod(cache_dir, 0o555)
    refuses('INVALID', cache_dir, digest, system['exe'])


def test_untrusted_ancestor_is_invalid(system, tmp_path):
    parent = tmp_path / 'parent'; parent.mkdir()
    cache_dir, digest, _ = sealed(dict(system, tmp=parent))
    link = tmp_path / 'link'; link.symlink_to(parent)
    refuses('INVALID', link / 'prepared', digest, system['exe'])  # symlinked ancestor
    os.chmod(parent, 0o777)  # group/world-writable ancestor without the sticky bit
    refuses('INVALID', cache_dir, digest, system['exe'])
    shared = tmp_path / 'shared'; shared.mkdir(); os.chmod(shared, 0o777)
    with pytest.raises(pfc.PreparedFontCacheError, match='PREPARED_FONT_CACHE_INVALID'):
        sealed(dict(system, tmp=shared))  # preparation refuses an untrusted location too


@pytest.mark.parametrize('cache_dir,digest', [('relative/dir', '0' * 64), ('/tmp/a b', '0' * 64), ('/tmp/<x>', '0' * 64),
                                              ('/tmp/../etc', '0' * 64), ('/tmp/x', 'ABC'), ('/tmp/x', None)])
def test_unsafe_selection_is_invalid(system, cache_dir, digest):
    refuses('INVALID', cache_dir, digest, system['exe'])


@pytest.mark.parametrize('change', ['manifest_not_json', 'manifest_oversize', 'unreadable_cache', 'font_entry_bound'])
def test_unverifiable_data_refuses(system, monkeypatch, change):
    cache_dir, digest, _ = sealed(system)
    if change in ('manifest_not_json', 'manifest_oversize'):
        unseal(cache_dir); m = cache_dir / pfc.MANIFEST; unseal(m)
        raw = b'{' if change == 'manifest_not_json' else b' ' * (pfc.LIMITS['manifest_bytes'] + 1)
        m.write_bytes(raw); os.chmod(m, 0o444); os.chmod(cache_dir, 0o555)
        digest = __import__('hashlib').sha256(raw).hexdigest()
    elif change == 'unreadable_cache':os.chmod(cache_dir / CACHE_FILES[0], 0o000)
    else:monkeypatch.setitem(pfc.LIMITS, 'font_entries', 1)
    refuses('UNVERIFIED', cache_dir, digest, system['exe'])


# --- probe wiring: default unchanged, refusal before launch ----------------------

class FakeChromium:
    def __init__(self, executable):self.executable_path = str(executable);self.calls = []
    async def launch(self, **kwargs):
        self.calls.append(kwargs);raise RuntimeError('stop before any page')


def run_probe(monkeypatch, executable, **kwargs):
    chromium = FakeChromium(executable)
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(Path(executable).parents[2]))
    monkeypatch.setattr(probe_module, 'prepared_font_executable', lambda browsers: Path(executable))
    class Playwright:
        async def __aenter__(self):return type('P', (), {'chromium': chromium})()
        async def __aexit__(self, *_):return False
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: Playwright())
    audit = asyncio.run(probe_module.probe('trafford', **kwargs))
    return audit, chromium.calls


def test_default_launch_is_unchanged(monkeypatch, system):
    audit, calls = run_probe(monkeypatch, system['exe'])
    assert calls == [{'headless': True}] and audit['failure'] == 'BROWSER_RuntimeError'
    assert probe_module.browser_launch_options(None) == {}


def test_prepared_mode_passes_only_fontconfig_file(monkeypatch, system):
    cache_dir, digest, _ = sealed(system)
    home = system['tmp'] / 'probe-home'; home.mkdir(); monkeypatch.setenv('HOME', str(home))
    audit, calls = run_probe(monkeypatch, system['exe'], prepared_font_cache=(str(cache_dir), digest))
    assert len(calls) == 1 and set(calls[0]) == {'headless', 'env'}
    assert calls[0]['env'] == {**os.environ, 'FONTCONFIG_FILE': str(home / 'prepared-fonts.conf')}


@pytest.mark.parametrize('code', ['MISSING', 'MANIFEST_MISMATCH', 'STALE'])
def test_refusal_happens_before_browser_launch(monkeypatch, system, code):
    cache_dir, digest, _ = sealed(system)
    home = system['tmp'] / 'probe-home'; home.mkdir(); monkeypatch.setenv('HOME', str(home))
    if code == 'MISSING':cache_dir = system['tmp'] / 'absent'
    elif code == 'MANIFEST_MISMATCH':digest = ('0' if digest[0] != '0' else '1') + digest[1:]
    else:system['exe'].write_bytes(b'browser-v2')
    audit, calls = run_probe(monkeypatch, system['exe'], prepared_font_cache=(str(cache_dir), digest))
    assert calls == [] and audit['failure'] == 'PREPARED_FONT_CACHE_' + code
    assert audit['navigations'] == 0 and audit['requests'] == 0 and audit['cleanup'] == 'NOT_STARTED'


def test_headless_shell_executable_is_resolved_from_the_registry(tmp_path):
    browsers = tmp_path / 'browsers'
    exe = browsers / 'chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell'
    exe.parent.mkdir(parents=True); exe.write_bytes(b'x')
    registry = tmp_path / 'browsers.json'
    def write(entries):registry.write_text(json.dumps({'browsers': entries}))
    write([{'name': 'chromium', 'revision': '1243'}, {'name': 'chromium-headless-shell', 'revision': '1243'}])
    assert pfc.headless_shell_executable(browsers, registry) == exe
    for entries in ([{'name': 'chromium-headless-shell', 'revision': '1244'}],  # not installed
                    [{'name': 'chromium', 'revision': '1243'}],  # no headless shell entry
                    [{'name': 'chromium-headless-shell', 'revision': '12/43'}],
                    [{'name': 'chromium-headless-shell', 'revision': '1243'}] * 2):
        write(entries)
        with pytest.raises(pfc.PreparedFontCacheError, match='PREPARED_FONT_CACHE_UNVERIFIED'):
            pfc.headless_shell_executable(browsers, registry)
    write([{'name': 'chromium-headless-shell', 'revision': '1243'}])
    with pytest.raises(pfc.PreparedFontCacheError, match='PREPARED_FONT_CACHE_UNVERIFIED'):
        pfc.headless_shell_executable('relative/browsers', registry)


def test_prepared_mode_without_browser_path_is_unverified(monkeypatch, system):
    monkeypatch.delenv('PLAYWRIGHT_BROWSERS_PATH', raising=False)
    with pytest.raises(pfc.PreparedFontCacheError, match='PREPARED_FONT_CACHE_UNVERIFIED'):
        probe_module.browser_launch_options(('/tmp/x', '0' * 64))


def test_supervised_selection_and_command(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='PREPARED_FONT_CACHE_SELECTION'):
        probe_module.supervised('trafford', tmp_path / 'o.json', prepared_font_cache=['/x', '0' * 64])
    monkeypatch.setattr(probe_module, 'execution_environment_allowed', lambda *a: True)
    seen = []
    def popen(command, **kwargs):
        seen.append((command, kwargs['env']));raise RuntimeError('stop')
    monkeypatch.setattr(probe_module.subprocess, 'Popen', popen)
    for selection in (None, ('/tmp/cache', 'a' * 64)):
        with pytest.raises(RuntimeError):
            probe_module.supervised('trafford', tmp_path / 'o.json', **({'prepared_font_cache': selection} if selection else {}))
    (default, env1), (prepared, env2) = seen
    out = default.index('--output') + 1
    assert prepared[out] != default[out]  # fresh per-run output path
    prepared = prepared[:out] + [default[out]] + prepared[out + 1:]
    fresh = ('HOME', 'TMPDIR')  # per-run temporary directory, different on every call
    assert '--prepared-font-cache' not in default and set(env1) == set(env2)
    assert {k: v for k, v in env1.items() if k not in fresh} == {k: v for k, v in env2.items() if k not in fresh}
    assert prepared == default + ['--prepared-font-cache', '/tmp/cache', '--prepared-font-cache-sha256', 'a' * 64]
