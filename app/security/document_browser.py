"""Dedicated offline browser renderer with verified HTTP transport and disk downloads.

Chromium never dispatches document HTTP itself. Route fulfillment is limited to
20 MiB renderable resources. Attachments stream to disk (existing 200 MiB ceiling);
a tiny attachment acknowledgement supplies Playwright's download event, while the
adapter consumes only the corresponding verified artifact, never its placeholder.
"""
from contextlib import contextmanager
from pathlib import Path
import shutil
import json
import secrets
import os
import base64
from types import SimpleNamespace
import tempfile
import time
from urllib.parse import urljoin, urlsplit
import requests
from app.security.outbound import DocumentSession, DestinationDenied, destination
from app.security.document_process import protected_browser, output_lock

RENDER_LIMIT = 20 * 1024 * 1024
DOWNLOAD_LIMIT = 200 * 1024 * 1024


class DocumentBrowserFailure(DestinationDenied):
    """Document discovery failed; do not record successful empty results."""


class _PausedRoute:
    """CDP interception includes redirects that Playwright route() omits."""
    def __init__(self, client, event):
        self.client=client
        self.key=event['requestId']
        self.previous=event.get('redirectedRequestId')
        req=event['request']
        data=None
        if req.get('hasPostData'):
            entries=req.get('postDataEntries')
            if entries and all('bytes' in entry for entry in entries):
                data=b''.join(base64.b64decode(entry['bytes'],validate=True) for entry in entries)
            elif 'postData' in req:data=req['postData'].encode()
            else:raise DocumentBrowserFailure('Unsupported document request body.')
        if data is not None and len(data)>RENDER_LIMIT:
            raise DocumentBrowserFailure('Document request body too large.')
        self.request=SimpleNamespace(url=req['url'],method=req['method'],headers=req['headers'],post_data_buffer=data)

    def fulfill(self, *, status, headers, body):
        self.client.send('Fetch.fulfillRequest',dict(requestId=self.key,responseCode=status,
            responseHeaders=[dict(name=k,value=str(v)) for k,v in headers.items()],
            body=base64.b64encode(body).decode()))

    def abort(self, reason):
        self.client.send('Fetch.failRequest',dict(requestId=self.key,errorReason='BlockedByClient'))


class DocumentRenderer:
    def __init__(self, context, source, directory):
        self.context=context
        self.source=source
        self.directory=Path(directory)
        self.page=None
        self.failure=None
        self.deadline=time.monotonic()+30
        self.artifacts={}
        self.verified_download_urls=set()
        self.mirrored_cookies=set()
        self.chain={}
        self.written={}
        self.output_journal=[]
        self.max_render_bytes=0
        self.max_chunk_bytes=0

    def operation(self, seconds):
        self.check()
        self.deadline=time.monotonic()+seconds

    def check(self):
        if not self.directory.is_dir() or (self.directory/'.document-aborted').exists():
            raise DocumentBrowserFailure('Document job ownership expired.')
        if self.failure is not None:
            raise DocumentBrowserFailure(self.failure)

    def deny(self, reason):
        self.failure=self.failure or reason

    def websocket(self, route):
        self.deny('Document WebSocket denied.')
        # Never connect_to_server: context closure tears down the denied socket.
        # Closing synchronously inside a reentrant CDP callback deadlocks Chromium.

    def route(self, route):
        response=None
        try:
            self.check()
            request=route.request
            parsed,host,_=destination(request.url)
            previous=route.previous
            hops,deadline,previous_url=self.chain.pop(previous,(0,self.deadline,None))
            if hops>5 or time.monotonic()>=deadline:
                raise DocumentBrowserFailure('Document redirect/deadline exceeded.')
            if previous is not None:
                if urlsplit(previous_url).scheme=='https' and parsed.scheme!='https':
                    raise DocumentBrowserFailure('Document downgrade denied.')
                if urlsplit(previous_url).hostname!=host and request.post_data_buffer:
                    raise DocumentBrowserFailure('Document cross-origin body denied.')
            # Browser cookie headers are not passed. Use exact-host cookies from
            # the isolated Requests jar; its RFC path/secure/expiry rules apply.
            response=DocumentSession(self.source).request(request.method,request.url,
                data=request.post_data_buffer,headers=request.headers,stream=True,
                timeout=max(.001,min(30,deadline-time.monotonic())),
                allow_redirects=False,deadline=deadline)
            headers={k:v for k,v in response.headers.items() if k.lower() not in
                     ('content-encoding','transfer-encoding','content-length','set-cookie')}
            # Add, do not replace an origin's more restrictive CSP.
            csp="worker-src 'none'; object-src 'none'"
            existing=headers.pop('Content-Security-Policy',headers.pop('content-security-policy',''))
            headers['Content-Security-Policy']=(existing+', ' if existing else '')+csp
            self._browser_cookies(host)
            if response.status_code in (301,302,303,307,308):
                target=urljoin(request.url,response.headers.get('Location',''))
                target_parsed,_,_=destination(target)
                if not response.headers.get('Location') or hops>=5 or (parsed.scheme=='https' and target_parsed.scheme!='https'):
                    raise DocumentBrowserFailure('Document redirect denied.')
                headers['Location']=target
                self.chain[route.key]=(hops+1,deadline,request.url)
                route.fulfill(status=response.status_code,headers=headers,body=b'')
                return
            response.raise_for_status()
            attachment='attachment' in response.headers.get('Content-Disposition','').lower()
            attachment=attachment or response.headers.get('Content-Type','').split(';')[0].lower() in ('application/pdf','application/octet-stream')
            limit=DOWNLOAD_LIMIT if attachment else RENDER_LIMIT
            size=0
            if attachment:
                if request.url in self.artifacts:
                    raise DocumentBrowserFailure('Ambiguous document download.')
                with tempfile.NamedTemporaryFile(dir=self.directory,delete=False) as output:
                    path=Path(output.name)
                    for chunk in response.iter_content(65536):
                        self.max_chunk_bytes=max(self.max_chunk_bytes,len(chunk));size+=len(chunk)
                        if size>limit:raise DocumentBrowserFailure('Document exceeds 200 MiB.')
                        output.write(chunk)
                self.artifacts[request.url]=path
                self.verified_download_urls.add(request.url)
                headers['Content-Disposition']='attachment; filename="verified-document"'
                route.fulfill(status=response.status_code,headers=headers,body=b'verified-transport-acknowledgement')
            else:
                body=bytearray()
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>limit:raise DocumentBrowserFailure('Document resource exceeds 20 MiB.')
                    body.extend(chunk)
                self.max_render_bytes=max(self.max_render_bytes,size)
                route.fulfill(status=response.status_code,headers=headers,body=bytes(body))
        except Exception as exc:
            self.deny('Document transport failed: '+type(exc).__name__)
            try:route.abort('blockedbyclient')
            except Exception:pass  # preserve first failure if browser already died
        finally:
            if response is not None:response.close()

    def _browser_cookies(self, host):
        current={(c.name,c.domain.lstrip('.'),c.path or '/') for c in self.source.cookies if c.domain.lstrip('.')==host}
        for name,domain,path in self.mirrored_cookies-current:
            if domain==host:self.context.clear_cookies(name=name,domain=domain,path=path)
        self.mirrored_cookies={key for key in self.mirrored_cookies if key[1]!=host}|current
        values=[]
        for c in self.source.cookies:
            if c.domain.lstrip('.')!=host:continue
            try:destination('https://'+host+(c.path or '/'))
            except DestinationDenied:continue
            value=dict(name=c.name,value=c.value,domain=host,path=c.path or '/',secure=c.secure,
                       httpOnly=('HttpOnly' in c._rest and c._rest['HttpOnly'] is not False))
            same_site=c._rest.get('SameSite')
            if same_site and same_site.capitalize() in ('Strict','Lax','None'):value['sameSite']=same_site.capitalize()
            if c.expires is not None:value['expires']=c.expires
            values.append(value)
        if values:self.context.add_cookies(values)

    def save_download(self, download, target):
        with output_lock(self.directory,self.deadline):
            self._save_download(download,target)

    def _save_download(self, download, target):
        self.check()
        path=self.artifacts.pop(download.url,None)
        if path is None or not path.is_file():
            raise DocumentBrowserFailure('Unverified document download denied.')
        # Atomic replacement, no partial destination on interrupted copying.
        target=Path(target).absolute()
        if target in self.written:
            raise DocumentBrowserFailure("Conflicting document identity.")
        backup=None
        if target.exists():
            backup=self.directory/("backup-"+str(len(self.written)))
            shutil.copyfile(target,backup)
        partial=target.parent/('.document-'+secrets.token_hex(16))
        self.output_journal.append(dict(target=str(target),backup=str(backup) if backup is not None else None,partial=str(partial)))
        raw=json.dumps(dict(version=1,files=self.output_journal))
        if len(self.output_journal)>128 or len(raw.encode())>1024*1024:raise DocumentBrowserFailure('Document output ownership bound exceeded.')
        journal=self.directory/'outputs.next';journal.write_text(raw);journal.replace(self.directory/'outputs.json')
        self.written[target]=backup
        fd=os.open(partial,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        try:
            with path.open('rb') as incoming,partial.open('wb') as outgoing:
                while chunk:=incoming.read(65536):
                    self.check();outgoing.write(chunk)
            self.check()
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
            path.unlink(missing_ok=True)


@contextmanager
def document_page(parent_page, session, origins):
    browser=parent_page.context.browser
    if browser is None:raise DocumentBrowserFailure('Dedicated browser context unavailable.')
    source=requests.Session();source.trust_env=False
    # Only explicitly allowlisted exact-domain/path cookies enter this context.
    allowed_hosts={destination(url)[1] for url in origins}
    transferred={}
    for c in session.cookies:
        try:destination('https://'+c.domain.lstrip('.')+(c.path or '/'))
        except DestinationDenied:continue
        if c.domain.startswith('.') or c.domain not in allowed_hosts:continue
        source.cookies.set_cookie(c)
        transferred[(c.name,c.domain,c.path)]=c
    parent_cookies=[]
    for c in parent_page.context.cookies():
        try:destination('https://'+c['domain'].lstrip('.')+c['path'])
        except DestinationDenied:continue
        if c['domain'].startswith('.') or c['domain'] not in allowed_hosts:continue
        parent_cookies.append(c)
        source.cookies.set(c['name'],c['value'],domain=c['domain'],path=c['path'],secure=c['secure'],expires=int(c['expires']) if c.get('expires',-1)>0 else None,rest={'HttpOnly':c.get('httpOnly',False),'SameSite':c.get('sameSite','Lax')})
    context=None;renderer=None;process_status=None
    try:
        with tempfile.TemporaryDirectory(prefix='propertyaigent-document-') as directory:
            try:
                with protected_browser(browser.browser_type,directory,remove_on_parent_loss=True) as (document_browser,process_status):
                    try:
                        context=document_browser.new_context(service_workers='block',offline=True,accept_downloads=True)
                        renderer=DocumentRenderer(context,source,directory)
                        document_browser.on('disconnected',lambda:renderer.deny('Document containment process disconnected.'))
                        context.route_web_socket('**/*',renderer.websocket)
                        def new_page(page):
                            if renderer.page is not None:
                                renderer.deny('Document popup denied.')
                                page.close()
                        context.on('page',new_page)
                        def failed_request(request):
                            if request.url not in renderer.verified_download_urls:
                                renderer.deny('Document browser request failed.')
                        context.on('requestfailed',failed_request)
                        page=context.new_page();renderer.page=page
                        page.on('worker',lambda _:renderer.deny('Document worker denied.'))
                        page.on('console',lambda message:renderer.deny('Document service worker denied.') if message.text=='Service Worker registration blocked by Playwright' else None)
                        client=context.new_cdp_session(page)
                        client.on('Log.entryAdded',lambda event:renderer.deny('Document security policy violation.') if event.get('entry',{}).get('source')=='security' else None)
                        client.send('Log.enable')
                        client.on('Network.webTransportCreated',lambda _:renderer.deny('Document WebTransport denied.'))
                        client.send('Network.enable')
                        def paused(event):
                            try:renderer.route(_PausedRoute(client,event))
                            except Exception as exc:
                                renderer.deny('Document interception failed: '+type(exc).__name__)
                                client.send('Fetch.failRequest',dict(requestId=event['requestId'],errorReason='BlockedByClient'))
                        client.on('Fetch.requestPaused',paused)
                        client.send('Fetch.enable',{'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
                        yield page,renderer
                        renderer.check()
                    finally:
                        if context is not None:
                            try:context.close()
                            except Exception:
                                if document_browser.is_connected():raise
                # Update only scopes originally transferred; unrelated cookies
                # and new domains never enter the discovery session/context.
                current={(c.name,c.domain,c.path):c for c in source.cookies}
                for key in transferred:
                    if key in current:session.cookies.set_cookie(current[key])
                    else:session.cookies.clear(domain=key[1],path=key[2],name=key[0])
                for original in parent_cookies:
                    key=(original['name'],original['domain'],original['path'])
                    c=current.get(key)
                    parent_page.context.clear_cookies(name=key[0],domain=key[1],path=key[2])
                    if c is not None:
                        value=dict(name=c.name,value=c.value,domain=c.domain,path=c.path,secure=c.secure,
                            httpOnly=('HttpOnly' in c._rest and c._rest['HttpOnly'] is not False))
                        if c.expires is not None:value['expires']=c.expires
                        same_site=c._rest.get('SameSite')
                        if same_site and same_site.capitalize() in ('Strict','Lax','None'):value['sameSite']=same_site.capitalize()
                        parent_page.context.add_cookies([value])
                process_status.finish_files(True)
            except BaseException as exc:
                if renderer is not None:
                    try:
                        with output_lock(renderer.directory,time.monotonic()+5):
                            if not renderer.directory.exists():raise FileNotFoundError()
                            for row in renderer.output_journal:Path(row['partial']).unlink(missing_ok=True)
                            for path,backup in renderer.written.items():
                                if backup is None:path.unlink(missing_ok=True)
                                else:shutil.copyfile(backup,path)
                    except FileNotFoundError:
                        receipt=process_status.wait_custodian() if process_status is not None else None
                        if receipt is None or receipt['state']!='rolled_back':raise DocumentBrowserFailure('Document rollback ownership lost.')
                if process_status is not None:process_status.finish_files(False)
                if isinstance(exc,Exception) and not isinstance(exc,DocumentBrowserFailure):
                    raise DocumentBrowserFailure('Document browser failed: '+type(exc).__name__) from exc
                raise
    finally:
        source.close()
        if process_status is not None:
            try:process_status.wait_custodian()
            except Exception as exc:raise DocumentBrowserFailure('Document file cleanup failed: '+type(exc).__name__) from exc
