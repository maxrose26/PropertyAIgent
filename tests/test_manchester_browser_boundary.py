"""Offline production probe path: first-request browser failure, no HTTP transport."""
import asyncio,json
import pytest
from types import SimpleNamespace
from playwright.async_api import Error,TimeoutError
from verification.direct_reference import instrumented_probe as p

@pytest.mark.parametrize('message,expected',[
 ('page.goto: net::ERR_NAME_NOT_RESOLVED at https://private/?token=SECRET','ERR_NAME_NOT_RESOLVED'),
 ('net::ERR_CERT_AUTHORITY_INVALID cookie=SECRET','ERR_CERT_AUTHORITY_INVALID'),
 ('net::ERR_CONNECTION_RESET','ERR_CONNECTION_RESET'),
 ('net::ERR_NOT_REVIEWED secret','UNKNOWN'),
 ('net::ERR_CONNECTION_RESET net::ERR_TIMED_OUT','UNKNOWN'),
 ('SECRET','UNKNOWN'),
 ('net::ERR_CONNECTION_RESET_SUFFIX','UNKNOWN')])
def test_fixed_nonsecret_tokens(message,expected):
 assert p.network_error_code(message)==expected
 assert 'SECRET' not in json.dumps(p.browser_diagnostic(Error(message),'INITIAL_NAVIGATION'))

@pytest.mark.parametrize('error',[Error('net::ERR_NAME_NOT_RESOLVED https://private/?token=SECRET'),Error('net::ERR_CONNECTION_RESET SECRET'),TimeoutError('SECRET')])
def test_actual_probe_first_request_refuses_and_closes(monkeypatch,error):
 calls=[];handlers={};context_handlers={};closed=[]
 class Client:
  def on(self,k,fn):handlers[k]=fn
  async def send(self,k,args=None):calls.append(k)
 class Page:
  def on(self,*args):pass
  async def goto(self,url,**kw):
   await handlers['Fetch.requestPaused'](dict(requestId='PRIVATE_ID',resourceType='Document',request=dict(url=url,method='GET',headers={})))
   raise error
 class Context:
  async def route_web_socket(self,*args):pass
  def on(self,k,fn):context_handlers[k]=fn
  async def new_page(self):context_handlers['page'](None);return Page()
  async def new_cdp_session(self,page):return Client()
  async def close(self):closed.append('context')
 class Browser:
  async def new_context(self,**kw):return Context()
  async def close(self):closed.append('browser')
 class Chromium:
  async def launch(self,**kw):return Browser()
 class Playwright:
  async def __aenter__(self):return SimpleNamespace(chromium=Chromium())
  async def __aexit__(self,*args):pass
 monkeypatch.setattr('playwright.async_api.async_playwright',Playwright)
 result=asyncio.run(p.probe('discovery_manchester_ui_window',('2026-10-27','2026-11-02')))
 assert result['failure']=='BROWSER_'+type(error).__name__ and result['safety_failure'] is True
 assert result['requests']==1 and result['responses']==0 and result['pages']==1
 assert result['browser_diagnostic']['stage']=='INITIAL_NAVIGATION'
 assert result['browser_diagnostic']['exception_class']==type(error).__name__
 assert calls.count('Fetch.continueRequest')==1 and closed==['context','browser']
 assert 'SECRET' not in json.dumps(result) and 'PRIVATE_ID' not in json.dumps(result)
 assert result['cleanup']=='CONTEXT_BROWSER_CLOSED'
