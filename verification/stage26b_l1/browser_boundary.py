"""Verification-only browser interception using existing Stage 1 primitives.

Not a live command. Dispatch is supplied by the caller/rehearsal. Every browser
request is CDP-paused; native browser networking is independently denied by the
existing protected_browser guardian. Unknown XHR routes fail closed.
"""
from contextlib import contextmanager
import tempfile
from types import SimpleNamespace
from urllib.parse import urlsplit
from app.security.document_browser import _PausedRoute
from app.security.document_process import protected_browser
from .request_boundary import BoundaryFailure

class StatusSession:
    def __init__(self, boundary): self.boundary=boundary
    def get(self, url, **kwargs):
        status, headers, payload=self.boundary.request('GET',url)
        if 300 <= status < 400:
            self.boundary.budget.reject('PARTIAL_RETRIEVAL','direct summary redirect not accepted')
        return SimpleNamespace(status_code=status,headers=headers,text=payload.decode('utf-8','strict'))

class Renderer:
    def __init__(self, context, boundary):
        self.context,self.boundary=context,boundary
        self.page=None
        self.chain={}

    def deny(self, reason):
        if self.boundary.budget.failure is None:
            self.boundary.budget.failure=BoundaryFailure('PARTIAL_RETRIEVAL',reason)

    def route(self, route):
        try:
            req=route.request
            status,headers,payload=self.boundary.request(req.method,req.url,
                body=req.post_data_buffer,headers=req.headers,redirected=route.previous is not None)
            # Session cookies stay in the isolated dispatch jar. Browser cookie
            # values are never forwarded or returned in audit metadata.
            filtered={k:v for k,v in headers.items() if k.lower() not in
                ('content-length','content-encoding','transfer-encoding','set-cookie')}
            csp="worker-src 'none'; object-src 'none'; frame-src 'none'"
            existing=filtered.pop('Content-Security-Policy',filtered.pop('content-security-policy',''))
            filtered['Content-Security-Policy']=(existing+', ' if existing else '')+csp
            route.fulfill(status=status,headers=filtered,body=payload)
        except BaseException:
            self.deny('interception failed')
            route.abort('blockedbyclient')

@contextmanager
def status_page(browser_type, boundary):
    context=None
    with tempfile.TemporaryDirectory(prefix='propertyaigent-document-') as directory:
        with protected_browser(browser_type,directory,remove_on_parent_loss=True) as (browser,process):
            try:
                context=browser.new_context(service_workers='block',offline=True,accept_downloads=False)
                renderer=Renderer(context,boundary)
                browser.on('disconnected',lambda:renderer.deny('browser disconnected'))
                context.route_web_socket('**/*',lambda _:renderer.deny('websocket denied'))
                def new_page(page):
                    if renderer.page is not None:
                        renderer.deny('popup denied');page.close()
                context.on('page',new_page)
                context.on('requestfailed',lambda _:renderer.deny('browser request failed'))
                page=context.new_page();renderer.page=page
                page.on('worker',lambda _:renderer.deny('worker denied'))
                page.on('download',lambda _:renderer.deny('download denied'))
                page.on('console',lambda m:renderer.deny('service worker denied') if
                    m.text=='Service Worker registration blocked by Playwright' else None)
                client=context.new_cdp_session(page)
                client.on('Log.entryAdded',lambda e:renderer.deny('security violation') if
                    e.get('entry',{}).get('source')=='security' else None)
                client.send('Log.enable');client.send('Network.enable')
                client.on('Network.webTransportCreated',lambda _:renderer.deny('webtransport denied'))
                def paused(event):
                    try:renderer.route(_PausedRoute(client,event))
                    except BaseException:
                        renderer.deny('CDP failure')
                        client.send('Fetch.failRequest',dict(requestId=event['requestId'],errorReason='BlockedByClient'))
                client.on('Fetch.requestPaused',paused)
                client.send('Fetch.enable',{'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
                page.set_default_timeout(15000);page.set_default_navigation_timeout(15000)
                yield page
                boundary.budget.check()
            finally:
                if context is not None:context.close()
                boundary.close()
                process.finish_files(not bool(boundary.budget.failure))
        process.wait_custodian()
