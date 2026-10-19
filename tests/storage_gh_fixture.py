"""Real gh, disposable HTTPS GitHub API shape; no real account or network route.

Only CLI transport/auth/public-key and protected-store boundaries differ.
Password/SCRAM values are never logged or written. PUT sees sealed ciphertext.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
import http.server
import ipaddress
import json
import os
import shutil
import select
import socket
import ssl
import subprocess
import threading
from urllib.parse import urlsplit, unquote,parse_qs

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
from cryptography.x509.oid import NameOID
import pytest


@pytest.fixture
def real_gh_store(tmp_path,request):
    gh = shutil.which('gh')
    assert gh, 'Real Linux gh required'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'DISPOSABLE LOOPBACK ONLY')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('storage-fixture.invalid')]), False)
            .sign(key, hashes.SHA256()))
    pem=tmp_path/'fixture-ca.pem'; pk=tmp_path/'fixture-tls.key'; config=tmp_path/'gh-fixture-config'; config.mkdir()
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    pk.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    pub=x25519.X25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    operational=getattr(request,'param',None)=='operational'
    ciphertexts={'DATABASE_URL':b'disposable-preserved'} if operational else {}; requests=[]
    names={'INGESTION_WORKER_DATABASE_URL','INGESTION_STORAGE_DATABASE_URL'}
    if operational:names|={'INGESTION_EFFECT_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL'}
    git_objects={};git_head=['1'*40]
    prefix='/repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets'
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def git_body(self):
            if self.headers.get('Transfer-Encoding','').lower()!='chunked':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<3*1024**2:raise ValueError('FIXTURE_BODY_BOUND')
                return self.rfile.read(n)
            body=bytearray()
            for _ in range(4096):
                n=int(self.rfile.readline(80).strip(),16)
                if n==0:
                    if self.rfile.readline(3)!=b'\r\n':raise ValueError('FIXTURE_CHUNK')
                    return bytes(body)
                if n<0 or len(body)+n>=3*1024**2:raise ValueError('FIXTURE_BODY_BOUND')
                body.extend(self.rfile.read(n))
                if self.rfile.read(2)!=b'\r\n':raise ValueError('FIXTURE_CHUNK')
            raise ValueError('FIXTURE_CHUNK_BOUND')
        def answer(self,status,value=None):
            body=b'' if value is None else json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def handle_request(self,method):
            path=unquote(urlsplit(self.path).path)
            if path.startswith('/api/v3'):path=path[7:]
            requests.append((method,path))
            if method=='GET' and path=='/user':return self.answer(200,{'login':'maxrose26'})
            if method=='GET' and path==prefix+'/public-key':return self.answer(200,{'key_id':'disposable-key','key':base64.b64encode(pub).decode()})
            if method=='GET' and path==prefix:return self.answer(200,{'total_count':len(ciphertexts),'secrets':[{'name':n} for n in sorted(ciphertexts)]})
            contents='/repos/maxrose26/PropertyAIgent/contents/'
            if operational and method=='GET' and path.startswith(contents):
                revision=parse_qs(urlsplit(self.path).query)['ref'][0]
                tree=git_objects[git_objects[revision]['tree']['sha']]['tree']
                entry=next((x for x in tree if x['path']==path[len(contents):]),None)
                if entry is None:return self.answer(404,{'message':'Not Found'})
                return self.answer(200,git_objects[entry['sha']])
            git_prefix='/repos/maxrose26/PropertyAIgent/git/'
            if operational and path.startswith(git_prefix):
                target=path[len(git_prefix):]
                if method=='GET' and target.startswith('ref/heads/'):return self.answer(200,{'object':{'sha':git_head[0]}})
                if method=='GET' and target=='commits/'+'1'*40:return self.answer(200,{'tree':{'sha':'2'*40}})
                if method=='GET' and target.startswith('blobs/'):
                    value=git_objects.get(target[6:]);return self.answer(200,value) if value else self.answer(404)
                if method=='GET' and target.startswith('commits/'):
                    value=git_objects.get(target[8:]);return self.answer(200,value) if value else self.answer(404)
                if method in ('POST','PATCH'):
                    value=json.loads(self.git_body())
                    if target=='blobs':
                        raw=base64.b64decode(value['content']);sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                    else:sha=hashlib.sha1(json.dumps(value,sort_keys=True).encode()).hexdigest()
                    if target.startswith('refs/heads/'):
                        if value.get('force') is not False or git_objects[value['sha']]['parents']!=[git_head[0]]:return self.answer(409)
                        git_head[0]=value['sha'];return self.answer(200,{'object':{'sha':git_head[0]}})
                    if target=='trees':      # as on the real API a tree built on a base_tree contains the base tree's entries plus (or replacing) the new ones
                        base=git_objects.get(value.get('base_tree'));merged={x['path']:x for x in (base['tree'] if base else [])};merged.update({x['path']:x for x in value['tree']});value=dict(value,tree=list(merged.values()))
                    git_objects[sha]=dict(value,sha=sha)
                    if target=='commits':git_objects[sha]['tree']={'sha':value['tree']}
                    return self.answer(201,{'sha':sha})
                return self.answer(404)
            name=path.removeprefix(prefix+'/')
            if name not in names:return self.answer(404,{'message':'DISPOSABLE_UNKNOWN_PATH'})
            if method=='PUT':
                if self.headers.get('Transfer-Encoding','').lower()=='chunked':
                    body=bytearray()
                    for _ in range(32):
                        line=self.rfile.readline(80)
                        size=int(line.strip(),16)
                        if size==0:
                            if self.rfile.readline(3)!=b'\r\n':return self.answer(400)
                            break
                        if size<0 or len(body)+size>=16384:return self.answer(400)
                        body.extend(self.rfile.read(size))
                        if self.rfile.read(2)!=b'\r\n':return self.answer(400)
                    else:return self.answer(400)
                else:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<16384:
                        requests.append(('BAD_LENGTH',prefix));return self.answer(400)
                    body=self.rfile.read(size)
                payload=json.loads(body)
                if payload.get('key_id')!='disposable-key':
                    requests.append(('BAD_KEY_ID',prefix));return self.answer(400)
                encrypted=base64.b64decode(payload['encrypted_value'],validate=True)
                if len(encrypted)<80:
                    requests.append(('BAD_CIPHERTEXT_LENGTH',prefix));return self.answer(400)
                ciphertexts[name]=encrypted
                return self.answer(201,{})
            if method=='DELETE' and name in ciphertexts:
                del ciphertexts[name];return self.answer(204)
            return self.answer(404)
        def do_GET(self):self.handle_request('GET')
        def do_PUT(self):self.handle_request('PUT')
        def do_DELETE(self):self.handle_request('DELETE')
        def do_POST(self):self.handle_request('POST')
        def do_PATCH(self):self.handle_request('PATCH')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(pem,pk)
    server.socket=ctx.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    # gh's repository parser intentionally removes a URL port. A fixed-name
    # CONNECT proxy routes every permitted CLI request to this loopback TLS
    # fixture without DNS, external network access or privileged port binding.
    host='storage-fixture.invalid'
    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_CONNECT(self):
            if self.path != host+':443':
                self.send_error(403);return
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as upstream:
                upstream.settimeout(10)
                upstream.connect(('127.0.0.1',server.server_port))
                self.send_response(200);self.end_headers()
                sockets=[self.connection,upstream]
                while True:
                    ready,_,_=select.select(sockets,[],[],10)
                    if not ready:return
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (upstream if source is self.connection else self.connection).sendall(data)
    proxy=http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy)
    proxy.daemon_threads=True
    proxy_thread=threading.Thread(target=proxy.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    proxy_thread.start()
    def fixture_env():
        return {**os.environ,'GH_HOST':host,'GH_ENTERPRISE_TOKEN':'disposable_fixture_only',
             'GH_TOKEN':'disposable_fixture_only','GH_CONFIG_DIR':str(config),
             'SSL_CERT_FILE':str(pem),'SSL_CERT_DIR':str(config),
             'GH_PROMPT_DISABLED':'1','GH_DEBUG':'',
             'HTTPS_PROXY':'http://127.0.0.1:%s'%proxy.server_port,
             'https_proxy':'http://127.0.0.1:%s'%proxy.server_port,
             'NO_PROXY':'','no_proxy':''}
    def cli(command,**kwargs):
        assert command[0]=='gh'
        env=fixture_env()
        args=[gh,*command[1:]]
        # Both API and explicit repository routes must use the fixed fixture.
        if '--repo' in args:
            index=args.index('--repo')+1
            assert args[index]=='github.com/maxrose26/PropertyAIgent'
            args[index]='https://'+host+'/maxrose26/PropertyAIgent'
        # Input is inherited only in a pipe. Never inspect or retain plaintext.
        result=subprocess.run(args,input=kwargs.get('input'),stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,env=env,timeout=10,check=False)
        assert len(result.stdout)+len(result.stderr)<(3*1024**2 if operational else 32768)
        if result.returncode:
            # Fixture-only diagnostic categories; no raw CLI output or values.
            import hashlib
            text=result.stderr.lower()
            diagnostic=dict(exit=result.returncode,command=command[1:3],
                certificate_error=b'certificate' in text,
                authentication_error=b'auth' in text,
                not_found=b'404' in text,connection_error=b'connect' in text,
                stderr_sha256=hashlib.sha256(result.stderr).hexdigest())
            from verification.ingestion_storage.storage_controller import Stop
            category='FILE_SIZE' if b'file too large' in text or b'file size' in text else 'EOF' if b'eof' in text else 'HTTP_BAD_REQUEST' if b'400' in text else 'EXIT_SIGNAL' if result.returncode<0 else 'CERTIFICATE' if diagnostic['certificate_error'] else 'AUTH' if diagnostic['authentication_error'] else 'NOT_FOUND' if diagnostic['not_found'] else 'CONNECT' if diagnostic['connection_error'] else 'OTHER'
            raise Stop('GH_FIXTURE_'+category)
        return result
    def metadata(command,seconds=10):return cli(command).stdout
    metadata.cli=cli;metadata.fixture_env=fixture_env;metadata.gh=gh
    def secret(operation,name,value):
        from verification.ingestion_storage import credential_mapping as mapping
        if operation=='set':mapping.put_secret(name,value,runner=cli)
        elif operation=='delete':cli(['gh','secret','delete',name,'--repo',mapping.REPO,'--env',mapping.ENVIRONMENT])
        elif operation=='verify_absent':
            assert not json.loads(cli(['gh','secret','list','--repo',mapping.REPO,'--env',mapping.ENVIRONMENT,'--json','name']).stdout)
        else:raise AssertionError('DISPOSABLE_UNKNOWN_OPERATION')
    try:
        assert cli(['gh','api','user','--jq','.login']).stdout.strip()==b'maxrose26'
        yield metadata,secret,ciphertexts,requests
    finally:
        proxy.shutdown();proxy.server_close();proxy_thread.join(timeout=2)
        assert not proxy_thread.is_alive()
        server.shutdown();server.server_close();thread.join(timeout=2)
        assert not thread.is_alive()
