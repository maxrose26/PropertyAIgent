"""TEST-ONLY entry for the credential-free source child. DISPOSABLE LOOPBACK ONLY: it is `operational_source.main` (the production worker, unchanged) with ONE substitution - the HTTPS adapter of the requests
session sends to a loopback fixture server instead of the council - so the real supervisor, the real worker, the real window runner, the real boundary and the real `requests` stack all run. Nothing here
exists in production."""
import sys
from urllib.parse import urlsplit

index=sys.argv.index('--loopback-port')
port=int(sys.argv[index+1]);del sys.argv[index:index+2]
if not 1024<=port<=65535:raise SystemExit('LOOPBACK_ONLY')
import requests.adapters
_send=requests.adapters.HTTPAdapter.send


def send(self,request,**kwargs):
    parts=urlsplit(request.url)
    if parts.scheme!='https':raise SystemExit('UNEXPECTED_SCHEME')
    request.headers['X-Original-Host']=parts.netloc
    request.url='http://127.0.0.1:%d%s%s'%(port,parts.path,'?'+parts.query if parts.query else '')
    return _send(self,request,**kwargs)


requests.adapters.HTTPAdapter.send=send
from verification.ingestion_storage import operational_source
operational_source.main()
