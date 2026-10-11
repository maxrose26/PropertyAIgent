"""Pinned, clean, disposable Actions supervisor for the ONE-GET diagnostic."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from .actions_runner import supervise
from .form_metadata import (AUTHORITY, CLASSES, MAX_ARTIFACT, MAX_BODY, MAX_FIELDS,
    REASONS, SAFE_NAMES, TYPES, VERSION, REPOSITORY, encode, envelope)

FAILURES = {'REQUEST_DENIED', 'REDIRECT_DENIED', 'HTTP_UNAVAILABLE', 'BODY_OVERFLOW',
    'FORM_SELECTION_FAILED', 'FIELD_OVERFLOW', 'OPTION_OVERFLOW', 'ARTIFACT_OVERFLOW',
    'RETRIEVAL_OR_PARSE_FAILURE', 'INDEPENDENT_DEADLINE', 'INVALID_ARTIFACT', 'SETUP_DEADLINE'}


def validate(result, *, sha, mode, status):
    """Closed metadata schema: no arbitrary error text, identifier or field value."""
    if not isinstance(result, dict) or set(result) != set(envelope(sha, mode)):
        raise ValueError('schema')
    for key, expected in dict(manifest_version=VERSION, repository=REPOSITORY,
            repository_sha=sha, mode=mode, source_host='planningpa.oldham.gov.uk',
            source_path='/online-applications/search.do').items():
        if result[key] != expected: raise ValueError('identity')
    if dt.datetime.fromisoformat(result['execution_time']).utcoffset() != dt.timedelta(0):
        raise ValueError('UTC')
    if result['execution_status'] not in ('COMPLETE', 'FAIL') or result['failure_category'] not in FAILURES | {None}:
        raise ValueError('state')
    if type(result['accounting_complete']) is not bool: raise ValueError('accounting')
    def integer(value, maximum):
        if type(value) is not int or not 0 <= value <= maximum: raise ValueError('bound')
    if type(result['elapsed_seconds']) not in (int, float) or not 0 <= result['elapsed_seconds'] <= 36:
        raise ValueError('elapsed')
    if result['http_status'] is not None:
        integer(result['http_status'], 599)
        if result['http_status'] < 100: raise ValueError('http')
    if result['accounting_complete']:
        integer(result['request_count'], 1)
        integer(result['received_bytes'], MAX_BODY + 65536)
        integer(result['council_network_requests'], 1)
        if result['council_network_requests'] != (result['request_count'] if mode == 'live' else 0):
            raise ValueError('network reconciliation')
    elif any(result[k] is not None for k in ('request_count', 'received_bytes', 'council_network_requests')):
        raise ValueError('interrupted counts must be unknown')
    complete = result['execution_status'] == 'COMPLETE'
    if complete:
        if (status != 0 or result['failure_category'] is not None or not result['accounting_complete']
            or result['request_count'] != 1 or result['http_status'] != 200
            or result['received_bytes'] > MAX_BODY or result['elapsed_seconds'] > 30):
            raise ValueError('contradictory complete')
    elif status == 0 or result['failure_category'] is None or result['form'] is not None:
        raise ValueError('contradictory failure')
    form = result['form']
    if complete:
        required = {'form_count', 'selected_form_ordinal', 'form_method', 'form_action_path',
            'form_action_approved_shape', 'fields', 'classification_is_approval'}
        if not isinstance(form, dict) or set(form) != required: raise ValueError('form schema')
        integer(form['form_count'], 20)
        integer(form['selected_form_ordinal'], form['form_count']-1)
        if form['form_method'] not in ('GET', 'POST', 'UNKNOWN') or form['classification_is_approval'] is not False:
            raise ValueError('method/approval')
        if form['form_action_path'] not in {None, '/online-applications/search.do', '/online-applications/advancedSearchResults.do'}:
            raise ValueError('action')
        if form['form_action_approved_shape'] is not (form['form_action_path'] is not None): raise ValueError('action shape')
        fields = form['fields']
        if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS: raise ValueError('fields')
        keys = {'ordinal', 'identifier', 'identifier_redacted', 'named', 'control_type',
            'populated', 'disabled', 'checked', 'multiple', 'option_count', 'selected_ordinals',
            'duplicate_name', 'current_verifier_collects', 'classification_candidate', 'rejection_category'}
        for i, row in enumerate(fields):
            if not isinstance(row, dict) or set(row) != keys or row['ordinal'] != i: raise ValueError('field schema')
            if row['identifier'] not in SAFE_NAMES | {None}: raise ValueError('identifier')
            for key in ('identifier_redacted', 'named', 'populated', 'disabled', 'checked', 'multiple', 'duplicate_name', 'current_verifier_collects'):
                if type(row[key]) is not bool: raise ValueError('boolean')
            if row['identifier_redacted'] is not (row['named'] and row['identifier'] is None): raise ValueError('redaction')
            if row['control_type'] not in TYPES or row['classification_candidate'] not in CLASSES or row['rejection_category'] not in REASONS:
                raise ValueError('enum')
            integer(row['option_count'], 500)
            selected = row['selected_ordinals']
            if not isinstance(selected, list) or selected != sorted(set(selected)): raise ValueError('selected')
            for ordinal in selected: integer(ordinal, row['option_count']-1)
    encode(result)


def interrupted(sha, mode, reason):
    result = envelope(sha, mode)
    result.update(failure_category=reason, accounting_complete=False,
        request_count=None, received_bytes=None, council_network_requests=None)
    return result


def execute(*, sha, mode, authority, output, deadline=30, job_start_epoch=None):
    if not re.fullmatch('[0-9a-f]{40}', sha) or mode not in ('offline', 'live') or not 0 < deadline <= 30:
        raise ValueError('admission')
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise ValueError('disposable runner required')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], text=True)
    if actual != sha or dirty or output.exists(): raise ValueError('clean pinned checkout/new artifact required')
    if mode == 'live' and authority != AUTHORITY: raise ValueError('distinct live authority required')
    if job_start_epoch is not None:
        remaining = 180 - (time.time() - job_start_epoch) - 20
        if remaining <= 0:
            output.write_bytes(encode(interrupted(sha, mode, 'SETUP_DEADLINE')))
            return 1
        deadline = min(deadline, remaining)
    with tempfile.TemporaryDirectory(prefix='oldham-form-metadata-') as directory:
        audit = Path(directory) / 'metadata.json'
        env = dict(PATH='/usr/bin:/bin', HOME=directory, TMPDIR=directory, LANG='C.UTF-8',
            PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-m', 'verification.stage26b_l1.form_metadata',
            '--sha', sha, '--mode', mode, '--authority', authority, '--output', str(audit)]
        started = time.monotonic()
        status, timeout = supervise(command, env=env, deadline=deadline)
        result = interrupted(sha, mode, 'INDEPENDENT_DEADLINE' if timeout else 'INVALID_ARTIFACT')
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if not timeout and audit.exists() and audit.stat().st_size <= MAX_ARTIFACT:
            try:
                candidate = json.loads(audit.read_bytes())
                validate(candidate, sha=sha, mode=mode, status=status)
                result = candidate
            except Exception: pass
        with output.open('xb') as target: target.write(encode(result))
    return 0 if result['execution_status'] == 'COMPLETE' else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha', required=True)
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--authority', default='OFFLINE_ONLY')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--deadline', type=float, default=30)
    parser.add_argument('--job-start-epoch', type=float)
    try: return execute(**vars(parser.parse_args()))
    except Exception:
        print('Metadata diagnostic admission/supervision failed', file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
