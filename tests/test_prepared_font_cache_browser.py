"""Real-Chromium proof for the default-off prepared fontconfig cache (council-free).

Inline content only, every request aborted, no host name resolvable and no proxy. Skipped where no Playwright browser is installed
(hosted CI). Each render runs in a child with a fresh HOME through the production helpers.
Functional proof only: font selection parity and cache use. Memory effects are not measured here.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

pytest.importorskip('playwright')

SAMPLES = {
    'latin': ('sans-serif', 'The quick brown fox jumps 0123456789'),
    'accents': ('sans-serif', 'Ångström café naïve Łódź Señor'),
    'symbols': ('sans-serif', '£ € © ™ → ≠ ∑ ½'),
    'serif': ('serif', 'Planning application reference 21/01234/FUL'),
    'mono': ('monospace', 'monospace 1lI0O {}[]'),
    'cyrillic': ('sans-serif', 'Привет мир'),
    'greek': ('sans-serif', 'Καλημέρα κόσμε'),
    'cjk': ('sans-serif', '漢字かなカナ'),
    'arabic': ('sans-serif', 'مرحبا بالعالم'),
}

CHILD = r'''
import asyncio, json, os, sys
from pathlib import Path
from playwright.async_api import async_playwright
from verification.direct_reference.instrumented_probe import browser_launch_options
mode, out = sys.argv[1], Path(sys.argv[2])
selection = (sys.argv[3], sys.argv[4]) if mode == 'prepared' else None
samples = json.loads(os.environ.pop('FONT_SAMPLES'))
async def main():
    async with async_playwright() as p:
        options = browser_launch_options(selection)
        if os.environ.get('FONT_TRACE') == '1':
            options = dict(env={**options.get('env', dict(os.environ)), 'FC_DEBUG': '144'})  # cache + scan
        # Test-only isolation (production launch is unchanged): no host name resolves, no proxy.
        browser = await p.chromium.launch(headless=True, args=['--host-resolver-rules=MAP * ~NOTFOUND', '--no-proxy-server'], **options)
        context = await browser.new_context(service_workers='block', accept_downloads=False)
        await context.route('**/*', lambda route: route.abort())
        page = await context.new_page()
        await page.set_content('<!doctype html><meta charset="utf-8">' + ''.join(
            f'<p id="{k}" style="font-family:{f};font-size:16px">{t}</p>' for k, (f, t) in samples.items()))
        cdp = await context.new_cdp_session(page)
        await cdp.send('DOM.enable'); await cdp.send('CSS.enable')
        root = (await cdp.send('DOM.getDocument'))['root']['nodeId']
        result = {}
        for k in samples:
            node = (await cdp.send('DOM.querySelector', {'nodeId': root, 'selector': '#' + k}))['nodeId']
            fonts = (await cdp.send('CSS.getPlatformFontsForNode', {'nodeId': node}))['fonts']
            box = await page.evaluate(f'(() => {{ const r = document.getElementById("{k}").getBoundingClientRect(); return [r.width, r.height]; }})()')
            result[k] = dict(fonts=sorted([f['familyName'], f.get('postScriptName', ''), f['glyphCount'], f['isCustomFont']] for f in fonts), box=box)
        import psutil
        mapped = set()
        for process in psutil.Process().children(recursive=True):  # this child's browser only
            try:
                mapped.update(l.split()[-1] for l in Path(f'/proc/{process.pid}/maps').read_text().splitlines() if '.cache-11' in l)
            except OSError:
                pass
        await browser.close()
    home = Path(os.environ['HOME'])
    out.write_text(json.dumps(dict(samples=result, mapped=sorted(mapped),
        home_fontconfig=sorted(str(x.relative_to(home)) for x in home.rglob('*') if 'fontconfig' in x.parts))))
asyncio.run(main())
'''


def child(tmp_path, name, mode, selection=None, trace=False):
    home = tmp_path / ('home-' + name); home.mkdir()
    out = tmp_path / (name + '.json')
    env = dict(PATH='/usr/bin:/bin', HOME=str(home), TMPDIR=str(home), LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1',
               PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path.home() / '.cache/ms-playwright')),
               FONT_SAMPLES=json.dumps(SAMPLES), **({'FONT_TRACE': '1', 'DEBUG': 'pw:browser'} if trace else {}))
    run = subprocess.run([sys.executable, '-B', '-c', CHILD, mode, str(out), *(selection or ())],
                         env=env, capture_output=True, timeout=120, cwd=Path(__file__).resolve().parents[1])
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(out.read_text()), run.stderr.decode(errors='replace')


@pytest.fixture(scope='module')
def executable():
    from verification.direct_reference import prepared_font_cache as pfc
    try:
        return str(pfc.headless_shell_executable(os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path.home() / '.cache/ms-playwright'))))
    except pfc.PreparedFontCacheError:
        pytest.skip('no installed Playwright headless shell')


def test_prepared_cache_is_used_and_font_selection_is_unchanged(tmp_path, executable):
    from verification.direct_reference import prepared_font_cache as pfc
    cache_dir = tmp_path / 'prepared'
    def render(extra):
        home = tmp_path / 'home-prepare'; home.mkdir()
        env = dict(PATH='/usr/bin:/bin', HOME=str(home), TMPDIR=str(home), LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1',
                   PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path.home() / '.cache/ms-playwright')),
                   FONT_SAMPLES=json.dumps(SAMPLES), PREPARE_FONTCONFIG_FILE=extra['FONTCONFIG_FILE'])
        script = CHILD.replace("options = browser_launch_options(selection)",
                               "options = dict(env={**os.environ, 'FONTCONFIG_FILE': os.environ['PREPARE_FONTCONFIG_FILE']})")
        run = subprocess.run([sys.executable, '-B', '-c', script, 'default', str(tmp_path / 'prepare.json')],
                             env=env, capture_output=True, timeout=120, cwd=Path(__file__).resolve().parents[1])
        assert run.returncode == 0, run.stderr[-2000:]
    digest = pfc.prepare(cache_dir, executable, render)
    selection = (str(cache_dir), digest)

    default, _ = child(tmp_path, 'default', 'default')
    prepared, _ = child(tmp_path, 'prepared', 'prepared', selection)
    traced, trace = child(tmp_path, 'traced', 'prepared', selection, trace=True)
    _, default_trace = child(tmp_path, 'default-traced', 'default', trace=True)

    # Rendering compatibility: identical platform fonts, glyph counts and boxes for every sample.
    assert prepared['samples'] == default['samples'] == traced['samples']
    # Direct cache-use evidence (1): prepared cache files mapped by the browser.
    assert prepared['mapped'] and all(m.startswith(str(cache_dir) + '/') for m in prepared['mapped'])
    # Direct cache-use evidence (2): the trace loads caches and shows no scan or cache write.
    loads = [l for l in trace.splitlines() if ' cache: ' in l and '.cache-11' in l]
    assert loads
    # Positive control: in default mode the same trace shows the rescan writing caches.
    assert 'FcDirCacheWriteDir' in default_trace and 'Created CACHEDIR' in default_trace
    assert 'FcDirCacheWriteDir' not in trace and 'Created CACHEDIR' not in trace
    # Direct cache-use evidence (3): nothing written to the per-run HOME; default mode does rebuild.
    assert prepared['home_fontconfig'] == [] and traced['home_fontconfig'] == []
    assert default['home_fontconfig'] and not default['mapped']
    pfc.verify(cache_dir, digest, executable)  # cache unchanged by use
