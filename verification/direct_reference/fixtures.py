"""Explicitly synthetic transport responses; never represent live compatibility."""
from html import escape
class Response:
    def __init__(self, url, body, status=200, headers=None):
        self.url, self.body, self.status_code = url, body, status
        self.headers = {'Content-Type':'text/html', **(headers or {})}
        self.history = []
        self.closed = False
    def iter_content(self, chunk_size):
        for i in range(0,len(self.body),chunk_size):
            yield self.body[i:i+chunk_size]
    def close(self): self.closed = True
class Session:
    def __init__(self, body, status=200, headers=None):
        self.body,self.status,self.headers=body,status,headers
        self.closed=False;self.responses=[];self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if isinstance(self.body, BaseException): raise self.body
        r=Response(url,self.body,self.status,self.headers);self.responses.append(r);return r
    def close(self): self.closed=True

def summary(reference, status='Awaiting decision', decision='', date='', omit=()):
    fields={'Reference':reference,'Status':status,'Decision':decision,'Decision Issued Date':date}
    return ('<html><body><table id="simpleDetailsTable">'+''.join(
        '<tr><th>'+escape(k)+'</th><td>'+escape(v)+'</td></tr>' for k,v in fields.items() if k not in omit
    )+'</table></body></html>').encode()
