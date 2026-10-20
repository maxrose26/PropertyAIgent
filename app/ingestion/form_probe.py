"""Receipt of the Bolton FORM PROBE. A diagnostic observation: it is not a listing receipt, can never be screened and never satisfies a capture."""
import re
from .ledger import Denied
from .coordinator import validate_outer

KIND='FORM_PROBE_RECEIPT_V1'
OUTCOMES=frozenset({'FORM_RECOGNISED','FORM_NOT_RECOGNISED','REQUEST_REJECTED'})
BODY_KEYS=frozenset({'body_bytes','body_sha256','shape_available','counts'})
# The bounded transport schema (restated from verification/discovery/source_diagnostics.py because application code never imports verification; tests/test_ingestion_form_probe_source.py proves the two are identical).
TRANSPORT_KEYS=frozenset({'http_status','media_type','redirect','rejection_outcome','rejection_reason'})
TRANSPORT_OUTCOMES=frozenset({'PARTIAL_RETRIEVAL','SOURCE_UNAVAILABLE','RATE_LIMITED','TIMEOUT','AMBIGUOUS_SOURCE_RESULT','REFERENCE_NOT_FOUND','FORM_REJECTED','LAYOUT_UNRECOGNISED','BUDGET_EXCEEDED'})
TRANSPORT_REASONS=frozenset({'HTTP failure','HTTP rate limit','transport failed','transient upstream response','response shape','document response rejected','closed transport','closed','origin rejected','noncanonical route',
                             'unapproved route class','unapproved form action','unapproved form field','method rejected','search expansion rejected','POST query rejected','exact reference required','window request not admitted',
                             'redirect ceiling','missing redirect location','request ceiling','request payload ceiling','response byte ceiling','run deadline','run-local host circuit open','unqualified transport failure',
                             'parser body bound','unqualified source encoding','discovery/document route rejected','additional search criterion rejected','no exact result','multiple plausible exact results'})
TRANSPORT_MEDIA=frozenset({'text/html','application/xhtml+xml','text/plain','application/json','application/xml','text/xml','OTHER'})
TRANSPORT_REDIRECTS=frozenset({'NONE','SAME_ORIGIN','OTHER_ORIGIN','MISSING_LOCATION'})


def validate_transport(value):
    if not isinstance(value,dict) or set(value)!=TRANSPORT_KEYS:raise ValueError('DIAGNOSTIC_SCHEMA')
    status=value['http_status']
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['media_type'] is not None and value['media_type'] not in TRANSPORT_MEDIA:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['redirect'] is not None and value['redirect'] not in TRANSPORT_REDIRECTS:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['rejection_outcome'] is not None and value['rejection_outcome'] not in TRANSPORT_OUTCOMES|{'OTHER'}:raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['rejection_reason'] is not None and value['rejection_reason'] not in TRANSPORT_REASONS|{'OTHER'}:raise ValueError('DIAGNOSTIC_SCHEMA')
    return dict(value)
OBSERVATION_KEYS=frozenset({'outcome','stage','failure','transport','body'})


def project(source,outer,limits):
    """Validate the form-only worker audit and the supervisor's closure and return the receipt. A council answer of ANY kind is accepted as an observation; a malformed worker audit, an unsafe
    supervisor outcome, more than one request, a retry or a redirect followed is a Denied (and so the accepted fail-safe stop)."""
    validate_outer(outer,limits)
    if (not isinstance(source,dict) or source.get('probe')!='FORM_ONLY' or source.get('council')!='bolton' or source.get('persistence') is not False or source.get('pages')!=[] or source.get('records')!=[]
        or source.get('cleanup')!='SESSION_BOUNDARY_CLOSED'):raise Denied('FORM_PROBE_SHAPE')
    resource=source.get('resource') or {}
    if (resource.get('requests_attempted') not in (0,1) or resource.get('retries')!=0 or resource.get('redirects')!=0 or resource.get('retry_policy')!='NO_INTERNAL_RETRY'
        or type(resource.get('received_bytes')) is not int or not 0<=resource['received_bytes']<=262144 or resource.get('budget_exhaustion') not in (True,False)):raise Denied('FORM_PROBE_ACCOUNTING')
    observation=source.get('observation')
    if not isinstance(observation,dict) or set(observation)!=OBSERVATION_KEYS or observation['outcome'] not in OUTCOMES or observation['stage'] not in ('FORM_REQUEST','FORM_PARSE'):raise Denied('FORM_PROBE_OBSERVATION')
    if observation['failure'] is not None and (not isinstance(observation['failure'],str) or re.fullmatch(r'[A-Za-z]{1,40}:[A-Z_]{3,60}|UNCLASSIFIED_FAILURE',observation['failure']) is None):raise Denied('FORM_PROBE_OBSERVATION')
    transport=observation['transport']
    if transport is not None:
        try:validate_transport(transport)
        except ValueError:raise Denied('FORM_PROBE_TRANSPORT') from None
    body=observation['body']
    if not isinstance(body,dict) or not set(body)<=BODY_KEYS or not {'body_bytes','body_sha256','shape_available'}<=set(body) or type(body['body_bytes']) is not int or not 0<=body['body_bytes']<=262144:raise Denied('FORM_PROBE_BODY')
    if re.fullmatch('[0-9a-f]{64}',body['body_sha256']) is None:raise Denied('FORM_PROBE_BODY')
    return dict(kind=KIND,council='bolton',requested_interval=source['requested_interval'],date_semantics=source['date_semantics'],observation=observation,
                resource={k:resource[k] for k in ('requests_attempted','retries','redirects','received_bytes','elapsed_seconds','budget_exhaustion','retry_policy') if k in resource},
                source_qualification='DIAGNOSTIC_ONLY_NOT_A_CAPTURE',body_retained=False,cleanup='CLOSED',accounting_complete=True)
