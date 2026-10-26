"""LABELLED LOCAL FIXTURE SERVER (not any council). Runs inside the proof namespace; loopback only.

* account.rochdale.gov.uk: a synthetic Arcus-shaped listing (FIXTURE rows) with the form-encoded POST the probe accounts for.
* publicaccess.tameside.gov.uk, planningpa.oldham.gov.uk: the existing reconstructed Idox bodies
  (tests.test_discovery_four_council_proof.bodies) in the reviewed request order: form, search, sort, refine.
"""
import http.server
import json
import ssl
import sys
import time
from pathlib import Path

work = Path(sys.argv[1])
rows = int(sys.argv[2])
from tests.test_discovery_four_council_proof import SCOPES, bodies   # noqa: E402

HOSTS = {'account.rochdale.gov.uk': 'rochdale', 'publicaccess.tameside.gov.uk': 'tameside', 'planningpa.oldham.gov.uk': 'oldham'}
sequences = {name: iter(bodies(next(s for s in SCOPES if s[0] == name))) for name in ('tameside', 'oldham')}
data = [(f'FIXTURE/2026/{i:04}', f'a1DSl00000{i:08}', '09/10/2026') for i in range(1, rows + 1)]
PAGE = """<!doctype html><meta charset=utf-8><title>FIXTURE (not Rochdale)</title>
<h1>FIXTURE listing - synthetic, local</h1>
<button type=button id=tgl>Show the search criteria</button>
<div id=criteria style="display:none">
<label for=f1>Valid date from</label><input id=f1 value="08/10/2026"><label for=f2>Valid date to</label><input id=f2 value="14/10/2026">
<label for=f3>Location of works</label><input id=f3 value=""><label for=f4>Description</label><input id=f4 value="">
<label for=f5>Decision notice was sent date from</label><input id=f5 value=""><label for=f6>Decision notice was sent date to</label><input id=f6 value="">
<button type=button role=combobox aria-label="Ward">Select an option</button><button type=button role=combobox aria-label="Application Status">Select an option</button>
<button type=button role=combobox aria-label="Application type">Select an option</button><button type=button role=combobox aria-label="Parish">Select an option</button>
<button type=button role=combobox aria-label="Category">Planning Applications</button></div>
<p class="pr-pagination__results" id=marker></p><div id=cards></div><a class="pr-pagination__link" id=next href="#">Next</a>
<script>const D=__DATA__;let page=0;
function aura(){fetch('/pr/s/sfsites/aura?fixture=1',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'message=%7B%22fixture%22%3Atrue%7D&aura.context=fixture'});}
function render(){const f=page*10,l=Math.min(D.length,f+10);document.getElementById('marker').textContent=`Showing ${f+1} to ${l} of ${D.length} results`;
 document.getElementById('cards').innerHTML=D.slice(f,l).map(r=>`<div role="list" class="slds-box"><a href="/pr/s/detail/${r[1]}?c__r=Arcus_BE_Public_Register">${r[0]}</a><div role="listitem"><div>Reference</div><div>${r[0]}</div></div><div role="listitem"><div>Valid Date</div><div>${r[2]}</div></div></div>`).join('');
 const n=document.getElementById('next');if(n&&l>=D.length)n.remove();}
document.getElementById('tgl').onclick=()=>{document.getElementById('criteria').style.display='block'};
document.getElementById('next').onclick=e=>{e.preventDefault();page++;aura();render()};aura();render();</script>"""
PAGE_BYTES = PAGE.replace('__DATA__', json.dumps(data)).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def log(self, kind):
        with open(work / 'server.log', 'a') as f:
            f.write(f"{round(time.time(), 2)} {self.command} {kind} {self.path.split('?')[0]}\n")

    def reply(self, code, body, content_type='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_any(self):
        kind = HOSTS.get(self.headers.get('Host', '').split(':')[0])
        self.log(kind or 'UNKNOWN_HOST')
        if self.command == 'POST':
            self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if kind == 'rochdale':
            return self.reply(200, b'{"actions":[]}', 'application/json') if self.command == 'POST' else self.reply(200, PAGE_BYTES)
        if kind in sequences:
            body = next(sequences[kind], None)
            return self.reply(200, body) if body is not None else self.reply(410, b'beyond the reviewed request sequence')
        self.reply(404, b'')

    do_GET = do_POST = do_HEAD = handle_any

    def log_message(self, *args):
        pass


context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(work / 'server.pem')
server = http.server.ThreadingHTTPServer(('127.0.0.1', 443), Handler)
server.socket = context.wrap_socket(server.socket, server_side=True)
print('fixture server ready', flush=True)
server.serve_forever()
