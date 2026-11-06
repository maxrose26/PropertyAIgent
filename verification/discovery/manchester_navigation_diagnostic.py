"""Fixed one-document Manchester diagnostic. No enumeration or intake admission."""
import asyncio
import json
import time
from verification.direct_reference.instrumented_probe import browser_diagnostic
from verification.discovery.arcus_ui_config import MANCHESTER, dated_config

MODE = 'MANCHESTER_INITIAL_NAVIGATION_V1'
ROW = dict(council='manchester', semantics='VALIDATED', start='2026-10-27', end='2026-11-02')
DESTINATION = dated_config(MANCHESTER, ROW['start'], ROW['end']).destination
MAX_BYTES = 20 * 1024 * 1024


async def observe():
    from playwright.async_api import async_playwright
    result = dict(version=MODE, row=ROW, coverage='NOT_ESTABLISHED',
                  physical_requests=0, retries=0, responses=0, http_status=None,
                  blocked_requests=0, stage='BROWSER_SETUP', exception_class=None,
                  network_error='UNKNOWN', cleanup='UNKNOWN', bytes=0,
                  status='INCOMPLETE', transport='CHROMIUM_FETCH_GATE')
    browser = context = None
    stopped = asyncio.Event()
    tasks = set()
    started = time.monotonic()

    async def request(event):
        # All browser requests are paused BEFORE transport. The slot is consumed
        # synchronously before the first await; parallel events cannot share it.
        allowed = (result['physical_requests'] == 0 and not stopped.is_set()
                   and event.get('resourceType') == 'Document'
                   and not event.get('redirectedRequestId')
                   and event['request'].get('url') == DESTINATION
                   and event['request'].get('method') == 'GET')
        if not allowed:
            result['blocked_requests'] += 1
            await client.send('Fetch.failRequest', dict(requestId=event['requestId'], errorReason='BlockedByClient'))
            return
        result['physical_requests'] = 1
        await client.send('Fetch.continueRequest', dict(requestId=event['requestId']))

    def received(event):
        if event.get('type') != 'Document' or result['responses']:
            return
        result['responses'] = 1
        status = event.get('response', {}).get('status')
        result['http_status'] = int(status) if isinstance(status, (int, float)) and 100 <= status <= 599 else None
        result['status'] = 'FIRST_RESPONSE_OBSERVED'
        stopped.set()  # Header observation is sufficient; no body/DOM retention.

    def redirected(event):
        if event.get('redirectResponse'):
            received(dict(type='Document', response=event['redirectResponse']))

    def charge(event):
        result['bytes'] += max(0, event.get('dataLength', 0)) + max(0, event.get('encodedDataLength', 0))
        if result['bytes'] > MAX_BYTES:
            result['status'] = 'BYTE_LIMIT'; stopped.set()

    def failed(event):
        if event.get('type') == 'Document' and not result['responses']:
            from verification.direct_reference.instrumented_probe import network_error_code
            result['network_error'] = network_error_code(event.get('errorText', ''))

    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(service_workers='block', accept_downloads=False)
                await context.route_web_socket('**/*', lambda ws: ws.close())
                page = await context.new_page()
                client = await context.new_cdp_session(page)
                client.on('Fetch.requestPaused', request)
                client.on('Network.responseReceived', received)
                client.on('Network.requestWillBeSent', redirected)
                client.on('Network.dataReceived', charge)
                client.on('Network.loadingFailed', failed)
                await client.send('Network.enable')
                await client.send('Network.setCacheDisabled', {'cacheDisabled': True})
                await client.send('Fetch.enable', {'patterns': [{'urlPattern': '*', 'requestStage': 'Request'}]})
                result['stage'] = 'INITIAL_NAVIGATION'
                nav = asyncio.create_task(page.goto(DESTINATION, wait_until='commit', timeout=25000))
                stop = asyncio.create_task(stopped.wait()); tasks.update((nav, stop))
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if nav in done:
                    response = await nav
                    # Playwright's commit acknowledgement can precede this CDP
                    # session's response event. Preserve the returned response.
                    if response is not None and not result['responses']:
                        received(dict(type='Document',response=dict(status=response.status)))
                # Never enumerate, submit criteria, follow redirect or read DOM.
            except Exception as exc:
                diagnostic = browser_diagnostic(exc, result['stage'])
                result.update(exception_class=diagnostic['exception_class'])
                if diagnostic['network_error'] != 'UNKNOWN': result['network_error'] = diagnostic['network_error']
                if not result['responses']: result['status'] = 'NAVIGATION_FAILED'
            finally:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    if context is not None: await context.close()
                finally:
                    if browser is not None: await browser.close()
                result['cleanup'] = 'CONTEXT_BROWSER_CLOSED' if browser is not None else 'NOT_STARTED'
    except Exception as exc:
        result['cleanup'] = 'UNVERIFIED'
        result['cleanup_exception_class'] = browser_diagnostic(exc, 'CLEANUP')['exception_class']
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def live():
    return asyncio.run(observe())
