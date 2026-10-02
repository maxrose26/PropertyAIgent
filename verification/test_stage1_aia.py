"""Synthetic certificate-chain repair; offline, real OpenSSL chain validation."""
import datetime
from pathlib import Path
import pytest,requests
from cryptography import x509
from cryptography.x509.oid import NameOID,AuthorityInformationAccessOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from app.scrapers import ssl_fix

@pytest.mark.parametrize('mode',['trusted-intermediate','untrusted-intermediate','self-signed-root','oversized'])
def test_aia_never_creates_new_trust_root(tmp_path,monkeypatch,mode):
    now=datetime.datetime.now(datetime.timezone.utc)
    rootkey=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuerkey=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    rootname=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic pretrusted root')])
    issuername=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic intermediate')])
    def certificate(subject,issuer,key,signer,ca=True):
        return x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=ca,path_length=None),critical=True).sign(signer,hashes.SHA256())
    root=certificate(rootname,rootname,rootkey,rootkey)
    roots=tmp_path/'pretrusted.pem';roots.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    signer=rootkey if mode=='trusted-intermediate' else issuerkey
    intermediate=certificate(issuername,rootname,issuerkey,signer)
    if mode=='self-signed-root':intermediate=root
    data=intermediate.public_bytes(serialization.Encoding.DER)
    if mode=='oversized':data=b'x'*(1024*1024+1)
    class Leaf:
        class Extensions:
            def get_extension_for_class(self,kind):
                from types import SimpleNamespace
                return SimpleNamespace(value=[x509.AccessDescription(AuthorityInformationAccessOID.CA_ISSUERS,x509.UniformResourceIdentifier('https://planning.bury.gov.uk/synthetic-ca.der'))])
        extensions=Extensions()
    class Response:
        def iter_content(self,*args):yield data
        def close(self):pass
    monkeypatch.setattr(ssl_fix,'_verify_bundle_cache',{})
    monkeypatch.setattr(ssl_fix.certifi,'where',lambda:str(roots))
    monkeypatch.setattr(ssl_fix.tempfile,'gettempdir',lambda:str(tmp_path))
    monkeypatch.setattr(ssl_fix.outbound.DocumentSession,'request',lambda *args,**kwargs:(_ for _ in ()).throw(requests.exceptions.SSLError('synthetic incomplete chain')))
    monkeypatch.setattr(ssl_fix,'_fetch_leaf_cert',lambda host:Leaf())
    fetched=[]
    def get(url,**kwargs):
        # Destination validation remains real; only HTTP body is a local fixture.
        ssl_fix.outbound.destination(url);fetched.append(url);return Response()
    monkeypatch.setattr(ssl_fix.outbound,'get',get)
    bundle=ssl_fix.get_verify_bundle_for_host('planning.bury.gov.uk')
    assert len(fetched)==1
    if mode=='trusted-intermediate':
        assert bundle!=str(roots)
        assert Path(bundle).read_bytes()==roots.read_bytes()+b'\n'+intermediate.public_bytes(serialization.Encoding.PEM)
    else:assert bundle==str(roots)
