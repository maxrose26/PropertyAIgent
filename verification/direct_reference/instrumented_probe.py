"""Credential-free, frozen-reference transport reconnaissance. Never writes B2."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

CASES = {
    'manchester': (688, '142419/FO/2025', 'https://arcusbe.manchester.gov.uk/pr/s/detail/a1DSl000007GOmFMAW?c__r=Arcus_BE_Public_Register'),
    'manchester_pending': (1299, '138696/FO/2023', 'https://arcusbe.manchester.gov.uk/pr/s/detail/a1DSl000007GO89MAG?c__r=Arcus_BE_Public_Register'),
    'salford': (252, 'PA/2025/1084', 'https://salfordcitycouncil.my.site.com/pr/s/detail/a0kSq000008OfVFIA0?c__r=Arcus_BE_Public_Register'),
    'rochdale': (295, '25/01149/FUL', 'https://account.rochdale.gov.uk/pr/s/detail/a0rSl00000eZEmGIAW?c__r=Arcus_BE_Public_Register'),
    'trafford': (290, '117039/FUL/25', 'https://pa.trafford.gov.uk/online-applications/applicationDetails.do?keyVal=T0TL4VQL01T00&activeTab=summary'),
}
MAX_BYTES = 20 * 1024 * 1024
MAX_REQUESTS = 80
MAX_SECONDS = 45


def origin(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('DESTINATION')
    return 'https://' + u.netloc


def safe_path(url):
    """No query, fragment or credential/session-bearing arbitrary path retained."""
    path = urlsplit(url).path
    if path.endswith('/aura'):
        return path if re.fullmatch(r'/[A-Za-z0-9_/-]{1,100}', path) else '/[public-site]/aura'
    for prefix in ('/pr/s/sfsites/', '/pr/sfsites/', '/pr/resource/', '/pr/webruntime/'):
        if path.startswith(prefix):
            return prefix + '[resource]'
    if path.startswith('/pr/s/'):
        return '/pr/s/[page]'
    if path == '/online-applications/applicationDetails.do':
        return path
    return '/[resource]'


def post_descriptors(body):
    """Only Salesforce action identifiers; no argument values/context/tokens."""
    if not body or len(body) > 65536:
        return []

    try:
        message = parse_qs(body).get('message', [''])[0]
        actions = json.loads(message).get('actions', [])
        return [a['descriptor'] for a in actions[:10]
                if isinstance(a, dict) and isinstance(a.get('descriptor'), str)
                and re.fullmatch(r'[A-Za-z0-9_$.:/+-]{1,240}', a['descriptor'])]
    except (ValueError, TypeError, AttributeError):
        return []


def post_metadata(body, destination):
    """Describe public RPC operations without retaining params, context or tokens."""
    if not body or len(body) > 65536:
        return []
    try:
        form = parse_qs(body, keep_blank_values=True)
        actions = json.loads(form.get('message', [''])[0]).get('actions', [])
        records = []
        for action in actions[:10]:
            params = action.get('params', {})
            record = {}
            for key in ('descriptor',):
                value = action.get(key)
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_$.:/+-]{1,240}',value):
                    record[key] = value
            for key in ('namespace', 'classname', 'className', 'method', 'methodName'):
                value=params.get(key)
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.$]{0,160}',value):
                    record[key] = value
            inner=params.get('params', {})
            record['argument_keys'] = sorted(k for k in inner if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}',k))[:20] if isinstance(inner,dict) else []
            record_id=urlsplit(destination).path.rsplit('/',1)[-1]
            record['contains_frozen_record_id'] = record_id in json.dumps(inner)
            record['token_state'] = 'ABSENT' if 'aura.token' not in form else 'NULL' if form['aura.token'] == ['null'] else 'EMPTY' if form['aura.token'] == [''] else 'PRESENT_NOT_RETAINED'
            records.append(record)
        return records
    except (ValueError, TypeError, AttributeError):
        return []


def qualify(pairs, reference):
    aliases = {'reference': ('Reference', 'Application Reference', 'Planning Application'),
               'status': ('Status',), 'decision': ('Decision',),
               'decision_date': ('Decision notice sent date', 'Decision date', 'Decision Issued Date')}
    result = {}
    for field, labels in aliases.items():
        values = [v.strip() for k, v in pairs if k.strip() in labels]
        if not values:
            state, value = 'NOT_PRESENT', None
        elif len(values) != 1:
            state, value = 'CONFLICTING', None
        else:
            value = values[0]
            state = 'PRESENT_VALUE' if value else 'PRESENT_BLANK'
        if value is not None and len(value) > 160:
            state, value = 'UNPARSEABLE', None
        result[field] = {'state': state, 'value': value}
    exact = result['reference'] == {'state': 'PRESENT_VALUE', 'value': reference}
    return exact, result


def permitted_navigation(url, expected):
    if url == expected:
        return True
    a, b = urlsplit(url), urlsplit(expected)
    if b.netloc == 'pa.trafford.gov.uk' and url == 'https://pa.trafford.gov.uk/online-applications/':
        return True
    # Observed Salford client route retains the exact frozen Salesforce identity.
    if b.netloc == 'salfordcitycouncil.my.site.com':
        record = b.path.rsplit('/', 1)[-1]
        return (origin(url) == origin(expected) and a.path ==
                '/pr/s/planning-application/' + record + '/pa20251084'
                and a.query in (b.query, "") and not a.fragment)
    return False


def request_failure(url, method, resource_type, destination, count):
    if origin(url) != origin(destination):
        return 'UNADMITTED_ORIGIN'
    if count > MAX_REQUESTS:
        return 'REQUEST_LIMIT'
    if method not in ('GET', 'HEAD'):
        return 'UNREVIEWED_METHOD'
    if resource_type == 'Document' and not permitted_navigation(url, destination):
        return 'UNADMITTED_NAVIGATION'
    path = urlsplit(url).path.lower()
    if (re.search(r'\.(pdf|docx?|xlsx?|zip)$', path)
            or any(x in path for x in ('/sfc/', '/servlet/', '/filedownload', '/download/'))):
        return 'DOCUMENT_DENIED'
    return None


async def probe(case):
    from playwright.async_api import async_playwright
    app_id, reference, destination = CASES[case]
    allowed = origin(destination)
    audit = dict(case=case, application_id=app_id, reference=reference, destination=destination,
                 persistence=False, requests=0, responses=0, redirects=0,
                 decoded_bytes=0, encoded_bytes=0, pages=0, navigations=0, local_frames=0, frame_kinds=[],
                 requested_origins=[], navigated_origins=[], endpoints=[],
                 http_probe=None, blocked_actions=[], blocked_action_metadata=[], blocked_posts=0, failure=None, exact_reference=False, fields=None,
                 cleanup='UNKNOWN', navigation_mismatch=None, network_classification='UNKNOWN')
    started = time.monotonic()
    browser = context = None
    stopped = asyncio.Event()

    def fail(reason):
        if audit['failure'] is None:
            audit['failure'] = reason
        stopped.set()

    def charge(event):
        audit['decoded_bytes'] += event.get('dataLength', 0)
        audit['encoded_bytes'] += event.get('encodedDataLength', 0)
        if max(audit['decoded_bytes'], audit['encoded_bytes']) > MAX_BYTES:
            fail('BYTE_LIMIT')

    async def route_handler(event):
        request = event['request']
        audit['requests'] += 1
        try:
            url = request['url']
            request_origin = origin(url)
            if request_origin not in audit['requested_origins']:
                audit['requested_origins'].append(request_origin)
            descriptor = dict(origin=request_origin, path=safe_path(url),
                              method=request['method'], resource_type=event.get('resourceType'))
            if descriptor not in audit['endpoints'] and len(audit['endpoints']) < 80:
                audit['endpoints'].append(descriptor)
            if event.get('redirectedRequestId'):
                audit['redirects'] += 1
            if request['method'] not in ('GET', 'HEAD'):
                for descriptor in post_descriptors(request.get('postData')):
                    if descriptor not in audit['blocked_actions'] and len(audit['blocked_actions']) < 20:
                        audit['blocked_actions'].append(descriptor)
                for metadata in post_metadata(request.get('postData'), destination):
                    if metadata not in audit['blocked_action_metadata'] and len(audit['blocked_action_metadata']) < 20:
                        audit['blocked_action_metadata'].append(metadata)
            reason = request_failure(url, request['method'], event.get('resourceType'), destination, audit['requests'])
            if reason == 'UNREVIEWED_METHOD':
                audit['blocked_posts'] += 1
                metadata = post_metadata(request.get('postData'), destination)
                if audit['http_probe'] is None and any(
                        m.get('namespace') == 'arcuscommunity' and
                        m.get('classname') == 'PublicRegisterViewService' and
                        m.get('method') == 'getRecordHeaderDetails' for m in metadata):
                    from verification.direct_reference.arcus_http_probe import observed_guest_read, MAX_BODY
                    if audit['requests'] >= MAX_REQUESTS or audit['decoded_bytes'] + MAX_BODY > MAX_BYTES:
                        fail('HTTP_BUDGET_UNAVAILABLE')
                        await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                        return
                    audit['http_probe'] = observed_guest_read(url, request.get('postData'), destination, reference)
                    audit['requests'] += int(audit['http_probe']['attempted'])
                    audit['decoded_bytes'] += audit['http_probe']['received_bytes']
                    if audit['requests'] > MAX_REQUESTS or audit['decoded_bytes'] > MAX_BYTES:
                        fail('HTTP_AGGREGATE_BOUND')
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                return  # collect other blocked public-page actions; never dispatch them
            if reason:
                fail(reason)
            if audit['failure']:
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
            else:
                await client.send('Fetch.continueRequest', {'requestId':event['requestId']})
        except Exception:
            fail('ROUTE_ERROR')
            try:
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
            except Exception:
                pass

    def response_handler(response):
        audit['responses'] += 1
        headers = response.headers
        if ('attachment' in headers.get('content-disposition', '').lower() or
                headers.get('content-type', '').split(';')[0] in ('application/pdf', 'application/octet-stream')):
            fail('DOWNLOAD_DENIED')
        if response.status >= 400:
            fail('HTTP_ERROR')
        try:
            if int(headers.get('content-length', '0')) > MAX_BYTES:
                fail('BYTE_LIMIT')
        except ValueError:
            fail('INVALID_CONTENT_LENGTH')

    def navigation(frame):
        if frame.parent_frame is not None:
            kind = 'BLANK' if frame.url == 'about:blank' else 'SRCDOC' if frame.url == 'about:srcdoc' else 'NETWORK' if frame.url.startswith('https://') else 'OTHER'
            if len(audit['frame_kinds']) < 4:
                audit['frame_kinds'].append({'kind':kind,'direct_child':frame.parent_frame.parent_frame is None})
            # Permit only bounded local blank/srcdoc frame navigations.
            # This admits no additional network destination; scripts are not presumed inert.
            if frame.url in ('about:blank', 'about:srcdoc') and frame.parent_frame.parent_frame is None:
                audit['local_frames'] += 1
                if audit['local_frames'] > 2:
                    fail('FRAME_LIMIT')
            else:
                fail('FRAME_DENIED')
            return
        audit['navigations'] += 1
        try:
            seen = origin(frame.url)
            if seen not in audit['navigated_origins']:
                audit['navigated_origins'].append(seen)
            if not permitted_navigation(frame.url, destination):
                u=urlsplit(frame.url)
                frozen_id=urlsplit(destination).path.rsplit('/',1)[-1]
                audit['navigation_mismatch']={'same_origin':seen==allowed, 'contains_frozen_record_id':frozen_id in u.path, 'path':u.path if frozen_id in u.path and re.fullmatch(r'/[A-Za-z0-9_/-]{1,160}',u.path) else '[redacted]', 'query_keys':sorted(parse_qs(u.query))[:10], 'query_absent':not u.query, 'fragment_present':bool(u.fragment)}
                fail('UNADMITTED_NAVIGATION')
        except ValueError:
            fail('UNADMITTED_NAVIGATION')
        if audit['navigations'] > 2:
            fail('NAVIGATION_LIMIT')

    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(service_workers='block', accept_downloads=False)
                await context.route_web_socket('**/*', lambda ws: fail('WEBSOCKET_DENIED'))
                context.on('page', lambda _: (audit.update(pages=audit['pages'] + 1),
                                            fail('PAGE_LIMIT') if audit['pages'] > 1 else None))
                page = await context.new_page()
                page.on('framenavigated', navigation)
                page.on('download', lambda _: fail('DOWNLOAD_DENIED'))
                page.on('worker', lambda _: fail('WORKER_DENIED'))
                page.on('response', response_handler)
                client = await context.new_cdp_session(page)
                await client.send('Network.enable')
                client.on('Network.dataReceived', charge)
                client.on('Fetch.requestPaused', route_handler)
                await client.send('Fetch.enable', {'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
                async def navigate():
                    if case == 'trafford':
                        await page.goto('https://pa.trafford.gov.uk/online-applications/', wait_until='domcontentloaded', timeout=12000)
                        if stopped.is_set():
                            return
                    await page.goto(destination, wait_until='domcontentloaded', timeout=25000)
                nav = asyncio.create_task(navigate())
                stop = asyncio.create_task(stopped.wait())
                done, _ = await asyncio.wait((nav, stop), return_when=asyncio.FIRST_COMPLETED)
                if stop in done:
                    nav.cancel()
                    await asyncio.gather(nav, return_exceptions=True)
                else:
                    await nav
                    # Read only relevant labels; never export whole HTML/body or people.
                    until = time.monotonic() + 8
                    while not stopped.is_set() and time.monotonic() < until:
                        pairs = await page.evaluate("""() => {
                          const labels = new Set(['Reference','Status','Decision','Decision notice sent date','Decision date','Decision Issued Date']);
                          const out=[], nodes=[];
                          function collect(root) { for(const el of root.querySelectorAll('*')) {
                            nodes.push(el); if(nodes.length>15000)throw Error('DOM_LIMIT');
                            if(el.shadowRoot)collect(el.shadowRoot);
                          }}
                          collect(document);
                          for(const el of nodes.filter(x=>['DT','TH'].includes(x.tagName))) {
                            const key=el.innerText.trim(); if(!labels.has(key))continue;
                            const next=el.nextElementSibling;
                            if(next && ['DD','TD'].includes(next.tagName)) out.push([key,next.innerText.trim().slice(0,161)]);
                          }
                          const hs=out.some(x=>x[0]==='Reference')?[]:nodes.filter(x=>x.tagName==='H1');
                          for(const h of hs) if(h.innerText.trim().length<100 && !h.innerText.includes('Application Summary'))out.push(['Reference',h.innerText.trim()]);
                          return out.slice(0,30);
                        }""")
                        exact, fields = qualify(pairs, reference)
                        audit.update(exact_reference=exact, fields=fields)
                        if exact and fields['status']['state'] == 'PRESENT_VALUE':
                            break
                        await asyncio.sleep(.2)
                    if audit['blocked_posts']:
                        fail('UNREVIEWED_METHOD')
                    elif not audit['exact_reference']:
                        fail('IDENTITY_NOT_ESTABLISHED')
                    elif not audit['fields'] or audit['fields']['status']['state'] != 'PRESENT_VALUE':
                        fail('STATUS_NOT_ESTABLISHED')
                stop.cancel()
                await asyncio.gather(stop, return_exceptions=True)
            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()
                audit['cleanup'] = 'CONTEXT_BROWSER_CLOSED' if browser is not None else 'NOT_STARTED'
    except Exception as exc:
        fail('BROWSER_' + type(exc).__name__)
    audit['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return audit


def supervised(case, output):
    import psutil
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise ValueError('DISPOSABLE_HOSTED_RUNNER_ONLY')
    if int(Path('/proc/self/stat').read_text().split()[0]) != os.getpid():
        raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    start = time.monotonic()
    seen = {}
    peak = 0
    expired = False
    with tempfile.TemporaryDirectory(prefix='stage4-probe-') as directory:
        child_output = Path(directory) / 'result.json'
        env = dict(PATH='/usr/bin:/bin', HOME=directory, TMPDIR=directory, LANG='C.UTF-8',
                   PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        # Browser package cache only; no inherited database, model or GitHub credentials.
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path.home()/'.cache/ms-playwright'))
        child = subprocess.Popen([sys.executable, '-m', 'verification.direct_reference.instrumented_probe', '--worker', '--case', case,
                                  '--output', str(child_output)], env=env, start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parent = psutil.Process(child.pid)
        try:
            while child.poll() is None:
                rss = 0
                try:
                    owned = [parent] + parent.children(recursive=True)
                except psutil.NoSuchProcess:
                    break
                for process in owned:
                    try:
                        seen[process.pid] = process.create_time()
                        rss += process.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, rss)
                if time.monotonic() - start > MAX_SECONDS or rss > 1024**3:
                    expired = True
                    break
                time.sleep(.1)
        finally:
            if child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait(timeout=5)
            killed=[]
            for pid, born in seen.items():
                try:
                    p = psutil.Process(pid)
                    if p.create_time() == born and p.status() != psutil.STATUS_ZOMBIE:
                        p.kill(); killed.append(p)
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(killed, timeout=3)
        survivors = []
        for pid, born in seen.items():
            try:
                p = psutil.Process(pid)
                if p.create_time() == born and p.status() != psutil.STATUS_ZOMBIE:
                    survivors.append(pid)
            except psutil.NoSuchProcess:
                pass
        result = (json.loads(child_output.read_text()) if child_output.exists() and child_output.stat().st_size < 65536
                  else {'case': case, 'failure': 'NO_WORKER_AUDIT', 'persistence': False})
        result.update(supervisor_seconds=round(time.monotonic()-start, 3), peak_owned_rss=peak,
                      owned_processes_seen=len(seen), live_owned_survivors=len(survivors),
                      supervisor_limit_hit=expired, process_cleanup='CLOSED' if not survivors else 'FAILED')
        if expired or survivors:
            result['failure'] = 'SUPERVISOR_BOUND_OR_CLEANUP'
        output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('failure') is None else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', action='store_true')
    a = p.parse_args()
    if any(name in os.environ for name in ('DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')):
        raise ValueError('CREDENTIAL_FREE_ONLY')
    if a.output.exists():
        raise ValueError('EXISTING_OUTPUT')
    if a.worker:
        a.output.write_text(json.dumps(asyncio.run(probe(a.case)), indent=2) + '\n')
        return 0
    return supervised(a.case, a.output)


if __name__ == '__main__':
    raise SystemExit(main())
