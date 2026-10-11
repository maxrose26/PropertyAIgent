"""One-response Oldham form metadata. No submission, values or planning facts."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests
from .actions_canary import ImportFence, offline_network_denial

VERSION = 'oldham-form-metadata-v1'
REPOSITORY = 'maxrose26/PropertyAIgent'
URL = 'https://planningpa.oldham.gov.uk/online-applications/search.do?action=advanced&searchType=Application'
AUTHORITY = 'AUTHORISE_ONE_OLDHAM_FORM_GET_ONLY'
MAX_BODY = 2_000_000
MAX_ARTIFACT = 16_384
MAX_FIELDS = 80
STATE = {'_csrf', 'csrfToken', 'org.apache.struts.taglib.html.TOKEN'}
CRITERIA = {'reference', 'applicant', 'applicantName', 'agent', 'address', 'postcode',
            'description', 'proposal', 'keyword', 'dateFrom', 'dateTo', 'startDate',
            'endDate', 'dateApplicationReceivedStart', 'dateApplicationReceivedEnd',
            'dateApplicationDecidedStart', 'dateApplicationDecidedEnd',
            'applicationType', 'caseType', 'status', 'decision', 'ward', 'parish'}
SAFE_NAMES = STATE | {'action', 'searchType', 'dateType', 'caseType', 'applicationType'} | {
    'searchCriteria.' + k for k in CRITERIA}
CLASSES = {'REQUIRED_SERVER_STATE', 'APPROVED_REFERENCE_INPUT', 'APPROVED_FIXED_DEFAULT',
           'IGNORABLE_NON_SUBMITTED_CONTROL', 'PROHIBITED_SEARCH_EXPANSION', 'UNKNOWN'}
REASONS = {'REFERENCE', 'RECOGNISED_STATE_SHAPE', 'UNAPPROVED_STATE_SHAPE',
           'FIXED_DEFAULT', 'UNAPPROVED_DEFAULT', 'EMPTY_CRITERION', 'POPULATED_CRITERION',
           'UNKNOWN_FIELD', 'NON_SUBMITTED_CONTROL', 'DUPLICATE_NAME'}
TYPES = {'text', 'hidden', 'submit', 'reset', 'button', 'checkbox', 'radio', 'email',
         'password', 'date', 'number', 'search', 'select', 'textarea', 'other'}


class Failure(Exception):
    pass


class OneGet:
    """Only a literal GET URL can reach an injected physical transport."""
    def __init__(self, dispatch):
        self.dispatch, self.requests, self.received_bytes = dispatch, 0, 0
        self.status = None

    def request(self, method, url):
        if method != 'GET' or url != URL or self.requests:
            raise Failure('REQUEST_DENIED')
        self.requests += 1
        response = None
        try:
            response = self.dispatch('GET', URL, allow_redirects=False, stream=True, timeout=15)
            self.status = response.status_code
            if 300 <= response.status_code < 400:
                raise Failure('REDIRECT_DENIED')
            if response.status_code != 200:
                raise Failure('HTTP_UNAVAILABLE')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                raw = getattr(response, 'raw', None)
                wire = raw.tell() if raw is not None and hasattr(raw, 'tell') else 0
                self.received_bytes = max(len(body), wire)
                if self.received_bytes > MAX_BODY:
                    raise Failure('BODY_OVERFLOW')
            raw = getattr(response, 'raw', None)
            wire = raw.tell() if raw is not None and hasattr(raw, 'tell') else 0
            self.received_bytes = max(self.received_bytes, wire)
            if self.received_bytes > MAX_BODY: raise Failure('BODY_OVERFLOW')
            return response.status_code, bytes(body)
        finally:
            if response is not None:
                try:
                    raw = getattr(response, 'raw', None)
                    wire = raw.tell() if raw is not None and hasattr(raw, 'tell') else 0
                    self.received_bytes = max(self.received_bytes, wire)
                finally:
                    response.close()


def classification(name, value, *, non_submitted=False):
    # These are diagnostic candidates, never an amendment to verifier admission.
    if name == 'searchCriteria.reference': return 'APPROVED_REFERENCE_INPUT', 'REFERENCE'
    if name in STATE:
        valid = bool(re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value))
        return 'REQUIRED_SERVER_STATE', 'RECOGNISED_STATE_SHAPE' if valid else 'UNAPPROVED_STATE_SHAPE'
    if name in ('action', 'searchType'):
        valid = value == ('Search' if name == 'action' else 'Application')
        return ('APPROVED_FIXED_DEFAULT' if valid else 'UNKNOWN'), ('FIXED_DEFAULT' if valid else 'UNAPPROVED_DEFAULT')
    if name.startswith('searchCriteria.'):
        return ('PROHIBITED_SEARCH_EXPANSION' if value else 'APPROVED_FIXED_DEFAULT'), ('POPULATED_CRITERION' if value else 'EMPTY_CRITERION')
    if non_submitted: return 'IGNORABLE_NON_SUBMITTED_CONTROL', 'NON_SUBMITTED_CONTROL'
    return 'UNKNOWN', 'UNKNOWN_FIELD'


def parse_form(body):
    soup = BeautifulSoup(body.decode('utf-8', errors='strict'), 'html.parser')
    forms = soup.find_all('form')
    candidates = [(i, f) for i, f in enumerate(forms) if f.select('input[name="searchCriteria.reference"]')]
    if len(forms) > 20 or len(candidates) != 1:
        raise Failure('FORM_SELECTION_FAILED')
    ordinal, form = candidates[0]
    method = form.get('method', 'GET').upper()
    target = urlsplit(urljoin(URL, form.get('action', '')))
    action = target.path if (target.scheme == 'https' and target.netloc == 'planningpa.oldham.gov.uk'
        and target.path in ('/online-applications/search.do', '/online-applications/advancedSearchResults.do')
        and target.query in ('', 'action=firstPage') and not target.fragment) else None
    controls = form.find_all(['input', 'select', 'textarea', 'button'])
    if len(controls) > MAX_FIELDS: raise Failure('FIELD_OVERFLOW')
    names = [el.get('name', '') for el in controls]
    rows = []
    for i, el in enumerate(controls):
        name = el.get('name', '')
        kind = el.name if el.name in ('select', 'textarea') else el.get('type', 'submit' if el.name == 'button' else 'text').lower()
        kind = kind if kind in TYPES else 'other'
        options = el.find_all('option') if el.name == 'select' else []
        if len(options) > 500: raise Failure('OPTION_OVERFLOW')
        explicit = [j for j, o in enumerate(options) if o.has_attr('selected')]
        selected = explicit or ([0] if options and not el.has_attr('multiple') else [])
        if el.name == 'select': value = '\n'.join(options[j].get('value', options[j].get_text()) for j in selected)
        elif el.name == 'textarea': value = el.get_text()
        else: value = el.get('value', '')
        disabled = el.has_attr('disabled') or any(p.name == 'fieldset' and p.has_attr('disabled') for p in el.parents)
        non_submitted = disabled or not name or kind in ('submit', 'reset', 'button') or (kind in ('checkbox', 'radio') and not el.has_attr('checked'))
        category, reason = classification(name, value, non_submitted=non_submitted)
        duplicate = bool(name and names.count(name) > 1)
        if duplicate: reason = 'DUPLICATE_NAME'
        rows.append(dict(ordinal=i, identifier=name if name in SAFE_NAMES else None,
            identifier_redacted=bool(name and name not in SAFE_NAMES), named=bool(name),
            control_type=kind, populated=bool(value), disabled=disabled,
            checked=el.has_attr('checked'), multiple=el.has_attr('multiple'),
            option_count=len(options), selected_ordinals=selected, duplicate_name=duplicate,
            current_verifier_collects=el.name == 'input' and bool(name),
            classification_candidate=category, rejection_category=reason))
    return dict(form_count=len(forms), selected_form_ordinal=ordinal,
        form_method=method if method in ('GET', 'POST') else 'UNKNOWN',
        form_action_path=action, form_action_approved_shape=action is not None,
        fields=rows, classification_is_approval=False)


def envelope(sha, mode):
    return dict(manifest_version=VERSION, repository=REPOSITORY, repository_sha=sha,
        execution_time=dt.datetime.now(dt.timezone.utc).isoformat(), mode=mode,
        source_host='planningpa.oldham.gov.uk', source_path='/online-applications/search.do',
        execution_status='FAIL', failure_category=None, http_status=None,
        request_count=0, council_network_requests=0, received_bytes=0,
        elapsed_seconds=0, accounting_complete=True, form=None)


def encode(result):
    b = (json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()
    if len(b) > MAX_ARTIFACT: raise Failure('ARTIFACT_OVERFLOW')
    return b


def run(sha, mode='offline', dispatch=None):
    if not re.fullmatch('[0-9a-f]{40}', sha) or mode not in ('offline', 'live'): raise ValueError('Identity')
    result, started, session = envelope(sha, mode), time.monotonic(), None
    if dispatch is None:
        if mode == 'offline':
            from .form_metadata_fixture import fixture_response
            dispatch = fixture_response
        else:
            session = requests.Session(); session.trust_env = False
            session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
            dispatch = session.request
    transport = OneGet(dispatch)
    fence = ImportFence(); sys.meta_path.insert(0, fence)
    try:
        result['http_status'], body = transport.request('GET', URL)
        result['form'] = parse_form(body)
        result['execution_status'] = 'COMPLETE'
        encode(result)
    except Failure as e:
        result.update(execution_status='FAIL', failure_category=str(e), form=None)
    except Exception:
        result.update(execution_status='FAIL', failure_category='RETRIEVAL_OR_PARSE_FAILURE', form=None)
    finally:
        sys.meta_path.remove(fence)
        if session is not None: session.close()
    result.update(request_count=transport.requests,
        http_status=transport.status,
        council_network_requests=transport.requests if mode == 'live' else 0,
        received_bytes=transport.received_bytes, elapsed_seconds=round(time.monotonic()-started, 3))
    try: encode(result)
    except Failure: result.update(execution_status='FAIL', failure_category='ARTIFACT_OVERFLOW', form=None)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--sha', required=True)
    p.add_argument('--mode', choices=('offline', 'live'), default='offline')
    p.add_argument('--authority', default='OFFLINE_ONLY'); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or (a.mode == 'live' and a.authority != AUTHORITY): return 2
    if a.mode == 'offline':
        with offline_network_denial(): result = run(a.sha, a.mode)
    else: result = run(a.sha, a.mode)
    with a.output.open('xb') as f: f.write(encode(result))
    return 0 if result['execution_status'] == 'COMPLETE' else 1


if __name__ == '__main__': raise SystemExit(main())
