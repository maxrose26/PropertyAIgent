"""Works around a real, confirmed server misconfiguration: some council
portals (Manchester's Arcus deployment confirmed) send only their own leaf
TLS certificate during the handshake, omitting the intermediate certificate
needed to build a trust chain up to a root CA - `openssl s_client -showcerts`
against arcusbe.manchester.gov.uk shows exactly this ("Verify return code: 21
(unable to verify the first certificate)"), and every single document
download for every Manchester scheme failed with
SSLCertVerificationError("unable to get local issuer certificate") as a
result. Browsers tolerate this by automatically fetching the missing
intermediate via the leaf certificate's own Authority Information Access
"CA Issuers" extension (a stable, standard PKI mechanism - not a browser
quirk); Python's requests/urllib3 doesn't do this automatically.

This is NOT a case for disabling verification (verify=False) - the site's
certificate chain IS genuinely valid, it's just incompletely served. Fetching
the same publicly-published intermediate a browser would and adding it to a
local trust bundle keeps verification real while working around the server's
own incomplete handshake.
"""
from __future__ import annotations

import socket
import ssl
import tempfile
from pathlib import Path

import certifi
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import AuthorityInformationAccessOID

_verify_bundle_cache: dict[str, str] = {}


def _fetch_leaf_cert(hostname: str, port: int = 443):
    ctx = ssl._create_unverified_context()
    with socket.create_connection((hostname, port), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
            der = ssock.getpeercert(binary_form=True)
    return x509.load_der_x509_certificate(der, default_backend())


def get_verify_bundle_for_host(hostname: str) -> str:
    """Returns a path suitable for requests' verify= kwarg - the standard
    certifi bundle for any normally-configured host (the common case,
    checked first and cached), or that bundle plus a fetched missing
    intermediate for a host whose own chain is incomplete."""
    if hostname in _verify_bundle_cache:
        return _verify_bundle_cache[hostname]

    try:
        requests.head(f"https://{hostname}", timeout=15, verify=certifi.where())
        _verify_bundle_cache[hostname] = certifi.where()
        return certifi.where()
    except requests.exceptions.SSLError:
        pass
    except requests.exceptions.RequestException:
        # Non-SSL failure (timeout, DNS, 404 on HEAD...) - not what this
        # function is for, fall back to the standard bundle rather than
        # masking an unrelated problem.
        _verify_bundle_cache[hostname] = certifi.where()
        return certifi.where()

    try:
        leaf = _fetch_leaf_cert(hostname)
        aia = leaf.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
        issuer_url = next(
            (d.access_location.value for d in aia.value if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS),
            None,
        )
        if not issuer_url:
            raise ValueError("certificate has no CA Issuers URL to fetch a missing intermediate from")

        intermediate_der = requests.get(issuer_url, timeout=15).content
        intermediate_cert = x509.load_der_x509_certificate(intermediate_der, default_backend())
        intermediate_pem = intermediate_cert.public_bytes(encoding=serialization.Encoding.PEM)

        combined = Path(tempfile.gettempdir()) / f"deal_finder_ca_bundle_{hostname}.pem"
        combined.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + intermediate_pem)
        print(f"    [ssl-fix] {hostname} sent an incomplete cert chain - fetched its missing intermediate from {issuer_url}")
        _verify_bundle_cache[hostname] = str(combined)
        return str(combined)
    except Exception as e:
        print(f"    [ssl-fix] could not work around {hostname}'s cert chain ({e}) - falling back to standard verification")
        _verify_bundle_cache[hostname] = certifi.where()
        return certifi.where()
