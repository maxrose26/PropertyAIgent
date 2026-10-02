"""Document-only verified, IP-bound transport. No proxy or resolver fallback."""
from contextlib import contextmanager
import ipaddress
import json
from pathlib import Path
import socket
import time
import threading
from urllib.parse import urljoin, urlsplit, unquote
import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPSConnectionPool, HTTPConnectionPool
from urllib3.util import Timeout
from urllib3 import exceptions as u3_errors
from urllib3.connection import HTTPConnection, HTTPSConnection


class DestinationDenied(requests.RequestException):
    pass


def destination(url):
    try:
        if not isinstance(url,str) or any(ord(c) < 33 for c in url) or '\\' in url:
            raise ValueError()
        parsed=urlsplit(url)
        if parsed.username is not None or parsed.password is not None or parsed.fragment or not parsed.hostname:
            raise ValueError()
        host=parsed.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        try: ipaddress.ip_address(host)
        except ValueError: pass
        else: raise DestinationDenied('Document destination denied.')
        if parsed.scheme not in ('https','http') or parsed.port not in (None,443 if parsed.scheme=='https' else 80):
            raise ValueError()
        policy=json.loads((Path(__file__).resolve().parents[2]/'config/document_origins.json').read_text())
        prefixes=policy[parsed.scheme].get(host,[])
        decoded=unquote(parsed.path or '/')
        if '%' in decoded or any(part in ('.','..') for part in decoded.split('/')) or '\\' in decoded or not any(decoded.startswith(prefix) for prefix in prefixes):
            raise ValueError()
        return parsed,host,443 if parsed.scheme=='https' else 80
    except (ValueError,KeyError,TypeError,OSError,UnicodeError):
        raise DestinationDenied('Document destination denied.') from None


def resolved_addresses(host,port):
    candidates=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(item[4][0] for item in candidates))
    if not addresses: raise DestinationDenied('Document destination denied.')
    for address in addresses:
        ip=ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip,'ipv4_mapped',None):
            raise DestinationDenied('Document destination denied.')
    return addresses


class BoundAdapter(HTTPAdapter):
    def __init__(self, *, deadline=None):
        super().__init__()
        self.deadline=deadline

    def send(self,request,stream=False,timeout=None,verify=True,cert=None,proxies=None):
        if verify is False or cert or proxies:
            raise DestinationDenied('Unsupported document transport configuration.')
        deadline=self.deadline if self.deadline is not None else time.monotonic()+300
        if time.monotonic()>=deadline:raise requests.Timeout('Document deadline exceeded.')
        parsed,host,port=destination(request.url)
        address=resolved_addresses(host,port)[0]
        options=dict(host=address,port=port,maxsize=1,block=True)
        if parsed.scheme=='https':
            options.update(cert_reqs='CERT_REQUIRED',ca_certs=verify if isinstance(verify,str) else certifi.where(),assert_hostname=host,server_hostname=host)
        pool=(HTTPSConnectionPool if parsed.scheme=='https' else HTTPConnectionPool)(**options)
        # A socket deadline also interrupts a slow-drip header/body while a
        # chunk read is still blocked; per-read inactivity timeouts cannot.
        base=HTTPSConnection if parsed.scheme=='https' else HTTPConnection
        deadline_timers=[]
        def close_pool():
            for timer in deadline_timers:timer.cancel()
            pool.close()
        class DeadlineConnection(base):
            _deadline_timer=None
            def connect(self):
                super().connect()
                connected_socket=self.sock
                def interrupt():
                    try: connected_socket.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                self._deadline_timer=threading.Timer(max(0,deadline-time.monotonic()),interrupt)
                self._deadline_timer.daemon=True
                deadline_timers.append(self._deadline_timer)
                self._deadline_timer.start()
            # urllib3 may detach/close its connection after HTTP/1.0 headers
            # while the response still owns a live socket file. Cancel only
            # when the response/pool is released, not on that early detach.
        pool.ConnectionCls=DeadlineConnection
        headers=dict(request.headers)
        headers['Host']=host
        headers.pop('Authorization',None);headers.pop('Proxy-Authorization',None)
        if isinstance(timeout,tuple): timeout=Timeout(connect=timeout[0],read=timeout[1])
        elif isinstance(timeout,(int,float)): timeout=Timeout(connect=timeout,read=timeout)
        else: timeout=Timeout(connect=15,read=60)
        try:
            raw=pool.urlopen(request.method,parsed.path+('?' + parsed.query if parsed.query else ''),body=request.body,headers=headers,redirect=False,retries=False,preload_content=False,timeout=timeout)
            response=self.build_response(request,raw)
            def raise_for_status():
                if 400 <= response.status_code < 600:
                    raise requests.HTTPError(f'Document HTTP status {response.status_code}.',response=response)
            response.raise_for_status=raise_for_status
            original_close=response.close
            def close():
                try: original_close()
                finally: close_pool()
            response.close=close
            return response
        except u3_errors.ConnectTimeoutError as exc:
            close_pool()
            raise requests.ConnectTimeout('Document connection timed out.') from None
        except u3_errors.ReadTimeoutError as exc:
            close_pool()
            raise requests.ReadTimeout('Document read timed out.') from None
        except u3_errors.SSLError as exc:
            close_pool()
            raise requests.exceptions.SSLError('Document TLS verification failed.') from None
        except u3_errors.HTTPError as exc:
            close_pool()
            raise requests.ConnectionError('Document connection failed.') from None
        except Exception:
            close_pool()
            raise


class DocumentSession:
    """Small GET adapter accepted by the unchanged portal retry function."""
    def __init__(self,source=None):
        self.source=source
        self.cookies=requests.cookies.RequestsCookieJar()

    def get(self,url,*,stream=False,timeout=30,headers=None,verify=True,**kwargs):
        return self.request('GET',url,stream=stream,timeout=timeout,headers=headers,verify=verify,**kwargs)

    def request(self,method,url,*,stream=False,timeout=30,headers=None,verify=True,data=None,deadline=None,**kwargs):
        if method not in ('GET','POST','HEAD'):
            raise DestinationDenied('Unsupported document method.')
        if kwargs.keys()-{'allow_redirects'}:
            raise DestinationDenied('Unsupported document request options.')
        follow_redirects=kwargs.get('allow_redirects',True)
        visited=set();initial=destination(url)[1];deadline=min(deadline,time.monotonic()+300) if deadline is not None else time.monotonic()+300
        for hop in range(6):
            parsed,host,port=destination(url)
            if url in visited: raise DestinationDenied('Document redirect denied.')
            visited.add(url)
            client=requests.Session();client.trust_env=False
            client.mount('https://',BoundAdapter(deadline=deadline));client.mount('http://',BoundAdapter(deadline=deadline))
            safe_headers={k:v for k,v in (headers or {}).items() if k.lower() in ('user-agent','accept','accept-language','content-type')}
            referer=(headers or {}).get('Referer')
            if referer and destination(referer)[1] == host == initial:
                safe_headers['Referer']=referer
            if host==initial and self.source is not None:
                for cookie in self.source.cookies:
                    # Exact destination domain only: no cross-origin suffix cookies.
                    if cookie.domain.lstrip('.')==host:
                        client.cookies.set_cookie(cookie)
            for cookie in self.cookies:
                if cookie.domain.lstrip('.')==host: client.cookies.set_cookie(cookie)
            initial_cookie_keys={(c.name,c.domain,c.path) for c in client.cookies}
            try:
                if time.monotonic() >= deadline: raise requests.Timeout('Document deadline exceeded.')
                response=client.request(method,url,data=data,stream=True,timeout=timeout,headers=safe_headers,verify=verify,allow_redirects=False)
            except BaseException:
                client.close()
                raise
            current_cookie_keys={(c.name,c.domain,c.path) for c in client.cookies}
            for name,domain,path in initial_cookie_keys-current_cookie_keys:
                for jar in (self.cookies, self.source.cookies if self.source is not None else None):
                    if jar is not None:
                        try:jar.clear(domain=domain,path=path,name=name)
                        except KeyError:pass
            for cookie in client.cookies:
                if cookie.domain.lstrip('.')==host:
                    self.cookies.set_cookie(cookie)
                    if self.source is not None: self.source.cookies.set_cookie(cookie)
            if follow_redirects and response.status_code in (301,302,303,307,308):
                target=urljoin(url,response.headers.get('Location',''))
                if response.status_code == 303 or (response.status_code in (301,302) and method=='POST'):
                    method='GET';data=None
                elif urlsplit(target).hostname != host and data is not None:
                    response.close();client.close()
                    raise DestinationDenied('Cross-origin request body denied.')
                response.close();client.close()
                if not target or (parsed.scheme=='https' and urlsplit(target).scheme!='https') or hop==5:
                    raise DestinationDenied('Document redirect denied.')
                url=target;continue
            close=response.close
            def close_all(close=close,client=client):
                try: close()
                finally: client.close()
            response.close=close_all
            original_iter=response.iter_content
            def bounded_iter(*args,original_iter=original_iter,**kwargs):
                for chunk in original_iter(*args,**kwargs):
                    if time.monotonic() >= deadline:
                        raise requests.Timeout('Document deadline exceeded.')
                    yield chunk
            response.iter_content=bounded_iter
            if not stream:
                try:
                    body=bytearray()
                    for chunk in response.iter_content(65536):
                        body.extend(chunk)
                        if len(body)>20*1024*1024: raise DestinationDenied('Document listing too large.')
                    response._content=bytes(body);response._content_consumed=True
                finally: response.close()
            return response
        raise DestinationDenied('Document redirect denied.')


def get(url,**kwargs):
    return DocumentSession().get(url,**kwargs)
