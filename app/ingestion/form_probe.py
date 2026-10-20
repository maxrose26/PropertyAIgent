"""Receipt of the Bolton FORM PROBE. A diagnostic observation: it is not a listing receipt, can never be screened and never satisfies a capture."""
from .ledger import Denied
from .coordinator import validate_outer

KIND='FORM_PROBE_RECEIPT_V1'
OUTCOMES=frozenset({'FORM_RECOGNISED','FORM_NOT_RECOGNISED','REQUEST_REJECTED'})
BODY_KEYS=frozenset({'body_bytes','body_sha256','shape_available','counts'})
OBSERVATION_KEYS=frozenset({'outcome','stage','failure','transport','body'})


def project(source,outer,limits):
    """Validate the form-only worker audit and the supervisor's closure and return the receipt. A council answer of ANY kind is accepted as an observation; a malformed worker audit, an unsafe
    supervisor outcome, more than one request, a retry or a redirect followed is a Denied (and so the accepted fail-safe stop)."""
    from verification.discovery.source_diagnostics import validate_transport
    import re
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
