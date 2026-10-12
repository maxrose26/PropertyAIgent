"""Synthetic HTML and mocked Requests send; never council truth."""
from contextlib import contextmanager
import io
import socket
from unittest.mock import patch
import requests
from .recon import FORM_URL, POST_URLS

TOKEN='SYNTHETIC_STATE_DO_NOT_EXPORT_8675309'
FORM=f'''<html><body><form method="post" action="advancedSearchResults.do?action=firstPage">
<input type="hidden" name="_csrf" value="{TOKEN}"/>
<input name="date(applicationReceivedStart)" value=""/>
<input name="date(applicationReceivedEnd)" value=""/>
<input name="searchCriteria.reference" value=""/>
<select name="searchCriteria.status"><option value="">All</option></select>
<input type="submit" name="action" value="Search"/>
</form></body></html>'''.encode()
RESULT=b'''<html><body><p class="searchinfo">Showing 1 to 1 of 1 results</p>
<ul id="searchresults"><li class="searchresult"><a href="applicationDetails.do?activeTab=summary&amp;keyVal=SYNTH1">PRIVATE PROPOSAL NOT EXPORTED</a>
<p class="metaInfo">Ref. No: SYNTH/001 | Status: PRIVATE STATUS NOT EXPORTED</p></li></ul></body></html>'''
ZERO=b'<html><body><div id="searchresults"><p class="noResults">No results found.</p></div></body></html>'

class Raw(io.BytesIO):
    def read(self,amount=-1,decode_content=False):
        assert decode_content is False
        return super().read(amount)

@contextmanager
def offline_responses(responses=None):
    responses=list(responses if responses is not None else [(200,FORM,{}),(200,RESULT,{})])
    seen=[]; closed=[]
    def send(session,request,**kwargs):
        assert kwargs['stream'] is True and kwargs['allow_redirects'] is False and kwargs['timeout']==(3,8)
        assert request.url in {FORM_URL,*POST_URLS}
        seen.append(request)
        if not responses: raise AssertionError('unexpected additional physical request')
        response_spec=responses.pop(0)
        if isinstance(response_spec,Exception): raise response_spec
        status,body,headers=response_spec
        response=requests.Response(); response.status_code=status
        response.headers={'Content-Type':'text/html',**headers}
        response.raw=Raw(body); response.url=request.url; response.request=request
        close=response.close
        def finish():
            closed.append(True); close()
        response.close=finish
        return response
    def deny(*a,**kw): raise AssertionError('offline network denied')
    with patch.object(requests.Session,'send',send), patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'connect_ex',deny), \
         patch.object(socket,'create_connection',deny), patch.object(socket,'getaddrinfo',deny):
        yield seen,closed
