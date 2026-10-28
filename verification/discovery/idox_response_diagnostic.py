"""Oldham single-page response diagnostic: at most TWO requests, the raw responses kept private, nothing published.

Purpose: the Oldham RECEIVED 15-21 October observation returned five records with no `p.pager` count or terminal marker. The retained projections cannot show whether a count or
navigation signal existed elsewhere in the HTML. This module captures exactly the search-form response and the date-search response once, stores them privately, and offers a pure
offline inspector for them. It is NOT a collection observation, never admits a record, never changes completeness and has no publication path.

Reuse: the existing `WindowBoundary` (origin/route allow-list, no redirect following, zero retries, status/media checks, request/byte accounting), the council's own form payload and the
existing 3 s connect / 8 s read dispatch. Only the budget differs: requests=2 (per-response and time ceilings are the existing reader's own).
Authority: see `render`/`validate`. A registration is inactive until the owner approves its exact hash in the conversation; it is local, database-free and does not synchronise with
database stops. No source request is made by import, `render`, `validate` or the inspector.
"""
import hashlib
import json
import os
import re
import signal
import stat
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from app.scrapers.discovery_idox import ListingError, parse_page
from verification.bolton_recon.recon import Failure
from verification.stage26b_l1.request_boundary import BoundaryFailure, Budget
from .idox_window import WindowBoundary, WindowConfig

KIND = 'OLDHAM_RESPONSE_DIAGNOSTIC_V1'
SCOPE = dict(council='oldham', semantics='RECEIVED', start='2026-10-15', end='2026-10-21')
# The existing reader's own ceilings (idox_window.WindowBoundary: response 500,000 bytes, 45 s). The combined byte bound is the per-response ceiling times the two requests, not a figure
# derived from any earlier response.
LIMITS = dict(requests=2, response_bytes=500_000, total_bytes=1_000_000, reader_seconds=45, connect_seconds=3, read_seconds=8, supervisor_seconds=50, max_registration_hours=2)
PERMIT = 'OWNER_APPROVED_DATABASE_FREE_SOURCE_ONLY_DIAGNOSTIC'
SCOPE_UNIT = 'propertyaigent-diagnostic.scope'      # the dedicated transient user scope the run must already be inside
MEMORY_BYTES = 1024 ** 3
MAX_INSPECT_BYTES = 500_000      # the per-response ceiling: a larger file was not produced by this capture
MAX_TAGS = 20_000
PRESERVED = ['CONSUMED_SALFORD_GLOBAL_STOP:38884069913', 'STORAGE_TEST_STOP']
IDENTITY = re.compile(r'oldham-search-response-diagnostic-[0-9]{8}-[a-z0-9]{1,16}')
FORBIDDEN_ENV = ('DATABASE', 'SUPABASE', 'OPENAI', 'ANTHROPIC')
STATE_ROOT = Path.home() / '.local/state/propertyaigent-diagnostics'
MAX_ITEMS = 25
TEXT = 120


def config():
    return WindowConfig(SCOPE['council'], SCOPE['semantics'], date.fromisoformat(SCOPE['start']), date.fromisoformat(SCOPE['end']), 0)


class DiagnosticBoundary(WindowBoundary):
    """The window boundary with a two-request budget. Every other rule (routes, methods, redirects, status and media checks, zero retries) is the existing one."""

    def __init__(self, dispatch, cfg):
        super().__init__(dispatch, cfg)
        self.budget = Budget(requests=LIMITS['requests'], per_reference=LIMITS['requests'], total_bytes=LIMITS['total_bytes'], response_bytes=LIMITS['response_bytes'], seconds=LIMITS['reader_seconds'])


def _write_private(directory, name, raw):
    fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)


def capture(dispatch, cfg, directory):
    """Request 1: the search form. Request 2: the exact date search, once. Then stop. Raw bodies go to `directory` (mode 0700) as 0600 files; the return value holds only hashes, sizes,
    statuses and accounting."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ValueError('PRIVATE_DIRECTORY')
    b = DiagnosticBoundary(dispatch, cfg)
    out = dict(kind=KIND, council=cfg.council, requested_interval=[cfg.start.isoformat(), cfg.end.isoformat()], date_semantics=cfg.semantics, collection_observation=False, persistence=False,
               raw_html_published=False, responses=[], failure=None, cleanup='UNKNOWN')
    stage = 'FORM_REQUEST'

    def keep(phase, raw):
        _write_private(directory, phase.lower() + '.html', raw)
        shape = b.last_response or {}
        out['responses'].append(dict(ordinal=len(out['responses']) + 1, phase=phase, http_status=shape.get('http_status'), media_type=shape.get('media_type'), redirect=shape.get('redirect'),
                                     bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), private_file=phase.lower() + '.html'))
    try:
        form = b.retrieve('GET', cfg.form_url)
        keep('FORM', form)
        stage = 'FORM_PARSE'
        target, payload = cfg.payload(form)
        b.admitted_post = target
        b.admitted_body = urlencode(payload).encode()
        b.phase = 'SEARCH'
        payload.clear()
        stage = 'SEARCH_REQUEST'
        html = b.retrieve('POST', target, b.admitted_body)
        b.admitted_body = None
        keep('SEARCH', html)
    except (ListingError, BoundaryFailure, Failure) as exc:
        from .source_diagnostics import transport_facts
        out['failure'] = dict(stage=stage, error=type(exc).__name__, transport=transport_facts(b.last_response, exc))
    except Exception:
        out['failure'] = dict(stage=stage, error='UNCLASSIFIED_FAILURE', transport=None)
    finally:
        b.admitted_body = None
        b.close()
    out['resource'] = b.audit('CAPTURED' if out['failure'] is None else 'FAILED')
    failure_redirect = ((out['failure'] or {}).get('transport') or {}).get('redirect')
    out['redirect_observed'] = any(r['redirect'] not in (None, 'NONE') for r in out['responses']) or failure_redirect not in (None, 'NONE')      # `resource.redirects` counts only redirects FOLLOWED, and none is
    out['cleanup'] = 'BOUNDARY_CLOSED'
    return out


def live(cfg, directory):
    import requests
    with requests.Session() as s:
        s.trust_env = False
        s.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
        previous = [None]

        def dispatch(method, url, **kwargs):
            if previous[0] is not None:
                time.sleep(max(0, 0.4 - (time.monotonic() - previous[0])))      # the reader's own spacing
            previous[0] = time.monotonic()
            kwargs.pop('deadline', None)
            kwargs['timeout'] = (LIMITS['connect_seconds'], LIMITS['read_seconds'])
            return s.request(method, url, **kwargs)
        result = capture(dispatch, cfg, directory)
    result['cleanup'] = 'SESSION_BOUNDARY_CLOSED'
    return result


# ------------------------------------------------------------------------------------------------------------------------------ inspector (offline, pure)
_COUNT_PATTERNS = [
    ('SHOWING_RANGE_OF_TOTAL', re.compile(r'showing\s+\d+\s*[-–]\s*\d+\s+of\s+\d+', re.I)),
    ('NUMBER_RESULTS', re.compile(r'\b\d+\s+(?:results?|applications?|records?|matches|items?)\b', re.I)),
    ('OF_NUMBER', re.compile(r'\bof\s+\d+\b', re.I)),
    ('PAGE_NUMBER', re.compile(r'\bpages?\s+\d+(?:\s+of\s+\d+)?\b', re.I)),
    ('TOTAL_NUMBER', re.compile(r'\btotal\w*\W{0,4}\d+\b', re.I)),
    ('END_OR_NONE_WORDING', re.compile(r'\b(?:no\s+(?:more\s+)?results?|end\s+of\s+results|last\s+page|only\s+page|all\s+results)\b', re.I)),
]
_NAME_SIGNAL = re.compile(r'(total|count|page|pager|paging|result|next|prev|more|last)', re.I)
_NAV_TEXT = re.compile(r'^\W*(next|previous|prev|more|first|last|older|newer)\W*$|^[«»<>]{1,2}$', re.I)
_SCRIPT_NUMBER = re.compile(r'(total\w*|count\w*|results?\w*|pages?\w*|numfound|numberofresults)["\']?\s*[:=]\s*["\']?(\d{1,7})', re.I)
_ATTRIBUTES = ('title', 'aria-label', 'alt', 'placeholder', 'content')
SCANNED = ['text nodes outside the results list', 'HTML comments', 'script bodies (inline)', 'title/aria-label/alt/placeholder/content/data-* attributes outside the results list',
           'anchors, link elements, forms, inputs, meta tags, select#resultsPerPage', 'the existing parser view of the same bytes']
NOT_SCANNED = ['the results list and every record subtree (record text, deliberately)', 'external scripts and stylesheets', 'JavaScript-rendered DOM', 'HTTP headers', 'a body that is not strict UTF-8 or exceeds %d bytes' % MAX_INSPECT_BYTES]


def _chain(tag):
    parts = []
    for parent in [tag, *tag.parents][:5]:
        if parent.name in (None, '[document]'):
            break
        ident = ('#' + parent.get('id')) if parent.get('id') else ''
        klass = ('.' + '.'.join(parent.get('class', []))) if parent.get('class') else ''
        parts.append(parent.name + ident + klass)
    return ' < '.join(parts)[:200]


def _clip(text, limit=TEXT):
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit] + '…'


def _path(href):
    """The path only: no query, fragment or path parameter (a `;jsessionid=...` is a token)."""
    return re.sub(r'[?#;].*$', '', href or '')[:120]


def _safe_value(value):
    value = value or ''
    return value if re.fullmatch(r'\d{1,10}', value) else '<%d chars>' % len(value)


def inspect_html(raw, cfg=None):
    """Structural findings in one saved response, with no record text and no token: the results list (and every `li.searchresult`) is never read or described, and when the list cannot be located
    exactly once all free text is suppressed. Observed facts only; `scanned` / `not_scanned` state what this did and did not examine, so an empty list is never read as exhaustive."""
    from bs4 import BeautifulSoup, Comment
    cfg = cfg or config()
    out = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), scanned=list(SCANNED), not_scanned=list(NOT_SCANNED))
    if len(raw) > MAX_INSPECT_BYTES:
        return dict(out, availability='TOO_LARGE')
    try:
        html = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        return dict(out, availability='INVALID_ENCODING', scanned=[])
    soup = BeautifulSoup(html, 'html.parser')
    results = soup.select('#searchresults')
    rows = soup.select('li.searchresult')
    protected_roots = [*results, *rows]
    records = set()      # object ids of every protected element and descendant, computed once
    for root in protected_roots:
        records.add(id(root))
        records.update(id(x) for x in root.descendants)
    contain = {id(a) for root in protected_roots for a in root.parents}      # ancestors of protected content: described never (their text includes it)
    located = len(results) == 1 and len(soup.select('#searchresults > li.searchresult')) >= 1
    suppress = not located
    out['availability'] = 'PRESENT'
    out['text_suppressed'] = suppress
    out['structure'] = dict(
        results_containers=len(results), result_rows=len(soup.select('#searchresults > li.searchresult')), rows_anywhere=len(rows),
        other_children=len([c for r in results for c in r.find_all('li', recursive=False) if 'searchresult' not in c.get('class', [])]),
        headings=[] if suppress else [_clip(h.get_text(), 80) for h in soup.select('h1, h2') if id(h) not in records and id(h) not in contain][:MAX_ITEMS],
        message_boxes=len(soup.select('div.messagebox')), forms=len(soup.select('form')),
        results_per_page=[dict(value=o.get('value'), selected=o.has_attr('selected')) for o in soup.select('select#resultsPerPage option')][:MAX_ITEMS])

    def text_of(value, limit=TEXT):
        return '<suppressed>' if suppress else _clip(value, limit)

    count_text = []
    for node in soup.find_all(string=True):
        parent = node.parent
        if parent is None or id(parent) in records or parent.name == 'style':
            continue      # a string is described only if it is NOT inside the protected results; an ancestor's own strings are not record text
        kind = 'COMMENT' if isinstance(node, Comment) else 'SCRIPT' if parent.name == 'script' else None
        text = _clip(str(node), 400 if kind == 'SCRIPT' else TEXT)
        for name, pattern in _COUNT_PATTERNS:
            match = pattern.search(text)
            if text and match:
                snippet = _clip(text[max(0, match.start() - 30):match.end() + 30]) if kind == 'SCRIPT' else text
                count_text.append(dict(source=kind or 'TEXT', pattern=name, element=_chain(parent), text=text_of(snippet)))
    out['count_text'] = count_text[:MAX_ITEMS]
    named = []
    attribute_hits = []
    navigation_text = []
    scanned_tags = 0
    for tag in soup.find_all(True):
        scanned_tags += 1
        if scanned_tags > MAX_TAGS:
            out['scan_truncated'] = True
            break
        if id(tag) in records or tag.name in ('script', 'style', 'html', 'head', 'body'):
            continue
        for name, value in tag.attrs.items():
            if isinstance(value, list):
                continue
            if name in _ATTRIBUTES or name.startswith('data-'):
                hit = next((p for p, pattern in _COUNT_PATTERNS if pattern.search(str(value))), None)
                numeric = name.startswith('data-') and _NAME_SIGNAL.search(name) and re.fullmatch(r'\d{1,10}', str(value))
                if hit or numeric:
                    attribute_hits.append(dict(element=_chain(tag), attribute=name, pattern=hit or 'NUMERIC_SIGNAL_ATTRIBUTE', value=_safe_value(str(value)) if numeric else text_of(str(value), 60)))
        own = ' '.join(str(t) for t in tag.find_all(string=True, recursive=False) if not isinstance(t, Comment))
        if tag.name in ('a', 'button', 'input', 'span', 'li') and _NAV_TEXT.match(_clip(own, 20) or (tag.get('value') or '')):
            navigation_text.append(dict(element=_chain(tag), text=text_of(own or tag.get('value') or '', 20), disabled=tag.has_attr('disabled') or tag.get('aria-disabled') == 'true'))
        if id(tag) in contain:
            continue
        label = ' '.join([tag.get('id') or '', *tag.get('class', [])])
        if label and _NAME_SIGNAL.search(label):
            disabled = tag.has_attr('disabled') or tag.get('aria-disabled') == 'true' or any('disabled' in c.lower() for c in tag.get('class', []))
            named.append(dict(element=_chain(tag), has_href=bool(tag.get('href')), disabled=disabled, text=text_of(own, 40)))
    out['navigation_like_elements'] = named[:MAX_ITEMS]
    out['attribute_signals'] = attribute_hits[:MAX_ITEMS]
    out['navigation_text'] = navigation_text[:MAX_ITEMS]
    links = []
    for a in soup.find_all(['a', 'link']):
        href = a.get('href') or ''
        rel = a.get('rel') or []
        if id(a) in records:
            continue
        if re.search(r'page|next|prev|first|last', href, re.I) or any(r in ('next', 'prev', 'previous', 'first', 'last') for r in rel) or any(re.search('next|prev|first|last|pag', c, re.I) for c in a.get('class', [])):
            names = sorted(set(re.findall(r'[?&;]([A-Za-z0-9_.]+)=', href)))
            links.append(dict(tag=a.name, rel=list(rel), classes=list(a.get('class', [])), href_path=_path(href), parameter_names=names[:10], text=text_of(a.get_text(), 40)))
    out['navigation_links'] = links[:MAX_ITEMS]
    inputs = []
    for field in soup.find_all('input'):
        name = field.get('name') or ''
        if _NAME_SIGNAL.search(name) and id(field) not in records:
            form = field.find_parent('form')
            inputs.append(dict(name=name, type=field.get('type'), form_action=_path(form.get('action', '') if form else ''), value=_safe_value(field.get('value'))))
    out['signal_inputs'] = inputs[:MAX_ITEMS]
    scripts = []
    for sc in soup.find_all('script'):
        body = sc.string or ''
        found = [dict(name=m.group(1), value=int(m.group(2))) for m in _SCRIPT_NUMBER.finditer(body)]
        if found or re.search(r'total|numfound|pager', body, re.I):
            scripts.append(dict(bytes=len(body), has_src=bool(sc.get('src')), numeric_assignments=found[:10]))
    out['scripts'] = scripts[:MAX_ITEMS]
    out['meta'] = [dict(name=m.get('name') or m.get('property'), content=_safe_value(m.get('content'))) for m in soup.find_all('meta') if _NAME_SIGNAL.search((m.get('name') or m.get('property') or ''))][:MAX_ITEMS]
    try:
        page = parse_page(raw, cfg.council, 1, cfg.start, cfg.end, cfg.semantics)
        out['parser'] = dict(accepted=True, rows=len(page.rows), first=page.first, last=page.last, total=page.total, terminal=page.terminal, next_url_present=page.next_url is not None, page_size=page.page_size)
    except ListingError as exc:
        out['parser'] = dict(accepted=False, error=type(exc).__name__)
    pagers = soup.select('p.pager')
    out['parser_selector'] = dict(pager_elements=len(pagers), next_anchors_in_pager=len([a for p in pagers for a in p.select('a.next')]))
    return out


# ------------------------------------------------------------------------------------------------------------------------------ registration and run
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def render(identity, revision, tree, issued, expires):
    """An INACTIVE local proposal. It authorises nothing until the owner approves its exact hash; rendering starts no clock and makes no request."""
    if not IDENTITY.fullmatch(identity) or not re.fullmatch('[0-9a-f]{40}', revision) or not re.fullmatch('[0-9a-f]{40}', tree):
        raise ValueError('IDENTITY_OR_GIT_BINDING')
    a, b = datetime.fromisoformat(issued), datetime.fromisoformat(expires)
    if a.tzinfo is None or b.tzinfo is None or not timedelta(0) < b - a <= timedelta(hours=LIMITS['max_registration_hours']):
        raise ValueError('EXPIRY_INTERVAL')
    return dict(kind=KIND, identity=identity, scope=dict(SCOPE), revision=revision, tree=tree, limits=dict(LIMITS), issued_at=issued, expires_at=expires, stop_treatment=PERMIT,
                preserved_stops=list(PRESERVED), database_synchronised=False, publication='NONE', raw_html='PRIVATE_OWNER_LOCAL_0600', collection_observation=False,
                containment=dict(scope_unit=SCOPE_UNIT, memory_max_bytes=MEMORY_BYTES, memory_swap_max_bytes=0))


def validate(registration, registration_sha256, raw, *, git, clock=lambda: datetime.now(timezone.utc)):
    """The exact bytes, the exact content, the clock AND the checkout are all required: `git` has no default and a missing one fails closed."""
    if not isinstance(git, dict) or set(git) != {'head', 'tree', 'dirty'}:
        raise ValueError('CHECKOUT_BINDING')
    if sha(raw) != registration_sha256 or canonical(registration) != raw or len(raw) > 16384:
        raise ValueError('REGISTRATION_HASH')
    if registration != render(registration.get('identity', ''), registration.get('revision', ''), registration.get('tree', ''), registration.get('issued_at', ''), registration.get('expires_at', '')):
        raise ValueError('REGISTRATION_CHANGED')
    now = clock()
    if not datetime.fromisoformat(registration['issued_at']) <= now < datetime.fromisoformat(registration['expires_at']):
        raise ValueError('REGISTRATION_NOT_CURRENT')
    if git['head'] != registration['revision'] or git['tree'] != registration['tree'] or git['dirty']:
        raise ValueError('CHECKOUT_BINDING')
    return registration


def _git():
    import subprocess
    repo = str(Path(__file__).resolve().parents[2])      # this module's own repository, not the caller's working directory

    def out(*args):
        return subprocess.check_output(['git', '-C', repo, *args], text=True).strip()
    return dict(head=out('rev-parse', 'HEAD'), tree=out('rev-parse', 'HEAD^{tree}'), dirty=bool(out('status', '--porcelain')))


def containment(proc='/proc/self/cgroup', sys_root='/sys/fs/cgroup'):
    """The run must already be inside the dedicated transient scope with exactly the registered memory limit and no swap (read-only inspection of this process's own cgroup)."""
    lines = Path(proc).read_text().splitlines()
    if len(lines) != 1 or not lines[0].startswith('0::/'):
        raise ValueError('CGROUP_V2_REQUIRED')
    relative = Path(lines[0][3:])
    if relative.name != SCOPE_UNIT or '..' in relative.parts:
        raise ValueError('DIAGNOSTIC_SCOPE_REQUIRED')
    root = Path(sys_root) / str(relative).lstrip('/')
    if root.is_symlink() or root.joinpath('memory.max').read_text().strip() != str(MEMORY_BYTES) or root.joinpath('memory.swap.max').read_text().strip() != '0':
        raise ValueError('DIAGNOSTIC_MEMORY_LIMIT')
    return dict(scope=str(relative), memory_max=MEMORY_BYTES, swap_max=0)


def _state_root():
    STATE_ROOT.mkdir(mode=0o700, exist_ok=True)
    st = STATE_ROOT.lstat()
    if STATE_ROOT.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise ValueError('STATE_ROOT')
    return STATE_ROOT


def _verified_claim(directory, registration_sha256):
    """What the worker requires before any request: the parent's fresh claim directory, holding the validated registration and nothing else."""
    directory = Path(directory)
    if directory.is_symlink() or directory.parent != _state_root() or sorted(x.name for x in directory.iterdir()) != ['registration.json']:
        raise ValueError('CLAIM_REQUIRED')
    raw = (directory / 'registration.json').read_bytes()
    registration = validate(json.loads(raw), registration_sha256, raw, git=_git())
    if registration['identity'] != directory.name:
        raise ValueError('CLAIM_IDENTITY')
    containment()
    return registration


def main(argv=None):
    import argparse
    from verification.stage26b_l1.actions_runner import supervise
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='mode', required=True)
    r = sub.add_parser('render')
    r.add_argument('--identity', required=True)
    r.add_argument('--revision', required=True)
    r.add_argument('--tree', required=True)
    r.add_argument('--issued-at', required=True)
    r.add_argument('--expires-at', required=True)
    r.add_argument('--output', required=True, type=Path)
    u = sub.add_parser('run')
    u.add_argument('--registration', required=True, type=Path)
    u.add_argument('--registration-sha256', required=True)
    u.add_argument('--enable-reviewed-source-only-diagnostic', action='store_true')
    w = sub.add_parser('worker')
    w.add_argument('--directory', required=True, type=Path)
    w.add_argument('--registration-sha256', required=True)
    i = sub.add_parser('inspect')
    i.add_argument('--file', required=True, type=Path)
    a = p.parse_args(argv)
    if a.mode == 'render':
        value = render(a.identity, a.revision, a.tree, a.issued_at, a.expires_at)
        raw = canonical(value)
        fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        print('INACTIVE_DIAGNOSTIC_REGISTRATION_RENDERED sha256=' + sha(raw))
        return 0
    if a.mode == 'inspect':
        print(json.dumps(inspect_html(a.file.read_bytes()), sort_keys=True, indent=1))
        return 0
    if any(any(s in k.upper() for s in FORBIDDEN_ENV) for k in os.environ):
        raise ValueError('OWNER_CREDENTIAL_CONTEXT')
    if a.mode == 'worker':
        _verified_claim(a.directory, a.registration_sha256)      # no registration, claim, hash, expiry, checkout or scope: no request
        result = live(config(), a.directory)
        raw = canonical(result)
        if len(raw) > 65536:
            raise ValueError('AUDIT_BOUND')
        _write_private(a.directory, 'audit.json', raw)
        return 0 if result['failure'] is None else 1
    raw = a.registration.read_bytes()
    registration = validate(json.loads(raw), a.registration_sha256, raw, git=_git())
    if not a.enable_reviewed_source_only_diagnostic:
        raise ValueError('DIAGNOSTIC_NOT_ENABLED')
    containment()      # before the claim is consumed and before any request
    root = _state_root()
    directory = root / registration['identity']
    directory.mkdir(mode=0o700, exist_ok=False)      # the single-use claim: an existing directory refuses, and a failed or interrupted run is never replayed
    _write_private(directory, 'registration.json', raw)

    def cancel(signum, frame):
        raise KeyboardInterrupt('SIGTERM')      # supervise() kills the worker's whole process group on any interruption
    signal.signal(signal.SIGTERM, cancel)
    code, expired = supervise([sys.executable, '-m', 'verification.discovery.idox_response_diagnostic', 'worker', '--directory', str(directory), '--registration-sha256', a.registration_sha256],
                              env={'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}, deadline=LIMITS['supervisor_seconds'])
    audit_path = directory / 'audit.json'
    summary = json.loads(audit_path.read_bytes()) if audit_path.is_file() and audit_path.stat().st_size <= 65536 else None
    print(json.dumps(dict(identity=registration['identity'], worker_exit=code, expired=expired, private_directory=str(directory), audit=summary), sort_keys=True))
    return 0 if code == 0 and not expired and isinstance(summary, dict) and summary.get('failure', 'MALFORMED') is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
