"""Offline destination/binding checks using recording transports, never DNS."""
import socket
import pytest
import requests
from urllib3 import exceptions as u3
from app.security import outbound

@pytest.mark.parametrize('url',[
'http://planning.bury.gov.uk/a','https://127.0.0.1/a','https://[::1]/a','https://planning.bury.gov.uk:444/a','https://u:p@planning.bury.gov.uk/a','https://planning.bury.gov.uk/a#fragment','file:///etc/passwd','https://planning.bury.gov.uk.evil.invalid/a','https://planning.bury.gov.uk\\@evil.invalid/a','https://tcintunestorage01.blob.core.windows.net/other/a','https://tcintunestorage01.blob.core.windows.net/tc-drupal-repo/../other/a','https://tcintunestorage01.blob.core.windows.net/tc-drupal-repo/%252e%252e/other/a'])
def test_bad_destinations_before_dns(monkeypatch,url):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:pytest.fail('DNS called before destination denial'))
    with pytest.raises(outbound.DestinationDenied):outbound.destination(url)

@pytest.mark.parametrize('url',[
'https://planning.stockport.gov.uk/PlanningData-live/applicationDetails.do?activeTab=documents',
'https://planning.bury.gov.uk/online-applications/applicationDetails.do',
'https://pad-planning.bury.gov.uk/a',
'https://live-iag-static-assets.s3.eu-west-1.amazonaws.com/pdf/Local+Plan+evidence/LocalPlan.pdf',
'https://tcintunestorage01.blob.core.windows.net/tc-drupal-repo/report.pdf'])
def test_legitimate_configured_origins(url):assert outbound.destination(url)[1]

@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','0.0.0.0','224.0.0.1','::1','fc00::1','fe80::1','::ffff:127.0.0.1'])
def test_any_private_dns_answer_denies(monkeypatch,address):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET6,socket.SOCK_STREAM,6,'',(address,443))])
    with pytest.raises(outbound.DestinationDenied):outbound.resolved_addresses('planning.bury.gov.uk',443)

def test_bound_ip_sni_verify_and_no_redirect_or_retry(monkeypatch):
    calls=[]
    class Pool:
        def __init__(self,**kwargs):calls.append(kwargs)
        def urlopen(self,*args,**kwargs):calls.append((args,kwargs));return object()
        def close(self):pass
    monkeypatch.setattr(outbound,'HTTPSConnectionPool',Pool)
    monkeypatch.setattr(outbound,'resolved_addresses',lambda *a:['8.8.8.8'])
    adapter=outbound.BoundAdapter();response=requests.Response();monkeypatch.setattr(adapter,'build_response',lambda *a:response)
    request=requests.Request('GET','https://planning.bury.gov.uk/doc').prepare()
    adapter.send(request,timeout=(2,3))
    assert calls[0]['host']=='8.8.8.8';assert calls[0]['server_hostname']==calls[0]['assert_hostname']=='planning.bury.gov.uk'
    assert calls[0]['cert_reqs']=='CERT_REQUIRED'
    assert calls[1][1]['redirect'] is False and calls[1][1]['retries'] is False
    assert calls[1][1]['headers']['Host']=='planning.bury.gov.uk'
    assert calls[1][1]['timeout'].connect_timeout==2
    assert calls[1][1]['timeout'].read_timeout==3

def test_existing_retry_exception_contract(monkeypatch):
    class Pool:
        def __init__(self,**kwargs):pass
        def urlopen(self,*args,**kwargs):raise u3.NewConnectionError(None,'fixture')
        def close(self):pass
    monkeypatch.setattr(outbound,'HTTPSConnectionPool',Pool);monkeypatch.setattr(outbound,'resolved_addresses',lambda *a:['8.8.8.8'])
    with pytest.raises(requests.ConnectionError):outbound.BoundAdapter().send(requests.Request('GET','https://planning.bury.gov.uk/doc').prepare())

def test_private_redirect_denied_before_second_send(monkeypatch):
    sent=[]
    def send(self,request,**kwargs):
        sent.append(request.url);response=requests.Response();response.status_code=302;response.headers['Location']='https://127.0.0.1/private';response._content=b'';response.request=request;return response
    monkeypatch.setattr(outbound.BoundAdapter,'send',send)
    with pytest.raises(outbound.DestinationDenied):outbound.get('https://planning.bury.gov.uk/doc')
    assert sent==['https://planning.bury.gov.uk/doc']


def test_redirects_share_one_overall_deadline(monkeypatch):
    deadlines=[];sent=[]
    original=outbound.BoundAdapter.__init__
    def init(self,*,deadline=None):
        deadlines.append(deadline);original(self,deadline=deadline)
    def send(self,request,**kwargs):
        sent.append(request.url);response=requests.Response();response.status_code=302 if len(sent)==1 else 200;response.headers['Location']='/done';response._content=b'';response._content_consumed=True;response.request=request;return response
    monkeypatch.setattr(outbound.BoundAdapter,'__init__',init);monkeypatch.setattr(outbound.BoundAdapter,'send',send)
    outbound.get('https://planning.bury.gov.uk/start')
    assert len(sent)==2 and len(deadlines)==4 and len(set(deadlines))==1 and deadlines[0] is not None
