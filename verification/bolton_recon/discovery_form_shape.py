"""One GET of the retained Bolton form; no search, facts, DB or documents.

Resolves the UNKNOWN_CONTROL diagnostic without exposing server-state values.
Only the existing transport's fixed first request is used. Parent supervision
is required by the workflow, with a 35-second hard process deadline.
"""
import hashlib
import json
import re
import time

from .recon import Transport, FORM_URL, soup_for


def inspect_form(body):
    soup = soup_for(body)
    forms = [f for f in soup.find_all('form') if f.find('input', attrs={'name': 'date(applicationReceivedStart)'})]
    if len(forms) != 1:
        raise ValueError('FORM_SELECTION')
    controls = forms[0].find_all(['input', 'select', 'textarea', 'button'])
    if len(controls) > 80:
        raise ValueError('CONTROL_LIMIT')
    result = []
    for i, el in enumerate(controls):
        name = el.get('name', '')
        if not re.fullmatch(r'[A-Za-z0-9_().-]{0,100}', name):
            name = 'UNRECOGNISED_NAME'
        kind = el.name if el.name in ('select', 'textarea') else el.get('type', 'text').lower()
        if kind not in {'select', 'textarea', 'text', 'hidden', 'submit', 'button',
                        'reset', 'checkbox', 'radio', 'date', 'number', 'search'}:
            kind = 'UNKNOWN'
        value = el.get('value', '')
        if el.name == 'select':
            options = el.find_all('option')
            selected = [o for o in options if o.has_attr('selected')] or options[:1]
            value = selected[0].get('value', selected[0].get_text()) if len(selected) == 1 else ''
        # Never report tokens, input defaults, applicant/address text or HTML.
        neutral = value if value in ('', 'All', 'ALL', 'all', 'Application', 'APPLICATION', 'true', 'false') else None
        if re.search('csrf|token|secret|password', name, re.I):
            neutral = None
        result.append({'ordinal': i, 'name': name, 'kind': kind,
                       'populated': bool(value), 'neutral_default': neutral})
    return result


def main():
    transport = Transport()
    started = time.monotonic()
    audit = {'purpose': 'BOLTON_UNKNOWN_CONTROL_SHAPE_ONLY', 'persistence': False,
             'reference_enumeration': False, 'outcome': 'FAILED'}
    try:
        body = transport.request('GET', FORM_URL)
        audit.update(outcome='FORM_OBSERVED', body_sha256=hashlib.sha256(body).hexdigest(),
                     controls=inspect_form(body))
    except Exception as exc:
        audit['failure'] = getattr(exc, 'reason', type(exc).__name__)
    finally:
        transport.close()
        audit.update(requests=transport.requests, bytes=transport.bytes,
                     statuses=transport.statuses, cleanup='CLOSED' if transport.closed else 'FAILED',
                     elapsed_seconds=round(time.monotonic() - started, 3))
    encoded = json.dumps(audit, sort_keys=True)
    if len(encoded.encode()) > 32768:
        raise ValueError('AUDIT_LIMIT')
    print(encoded)
    return 0 if audit['outcome'] == 'FORM_OBSERVED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
