"""Bounded shape-only failure diagnostics. No values, URLs, HTML or exceptions."""
import hashlib
import re
from bs4 import BeautifulSoup

STAGES={'DESTINATION','REQUEST','HEADERS','BODY','DECODE','STRUCTURE','SUMMARY_PARSE',
        'EXACT_REFERENCE','OBSERVATION','FORM_PARSE','ZERO_CHECK','SORT_FORM_PARSE',
        'SORT_VERIFY','PAGE_PARSE','CRITERIA_ECHO','UNKNOWN',
        'FORM_REQUEST','SEARCH_REQUEST','SORT_REQUEST','PAGE_REQUEST','REFINE_REQUEST'}
CODES={'PARSER_FAILURE','PARTIAL_RETRIEVAL','AMBIGUOUS_SOURCE_RESULT','TIMEOUT',
       'SOURCE_UNAVAILABLE','RATE_LIMITED','SOURCE_CONTRACT_REJECTED','UNCLASSIFIED_FAILURE',
       'SORT_SELECTOR_COUNT','DUPLICATE_REFERENCE','UNKNOWN'}
COUNTS={'summary_tables','reference_labels','status_labels','decision_labels','decision_date_labels',
        'order_by_selects','forms'}


OUTCOMES=frozenset({'PARTIAL_RETRIEVAL','SOURCE_UNAVAILABLE','RATE_LIMITED','TIMEOUT','AMBIGUOUS_SOURCE_RESULT','REFERENCE_NOT_FOUND','FORM_REJECTED','LAYOUT_UNRECOGNISED','BUDGET_EXCEEDED'})
REASONS=frozenset({'HTTP failure','HTTP rate limit','transport failed','transient upstream response','response shape','document response rejected','closed transport','closed','origin rejected','noncanonical route',
                   'unapproved route class','unapproved form action','unapproved form field','method rejected','search expansion rejected','POST query rejected','exact reference required','window request not admitted',
                   'redirect ceiling','missing redirect location','request ceiling','request payload ceiling','response byte ceiling','run deadline','run-local host circuit open','unqualified transport failure',
                   'parser body bound','unqualified source encoding','discovery/document route rejected','additional search criterion rejected','no exact result','multiple plausible exact results'})
MEDIA=frozenset({'text/html','application/xhtml+xml','text/plain','application/json','application/xml','text/xml','OTHER'})
REDIRECTS=frozenset({'NONE','SAME_ORIGIN','OTHER_ORIGIN','MISSING_LOCATION'})
TRANSPORT_KEYS=frozenset({'http_status','media_type','redirect','rejection_outcome','rejection_reason'})


def response_shape(response,url,base_url):
    """Bounded, non-sensitive facts about one response: the integer status, the media type only if it is on a fixed allow-list, and whether (not where) it redirects. Never a header value, URL, cookie or
    body. Failure to observe any of it yields None for that field; it never raises."""
    from urllib.parse import urljoin,urlsplit
    out=dict(http_status=None,media_type=None,redirect=None)
    try:
        status=response.status_code
        if type(status) is int and 100<=status<=599:out['http_status']=status
    except Exception:pass
    try:
        media=response.headers.get('Content-Type','').split(';')[0].strip().lower()
        out['media_type']=media if media in MEDIA else ('OTHER' if media else None)
    except Exception:pass
    try:
        status=out['http_status']
        if status is not None:
            if 300<=status<400:
                location=response.headers.get('Location','')
                if not location:out['redirect']='MISSING_LOCATION'
                else:
                    a,b=urlsplit(urljoin(url,location)),urlsplit(base_url)
                    out['redirect']='SAME_ORIGIN' if (a.scheme,a.hostname,a.port or 443)==(b.scheme,b.hostname,b.port or 443) else 'OTHER_ORIGIN'
            else:out['redirect']='NONE'
    except Exception:pass
    return out


def transport_facts(response,exc,*,failure=None):
    """The bounded transport object for a failed fetch: the boundary's recorded response shape plus the rejection's own fixed literals when (and only when) they are on the allow-lists. Everything else
    is dropped; nothing is derived from exception text."""
    base=response if isinstance(response,dict) else {}
    outcome=getattr(exc,'outcome',None);reason=getattr(exc,'reason',None)
    out=dict(http_status=base.get('http_status'),media_type=base.get('media_type'),redirect=base.get('redirect'),
             rejection_outcome=outcome if outcome in OUTCOMES else ('OTHER' if outcome is not None else None),
             rejection_reason=reason if reason in REASONS else ('OTHER' if reason is not None else None))
    if failure is not None:out['failure']=validate_transport_failure(failure)
    try:return validate_transport(out)
    except ValueError:return None


def validate_transport(value):
    if not isinstance(value,dict) or not (TRANSPORT_KEYS<=set(value)<=TRANSPORT_KEYS|{'failure'}):raise ValueError('DIAGNOSTIC_SCHEMA')
    if 'failure' in value:validate_transport_failure(value['failure'])
    status=value['http_status']
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['media_type'] is not None and value['media_type'] not in MEDIA:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['redirect'] is not None and value['redirect'] not in REDIRECTS:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['rejection_outcome'] is not None and value['rejection_outcome'] not in OUTCOMES|{'OTHER'}:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['rejection_reason'] is not None and value['rejection_reason'] not in REASONS|{'OTHER'}:raise ValueError('DIAGNOSTIC_SCHEMA')
    return dict(value)


def shape(body,stage,code,transport=None):
    if stage not in STAGES:stage='UNKNOWN'
    if code not in CODES:code='UNKNOWN'
    out=dict(version=1,stage=stage,code=code,body_bytes=len(body),
             body_sha256=hashlib.sha256(body).hexdigest(),shape_available=False)
    if transport is not None:out['transport']=transport
    # Diagnostic parsing has its own finite structural ceiling. Failure to obtain
    # shape never changes the source failure or permits another call.
    if not isinstance(body,bytes) or not body or len(body)>1_000_000 or body.count(b'<')>20000:return out
    try:
        soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
        counts={'summary_tables':len(soup.select('#simpleDetailsTable')),
                'order_by_selects':len(soup.select('select[name="orderBy"]')),'forms':len(soup.find_all('form'))}
        labels={'Reference':'reference_labels','Status':'status_labels','Decision':'decision_labels','Decision Issued Date':'decision_date_labels'}
        counts.update({k:0 for k in labels.values()})
        for row in soup.select('#simpleDetailsTable tr'):
            cells=row.find_all(['th','td'])
            if len(cells)==2 and cells[0].get_text(strip=True) in labels:
                counts[labels[cells[0].get_text(strip=True)]]+=1
        out.update(shape_available=True,counts=counts)
    except Exception:pass
    return out


def validate(value):
    keys={'version','stage','code','body_bytes','body_sha256','shape_available'}
    if not isinstance(value,dict) or not (keys<=set(value)<=keys|{'counts','transport'}):raise ValueError('DIAGNOSTIC_SCHEMA')
    if 'transport' in value:validate_transport(value['transport'])
    if (type(value['version']) is not int or value['version']!=1 or value['stage'] not in STAGES or value['code'] not in CODES
        or type(value['body_bytes']) is not int or not 0<=value['body_bytes']<=2_000_000
        or not isinstance(value['body_sha256'],str) or re.fullmatch('[0-9a-f]{64}',value['body_sha256']) is None
        or type(value['shape_available']) is not bool):raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['shape_available']:
        c=value.get('counts')
        if not isinstance(c,dict) or set(c)!=COUNTS or any(type(n) is not int or not 0<=n<=20000 for n in c.values()):raise ValueError('DIAGNOSTIC_SCHEMA')
    elif 'counts' in value:raise ValueError('DIAGNOSTIC_SCHEMA')
    return dict(value)


# Fixed literals only; no runtime exception-name/message export.
FAILURE_STAGES = frozenset({'REQUEST_DISPATCH','RESPONSE_READ','RESPONSE_STATUS','UNKNOWN'})
FAILURE_REASONS = frozenset({'DNS_FAILURE','TCP_CONNECTION_REFUSED','TCP_NETWORK_UNREACHABLE',
    'TCP_HOST_UNREACHABLE','TRANSPORT_PERMISSION_DENIED','CONNECTION_RESET','CONNECT_TIMEOUT',
    'READ_TIMEOUT','TIMEOUT_UNKNOWN_STAGE','TLS_CERTIFICATE_VERIFICATION_FAILED','TLS_FAILURE',
    'PROXY_FAILURE','UNKNOWN'})
FAILURE_CLASSES = frozenset({'REQUESTS_CONNECTION_ERROR','REQUESTS_CONNECT_TIMEOUT',
    'REQUESTS_READ_TIMEOUT','REQUESTS_TIMEOUT','REQUESTS_SSL_ERROR','REQUESTS_PROXY_ERROR',
    'URLLIB3_MAX_RETRY_ERROR','URLLIB3_NAME_RESOLUTION_ERROR','URLLIB3_NEW_CONNECTION_ERROR',
    'URLLIB3_CONNECT_TIMEOUT','URLLIB3_READ_TIMEOUT','URLLIB3_SSL_ERROR','URLLIB3_PROXY_ERROR',
    'SOCKET_GAIERROR','OS_ERROR','CONNECTION_REFUSED_ERROR','CONNECTION_RESET_ERROR',
    'PERMISSION_ERROR','TIMEOUT_ERROR','SSL_CERT_VERIFICATION_ERROR','SSL_ERROR','UNKNOWN'})
FAILURE_CODES = frozenset({'EAI_AGAIN','EAI_NONAME','EAI_FAIL','EAI_NODATA','ECONNREFUSED',
    'ENETUNREACH','EHOSTUNREACH','EACCES','EPERM','ECONNRESET','ETIMEDOUT','UNKNOWN'})
FAILURE_KEYS = frozenset({'version','stage','reason','exception_class','error_code','chain_truncated'})
FAILURE_BYTES = 512


def validate_transport_failure(value):
    import json
    if type(value) is not dict or set(value)!=FAILURE_KEYS:raise ValueError('DIAGNOSTIC_SCHEMA')
    if type(value['version']) is not int or value['version']!=1 or type(value['chain_truncated']) is not bool:
        raise ValueError('DIAGNOSTIC_SCHEMA')
    for key,allowed in (('stage',FAILURE_STAGES),('reason',FAILURE_REASONS),
                        ('exception_class',FAILURE_CLASSES),('error_code',FAILURE_CODES)):
        if type(value[key]) is not str or value[key] not in allowed:raise ValueError('DIAGNOSTIC_SCHEMA')
    if len(json.dumps(value,sort_keys=True).encode())>FAILURE_BYTES:raise ValueError('DIAGNOSTIC_SCHEMA')
    return dict(value)


def transport_failure(exc, stage='UNKNOWN'):
    # Diagnostic failure must never replace the original refusal or grant a retry.
    try:return _transport_failure(exc, stage)
    except Exception:
        return dict(version=1,stage=stage if type(stage) is str and stage in FAILURE_STAGES else 'UNKNOWN',
                    reason='UNKNOWN',exception_class='UNKNOWN',error_code='UNKNOWN',chain_truncated=False)


def _transport_failure(exc, stage='UNKNOWN'):
    """Class/code evidence only, with bounded traversal of exact known wrappers.

    Never read exception text, arbitrary unknown attributes, context, URLs,
    headers, cookies or responses. A class/code does not prove host reachability.
    """
    import errno
    import socket
    import ssl
    import requests.exceptions as rq
    import urllib3.exceptions as u3
    classes = {rq.ConnectionError:'REQUESTS_CONNECTION_ERROR',rq.ConnectTimeout:'REQUESTS_CONNECT_TIMEOUT',
        rq.ReadTimeout:'REQUESTS_READ_TIMEOUT',rq.Timeout:'REQUESTS_TIMEOUT',rq.SSLError:'REQUESTS_SSL_ERROR',
        rq.ProxyError:'REQUESTS_PROXY_ERROR',u3.MaxRetryError:'URLLIB3_MAX_RETRY_ERROR',
        u3.NameResolutionError:'URLLIB3_NAME_RESOLUTION_ERROR',u3.NewConnectionError:'URLLIB3_NEW_CONNECTION_ERROR',
        u3.ConnectTimeoutError:'URLLIB3_CONNECT_TIMEOUT',u3.ReadTimeoutError:'URLLIB3_READ_TIMEOUT',
        u3.SSLError:'URLLIB3_SSL_ERROR',u3.ProxyError:'URLLIB3_PROXY_ERROR',socket.gaierror:'SOCKET_GAIERROR',
        OSError:'OS_ERROR',ConnectionRefusedError:'CONNECTION_REFUSED_ERROR',
        ConnectionResetError:'CONNECTION_RESET_ERROR',PermissionError:'PERMISSION_ERROR',
        TimeoutError:'TIMEOUT_ERROR',ssl.SSLCertVerificationError:'SSL_CERT_VERIFICATION_ERROR',ssl.SSLError:'SSL_ERROR'}
    reason='UNKNOWN';code='UNKNOWN';pending=[exc];seen=set();nodes=[]
    while pending and len(seen)<8:
        node=pending.pop(0)
        if id(node) in seen:continue
        seen.add(id(node))
        if type(node) not in classes:continue
        nodes.append(node)
        # Only exact known wrappers are traversed. Strings and other args ignored.
        children=[node.__cause__]
        children.extend(x for x in node.args[:2] if isinstance(x,BaseException))
        if type(node) is u3.MaxRetryError:children.append(node.reason)
        if type(node) is u3.ProxyError:children.append(node.original_error)
        if type(node) is u3.NameResolutionError:children.append(node._reason)
        pending.extend(x for x in children if isinstance(x,BaseException) and id(x) not in seen)
    truncated=any(id(x) not in seen for x in pending)
    errno_map={getattr(errno,n):n for n in ('ECONNREFUSED','ENETUNREACH','EHOSTUNREACH','EACCES','EPERM','ECONNRESET','ETIMEDOUT')}
    dns_map={getattr(socket,n):n for n in ('EAI_AGAIN','EAI_NONAME','EAI_FAIL','EAI_NODATA') if hasattr(socket,n)}
    for node in nodes:
        if type(node) in (socket.gaierror,OSError,ConnectionRefusedError,ConnectionResetError,PermissionError,TimeoutError):
            n=node.errno
            candidate=(dns_map if type(node) is socket.gaierror else errno_map).get(n) if type(n) is int else None
            if candidate is not None:code=candidate;break
    types={type(n) for n in nodes}
    # Preserve wrapper context: nested proxy TCP/DNS failures do not establish
    # an origin connection; TLS wrapper failures stay TLS unless cert class known.
    if types & {rq.ProxyError,u3.ProxyError}:reason='PROXY_FAILURE'
    elif ssl.SSLCertVerificationError in types:reason='TLS_CERTIFICATE_VERIFICATION_FAILED'
    elif types & {rq.SSLError,u3.SSLError,ssl.SSLError}:reason='TLS_FAILURE'
    elif types & {socket.gaierror,u3.NameResolutionError}:reason='DNS_FAILURE'
    elif code=='ECONNREFUSED' or ConnectionRefusedError in types:reason='TCP_CONNECTION_REFUSED'
    elif code=='ENETUNREACH':reason='TCP_NETWORK_UNREACHABLE'
    elif code=='EHOSTUNREACH':reason='TCP_HOST_UNREACHABLE'
    elif code in {'EACCES','EPERM'} or PermissionError in types:reason='TRANSPORT_PERMISSION_DENIED'
    elif code=='ECONNRESET' or ConnectionResetError in types:reason='CONNECTION_RESET'
    elif types & {rq.ConnectTimeout,u3.ConnectTimeoutError}:reason='CONNECT_TIMEOUT'
    elif types & {rq.ReadTimeout,u3.ReadTimeoutError}:reason='READ_TIMEOUT'
    elif code=='ETIMEDOUT' or types & {rq.Timeout,TimeoutError}:reason='TIMEOUT_UNKNOWN_STAGE'
    out=dict(version=1,stage=stage if type(stage) is str and stage in FAILURE_STAGES else 'UNKNOWN',
        reason=reason,exception_class=classes.get(type(exc),'UNKNOWN'),error_code=code,chain_truncated=truncated)
    return validate_transport_failure(out)
