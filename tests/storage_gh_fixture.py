"""Real gh, disposable HTTPS GitHub API shape; no real account or network route.

Only CLI transport/auth/public-key and protected-store boundaries differ.
Password/SCRAM values are never logged or written. PUT sees sealed ciphertext.
"""
import base64
from datetime import datetime, timedelta, timezone
import http.server
import ipaddress
import json
import os
import shutil
import ssl
import subprocess
import threading
from urllib.parse import urlsplit, unquote

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
from cryptography.x509.oid import NameOID
import pytest


@pytest.fixture
def real_gh_store(tmp_path):
    gh = shutil.which('gh')
    assert gh, 'Real Linux gh required'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'DISPOSABLE LOOPBACK ONLY')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .sign(key, hashes.SHA256()))
    pem=tmp_path/'fixture-ca.pem'; pk=tmp_path/'fixture-tls.key'; config=tmp_path/'gh-fixture-config'; config.mkdir()
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    pk.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    pub=x25519.X25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    ciphertexts={}; requests=[]
    names={'INGESTION_WORKER_DATABASE_URL','INGESTION_STORAGE_DATABASE_URL'}
    prefix='/repos/maxrose26/PropertyAIgent/environments/stage4-production-canary/secrets'
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
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
            name=path.removeprefix(prefix+'/')
            if name not in names:return self.answer(404,{'message':'DISPOSABLE_UNKNOWN_PATH'})
            if method=='PUT':
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<16384:return self.answer(400)
                payload=json.loads(self.rfile.read(size))
                if payload.get('key_id')!='disposable-key':return self.answer(400)
                encrypted=base64.b64decode(payload['encrypted_value'],validate=True)
                if len(encrypted)<80:return self.answer(400)
                ciphertexts[name]=encrypted
                return self.answer(201)
            if method=='DELETE' and name in ciphertexts:
                del ciphertexts[name];return self.answer(204)
            return self.answer(404)
        def do_GET(self):self.handle_request('GET')
        def do_PUT(self):self.handle_request('PUT')
        def do_DELETE(self):self.handle_request('DELETE')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(pem,pk)
    server.socket=ctx.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    host='127.0.0.1:%s'%server.server_port
    def cli(command,**kwargs):
        assert command[0]=='gh'
        env={**os.environ,'GH_HOST':host,'GH_ENTERPRISE_TOKEN':'disposable_fixture_only',
             'GH_TOKEN':'disposable_fixture_only','GH_CONFIG_DIR':str(config),
             'SSL_CERT_FILE':str(pem),'SSL_CERT_DIR':str(config),
             'GH_PROMPT_DISABLED':'1','GH_DEBUG':''}
        args=[gh,*command[1:]]
        # GH_HOST selects this isolated host:port. gh api's --hostname flag
        # validates DNS hostnames and rejects a disposable high-port address.
        if '--repo' in args:
            index=args.index('--repo')+1
            assert args[index]=='github.com/maxrose26/PropertyAIgent'
            args[index]='https://'+host+'/maxrose26/PropertyAIgent'
        # Input is inherited only in a pipe. Never inspect or retain plaintext.
        result=subprocess.run(args,input=kwargs.get('input'),stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,env=env,timeout=10,check=False)
        assert len(result.stdout)+len(result.stderr)<32768
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
            category='CERTIFICATE' if diagnostic['certificate_error'] else 'AUTH' if diagnostic['authentication_error'] else 'NOT_FOUND' if diagnostic['not_found'] else 'CONNECT' if diagnostic['connection_error'] else 'OTHER'
            raise Stop('GH_FIXTURE_'+category)
        return result
    def metadata(command,seconds=10):return cli(command).stdout
    def secret(operation,name,value):
        from verification.ingestion_storage import credential_mapping as mapping
        if operation=='set':mapping.put_secret(name,value,runner=cli)
        elif operation=='delete':cli(['gh','secret','delete',name,'--repo',mapping.REPO,'--env',mapping.ENVIRONMENT])
        elif operation=='verify_absent':
            assert not json.loads(cli(['gh','secret','list','--repo',mapping.REPO,'--env',mapping.ENVIRONMENT,'--json','name']).stdout)
        else:raise AssertionError('DISPOSABLE_UNKNOWN_OPERATION')
    try:yield metadata,secret,ciphertexts,requests
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
        assert not thread.is_alive()
