"""Credential-free, frozen-reference transport reconnaissance. Never writes B2."""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

CASES = {
    'manchester': (688, '142419/FO/2025', 'https://arcusbe.manchester.gov.uk/pr/s/detail/a1DSl000007GOmFMAW?c__r=Arcus_BE_Public_Register'),
    'manchester_pending': (1299, '138696/FO/2023', 'https://arcusbe.manchester.gov.uk/pr/s/detail/a1DSl000007GO89MAG?c__r=Arcus_BE_Public_Register'),
    'salford': (252, 'PA/2025/1084', 'https://salfordcitycouncil.my.site.com/pr/s/detail/a0kSq000008OfVFIA0?c__r=Arcus_BE_Public_Register'),
    'rochdale': (295, '25/01149/FUL', 'https://account.rochdale.gov.uk/pr/s/detail/a0rSl00000eZEmGIAW?c__r=Arcus_BE_Public_Register'),
    'trafford': (290, '117039/FUL/25', 'https://pa.trafford.gov.uk/online-applications/applicationDetails.do?keyVal=T0TL4VQL01T00&activeTab=summary'),
}
from verification.direct_reference.arcus_manifest import case_definitions
CASES.update(case_definitions())
from verification.discovery.committee_exact import case_definitions as committee_case_definitions
CASES.update(committee_case_definitions())
from verification.discovery.material_qualification import case_definitions as material_case_definitions, IDOX_CASES
CASES.update(material_case_definitions())
from verification.discovery.r0_fixed80_qualification import case_definitions as fixed80_case_definitions
from verification.discovery.r0_bolton53_qualification import case_definitions as bolton53_case_definitions
BOLTON53_CASES = bolton53_case_definitions()
CASES.update(BOLTON53_CASES)
from verification.discovery.narrow_oldham_source import case_definitions as oldham_two_case_definitions
OLDHAM_TWO_CASES=oldham_two_case_definitions()
CASES.update(OLDHAM_TWO_CASES)
FIXED80_CASES = fixed80_case_definitions()
CASES.update(FIXED80_CASES)
from verification.discovery.manchester_shape import CASE as DISCOVERY_CASE, DESTINATION as DISCOVERY_DESTINATION
CASES[DISCOVERY_CASE] = (None, None, DISCOVERY_DESTINATION)
from verification.discovery.manchester_search_shape import CASE as SEARCH_SHAPE_CASE, bootstrap_read_allowed
CASES[SEARCH_SHAPE_CASE] = (None, None, DISCOVERY_DESTINATION)
DISCOVERY_CASES = {DISCOVERY_CASE, SEARCH_SHAPE_CASE}
from verification.discovery.arcus_ui_window import CASE as UI_WINDOW_CASE, enumerate_ui
from verification.discovery.arcus_ui_config import UI_CASES
from verification.discovery.arcus_ui_transport import measure_post, combined_bytes
CASES.update({name:(None,None,config.destination) for name,config in UI_CASES.items()})
MAX_BYTES = 20 * 1024 * 1024
MAX_REQUESTS = 80
MAX_SECONDS = 45


def origin(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('DESTINATION')
    return 'https://' + u.netloc


def safe_path(url):
    """No query, fragment or credential/session-bearing arbitrary path retained."""
    path = urlsplit(url).path
    if path.endswith('/aura'):
        return path if re.fullmatch(r'/[A-Za-z0-9_/-]{1,100}', path) else '/[public-site]/aura'
    for prefix in ('/pr/s/sfsites/', '/pr/sfsites/', '/pr/resource/', '/pr/webruntime/'):
        if path.startswith(prefix):
            return prefix + '[resource]'
    if path.startswith('/pr/s/'):
        return '/pr/s/[page]'
    if path == '/online-applications/applicationDetails.do':
        return path
    return '/[resource]'


def post_descriptors(body):
    """Only Salesforce action identifiers; no argument values/context/tokens."""
    if not body or len(body) > 65536:
        return []

    try:
        message = parse_qs(body).get('message', [''])[0]
        actions = json.loads(message).get('actions', [])
        return [a['descriptor'] for a in actions[:10]
                if isinstance(a, dict) and isinstance(a.get('descriptor'), str)
                and re.fullmatch(r'[A-Za-z0-9_$.:/+-]{1,240}', a['descriptor'])]
    except (ValueError, TypeError, AttributeError):
        return []


def post_metadata(body, destination):
    """Describe public RPC operations without retaining params, context or tokens."""
    if not body or len(body) > 65536:
        return []
    try:
        form = parse_qs(body, keep_blank_values=True)
        actions = json.loads(form.get('message', [''])[0]).get('actions', [])
        records = []
        for action in actions[:10]:
            params = action.get('params', {})
            record = {}
            for key in ('descriptor',):
                value = action.get(key)
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_$.:/+-]{1,240}',value):
                    record[key] = value
            for key in ('namespace', 'classname', 'className', 'method', 'methodName'):
                value=params.get(key)
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.$]{0,160}',value):
                    record[key] = value
            record['parameter_keys'] = sorted(k for k in params if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}',k))[:20]
            inner=params.get('params', {})
            record['argument_keys'] = sorted(k for k in inner if isinstance(k,str) and re.fullmatch(r'[A-Za-z0-9_]{1,80}',k))[:20] if isinstance(inner,dict) else []
            record_id=urlsplit(destination).path.rsplit('/',1)[-1]
            record['contains_frozen_record_id'] = record_id in json.dumps(inner)
            if 'recordDescriptor' in params:
                value=params['recordDescriptor']
                record['record_descriptor_encoding']=type(value).__name__
                if isinstance(value,str):
                    record['record_descriptor_raw']={'length':len(value),'exact_frozen_id':value==record_id,'contains_frozen_id':record_id in value,'delimiter_counts':{c:value.count(c) for c in '.-:;,|/{}[]'}}
                    from verification.direct_reference.arcus_http_probe import record_descriptor_matches
                    record['record_descriptor_closed_shape']=record_descriptor_matches(value,record_id)
                    public_controls={'undefined','null','true','false','Id','Name','VIEW','FULL','COMPACT','RecordTypeId'}
                    record['record_descriptor_slots']=[('FROZEN_RECORD' if part==record_id else part if part in public_controls else 'UNRETAINED_LENGTH_'+str(len(part))) for part in value.split('.')[:15]]
                if isinstance(value,str) and len(value)<8192:
                    try:
                        value=json.loads(value)
                        record['record_descriptor_encoding']='JSON_STRING'
                    except ValueError:
                        value=None
                shape=[]
                def describe(item,path='',depth=0):
                    if depth>4 or len(shape)>=40:
                        return
                    if isinstance(item,dict):
                        for key,child in item.items():
                            if isinstance(key,str) and re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_.$]{0,79}',key):
                                describe(child,path+'.'+key,depth+1)
                    elif isinstance(item,list):
                        shape.append({'path':path,'type':'list','count':len(item)})
                        if path.rsplit('.',1)[-1] in ('fields','optionalFields') and all(isinstance(x,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{0,100}',x) for x in item) and len(item)<=40:
                            shape.append({'path':path,'api_names':item})
                        else:
                            for child in item[:3]: describe(child,path+'[]',depth+1)
                    else:
                        shape.append({'path':path,'type':type(item).__name__,'equals_frozen_id':item==record_id})
                describe(value)
                record['record_descriptor_shape']=shape

            record['token_state'] = 'ABSENT' if 'aura.token' not in form else 'NULL' if form['aura.token'] == ['null'] else 'EMPTY' if form['aura.token'] == [''] else 'PRESENT_NOT_RETAINED'
            records.append(record)
        return records
    except (ValueError, TypeError, AttributeError):
        return []


def qualify(pairs, reference):
    aliases = {'reference': ('Reference', 'Application Reference', 'Planning Application'),
               'status': ('Status',), 'decision': ('Decision',),
               'decision_date': ('Decision notice sent date', 'Decision date', 'Decision Issued Date')}
    result = {}
    for field, labels in aliases.items():
        values = [v.strip() for k, v in pairs if k.strip() in labels]
        if not values:
            state, value = 'NOT_PRESENT', None
        elif len(values) != 1:
            state, value = 'CONFLICTING', None
        else:
            value = values[0]
            state = 'PRESENT_VALUE' if value else 'PRESENT_BLANK'
        if value is not None and len(value) > 160:
            state, value = 'UNPARSEABLE', None
        result[field] = {'state': state, 'value': value}
    exact = result['reference'] == {'state': 'PRESENT_VALUE', 'value': reference}
    return exact, result


def permitted_navigation(url, expected):
    if url == expected:
        return True
    a, b = urlsplit(url), urlsplit(expected)
    if b.path == '/pr/s/register-view':
        return False
    if b.netloc == 'pa.trafford.gov.uk' and url == 'https://pa.trafford.gov.uk/online-applications/':
        return True
    # Observed Salford client route retains the exact frozen Salesforce identity.
    if b.netloc == 'salfordcitycouncil.my.site.com':
        record = b.path.rsplit('/', 1)[-1]
        references = {reference for _, reference, destination in CASES.values() if destination == expected}
        if len(references) != 1:
            return False
        slug = re.sub('[^a-z0-9]', '', references.pop().lower())
        return (origin(url) == origin(expected) and a.path in ('/pr/s/planning-application/' + record + '/' + slug,
                           '/pr/s/planning-application/' + record + '/detail')
                and a.query in (b.query, "") and not a.fragment)
    return False


def request_failure(url, method, resource_type, destination, count):
    if origin(url) != origin(destination):
        return 'UNADMITTED_ORIGIN'
    if count > MAX_REQUESTS:
        return 'REQUEST_LIMIT'
    if method not in ('GET', 'HEAD'):
        return 'UNREVIEWED_METHOD'
    if resource_type == 'Document' and not permitted_navigation(url, destination):
        return 'UNADMITTED_NAVIGATION'
    path = urlsplit(url).path.lower()
    if (re.search(r'\.(pdf|docx?|xlsx?|zip)$', path)
            or any(x in path for x in ('/sfc/', '/servlet/', '/filedownload', '/download/'))):
        return 'DOCUMENT_DENIED'
    return None


def record_failure(audit, reason):
    """Keep fatal controls visible even after an optional action was denied."""
    if audit.get('failure') is None:
        audit['failure'] = reason
    if reason != 'UNREVIEWED_METHOD':
        audit['safety_failure'] = True
        events = audit.setdefault('safety_events', [])
        if reason not in events and len(events) < 8:
            events.append(reason)


def classify_ui_enumeration(audit, fail):
    """Transport boundary: a normal page cap is incomplete, not a safety event.

    Never erase an earlier failure. Parser/criteria/navigation exceptions and
    unknown termination shapes still take the original fatal path. Resource,
    identity and cleanup validation remains the caller's independent duty.
    """
    if audit.get('enumeration_evidence') == 'COUNT_RECONCILED':
        return
    if (audit.get('enumeration_evidence') == 'PAGE_CAP'
            and audit.get('completeness') == 'INCOMPLETE'
            and audit.get('listing_failure') is None
            and audit.get('failure') is None
            and audit.get('safety_failure') is False
            and audit.get('safety_events') == []):
        audit['listing_outcome'] = 'BOUNDED_PAGE_CAP'
        return
    if audit.get('observation_deadline') is True:
        # Budgeted runs only: fixed code, never the allowlisted source-local timeout.
        fail('OBSERVATION_DEADLINE')
        return
    from verification.discovery.arcus_ui_window import LOCAL_TIMEOUT,CRITERIA_OPERATIONS
    typed=audit.get('criteria_control_timeout',{})
    if (typed.get('code')==LOCAL_TIMEOUT and typed.get('operation') in CRITERIA_OPERATIONS
        and typed.get('exception_contract')=='PLAYWRIGHT_LOCATOR_TIMEOUT_V1'
        and audit.get('listing_stage')=='CRITERIA' and audit.get('applied_interval') is None
        and audit.get('failure') is None and audit.get('safety_failure') is False
        and audit.get('safety_events')==[]):
        audit['source_contract_failure']=LOCAL_TIMEOUT
        # No safety event is erased. Cleanup/accounting are checked AFTER browser
        # and owned-process closure by the parent before council containment.
        audit['listing_outcome']=LOCAL_TIMEOUT
        return
    fail('LISTING_NOT_QUALIFIED')


def exact_guest_record(audit, reference):
    """HTTP application identity is independent of optional rendered fields."""
    source = audit.get('record_http_probe')
    if not isinstance(source, dict):
        return False
    fields = source.get('record_field_states')
    return (source.get('outcome') == 'GUEST_JSON_OBSERVED' and source.get('http_status') == 200
            and source.get('exact_record_id_present') is True
            and source.get('exact_reference_value_present') is True
            and source.get('other_record_identity_count') == 0
            and isinstance(fields, dict) and isinstance(fields.get('reference'), dict)
            and fields['reference'].get('state') == 'PRESENT_VALUE'
            and fields['reference'].get('value') == reference)


def browser_launch_options(prepared_font_cache):
    """Default: no options (unchanged launch). Explicit prepared mode: validated browser-only env."""
    if prepared_font_cache is None:
        return {}
    # Imported only in prepared mode: the default path (and the Render disposable job, which ships
    # only this file and arcus_http_probe.py) never depends on the new module.
    from verification.direct_reference.prepared_font_cache import PreparedFontCacheError, headless_shell_executable, launch_env
    cache_dir, manifest_sha256 = prepared_font_cache
    if 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ or 'HOME' not in os.environ:
        raise PreparedFontCacheError('UNVERIFIED')
    executable = headless_shell_executable(os.environ['PLAYWRIGHT_BROWSERS_PATH'])
    return dict(env=launch_env(cache_dir, manifest_sha256, executable, os.environ['HOME'], dict(os.environ)))


def budget_selection(execution_budget, case):
    """None: historical envelope (no import). A named budget: Arcus UI listing cases only."""
    if execution_budget is None:
        return None
    from verification.discovery.execution_budget import select
    if not isinstance(execution_budget, str) or case not in UI_CASES:
        raise ValueError('EXECUTION_BUDGET_SELECTION')
    return select(execution_budget)


async def probe(case, window=None, metadata=False, *, retain_proof=False, prepared_font_cache=None, execution_budget=None, deadline_origin=None):
    from playwright.async_api import async_playwright
    budget = budget_selection(execution_budget, case)
    if (budget is None) != (deadline_origin is None):
        raise ValueError('EXECUTION_BUDGET_SELECTION')
    app_id, reference, destination = CASES[case]
    ui_config=UI_CASES.get(case)
    if ui_config is not None and ui_config.assessment_metadata and window!=(ui_config.start,ui_config.end):
        raise ValueError('ASSESSMENT_FIXED_WINDOW')
    if window is not None:
        if ui_config is None:raise ValueError('listing window only')
        from verification.discovery.arcus_ui_config import dated_config
        ui_config=dated_config(ui_config,*window);destination=ui_config.destination
    if metadata:
        if ui_config is None or window is None:raise ValueError('METADATA_LISTING_ONLY')
        from dataclasses import replace
        ui_config=replace(ui_config,capture_metadata=True)
    if type(retain_proof) is not bool:raise ValueError('proof selection')
    if retain_proof:
        from verification.discovery.four_council_proof import require_scope
        if ui_config is None or metadata:raise ValueError('PROOF_LISTING_ONLY')
        require_scope(ui_config.council,'VALIDATED',ui_config.start,ui_config.end)
    collection_profile=None
    if retain_proof:
        from verification.discovery.four_council_proof import current_collection_profile
        collection_profile=current_collection_profile()
        if collection_profile is not None:
            from verification.discovery.source_profiles import config as profile_config
            if metadata or case!=collection_profile['case'] or list(window or ())!=collection_profile['interval'] or execution_budget!=collection_profile['execution_budget']:raise ValueError('PROFILE_PROBE_BINDING')
            ui_config=profile_config(collection_profile);destination=ui_config.destination
    allowed = origin(destination)
    audit = dict(case=case, application_id=app_id, reference=reference, destination=destination,
                 persistence=False, requests=0, responses=0, redirects=0,
                 decoded_bytes=0, encoded_bytes=0, pages=0, navigations=0, local_frames=0, frame_kinds=[],
                 requested_origins=[], navigated_origins=[], endpoints=[],
                 http_probe=None, record_http_probe=None, name_http_probe=None, host_config_http_probe=None, blocked_actions=[], blocked_action_metadata=[], blocked_posts=0, failure=None, exact_reference=False, fields=None,
                 cleanup='UNKNOWN', navigation_mismatch=None, network_classification='UNKNOWN',
                 safety_failure=False, safety_events=[])
    if case in DISCOVERY_CASES:
        audit.update(purpose='DISCOVERY_LISTING_RPC_SHAPE_ONLY',
                     requested_interval=['2026-09-28', '2026-10-04'],
                     date_semantics='VALIDATED', completeness='UNKNOWN', bootstrap_reads=0, observed_action_metadata=[])
    if case in UI_CASES:
        audit.update(purpose='DISCOVERY_PUBLIC_UI_WINDOW',public_ui_posts=0,measured_public_ui_posts=0,outbound_payload_bytes=0,
            post_body_cdp_reads=0,largest_observed_post_bytes=0,completeness='UNKNOWN',
                     requested_interval=[ui_config.start,ui_config.end],date_semantics='VALIDATED')
    started = time.monotonic()
    deadline = None
    if budget is not None:
        # One observation deadline from the supervisor's start (CLOCK_MONOTONIC is system-wide), so
        # worker start-up is charged to it; the reserve covers browser close and export.
        from verification.discovery.execution_budget import Deadline
        deadline = Deadline(budget['worker_seconds'] - budget['finalisation_reserve_seconds'], started=deadline_origin)
        audit.update(execution_budget=budget['name'], stage_timings={},
                     deadline_ms=int((budget['worker_seconds'] - budget['finalisation_reserve_seconds']) * 1000))
    browser = context = None
    stopped = asyncio.Event()

    def fail(reason):
        record_failure(audit, reason)
        stopped.set()

    def charge(event):
        audit['decoded_bytes'] += event.get('dataLength', 0)
        audit['encoded_bytes'] += event.get('encodedDataLength', 0)
        if combined_bytes(audit) > MAX_BYTES:
            fail('BYTE_LIMIT')

    async def route_handler(event):
        request = event['request']
        audit['requests'] += 1
        try:
            url = request['url']
            request_origin = origin(url)
            if request_origin not in audit['requested_origins']:
                audit['requested_origins'].append(request_origin)
            descriptor = dict(origin=request_origin, path=safe_path(url),
                              method=request['method'], resource_type=event.get('resourceType'))
            if descriptor not in audit['endpoints'] and len(audit['endpoints']) < 80:
                audit['endpoints'].append(descriptor)
            if event.get('redirectedRequestId'):
                audit['redirects'] += 1
            if request['method'] not in ('GET', 'HEAD') and case not in UI_CASES:
                for descriptor in post_descriptors(request.get('postData')):
                    if descriptor not in audit['blocked_actions'] and len(audit['blocked_actions']) < 20:
                        audit['blocked_actions'].append(descriptor)
                metadata_slot = 'observed_action_metadata' if case == SEARCH_SHAPE_CASE else 'blocked_action_metadata'
                for metadata in post_metadata(request.get('postData'), destination):
                    if metadata not in audit[metadata_slot] and len(audit[metadata_slot]) < 20:
                        audit[metadata_slot].append(metadata)
            reason = request_failure(url, request['method'], event.get('resourceType'), destination, audit['requests'])
            if (reason == 'UNREVIEWED_METHOD' and request['method'] == 'POST'
                    and not stopped.is_set() and not audit['safety_failure'] and case == SEARCH_SHAPE_CASE
                    and bootstrap_read_allowed(url, request.get('postData'))):
                audit['bootstrap_reads'] += 1
                if audit['bootstrap_reads'] > 3:
                    fail('BOOTSTRAP_READ_LIMIT')
                    await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                else:
                    await client.send('Fetch.continueRequest', {'requestId':event['requestId']})
                return
            if (reason == 'UNREVIEWED_METHOD' and case in UI_CASES
                    and not stopped.is_set() and not audit['safety_failure']):
                measurement_failure=await measure_post(event,client,audit,ui_config.aura)
                if measurement_failure is not None or stopped.is_set() or combined_bytes(audit)>MAX_BYTES:
                    fail(measurement_failure or 'BYTE_LIMIT')
                    await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                else:
                    audit['public_ui_posts'] += 1
                    await client.send('Fetch.continueRequest', {'requestId':event['requestId']})
                return
            if reason == 'UNREVIEWED_METHOD':
                if case in UI_CASES:
                    fail('UNREVIEWED_METHOD')
                    await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                    return
                if case == SEARCH_SHAPE_CASE:
                    for metadata in post_metadata(request.get('postData'), destination):
                        if metadata not in audit['blocked_action_metadata'] and len(audit['blocked_action_metadata']) < 20:
                            audit['blocked_action_metadata'].append(metadata)
                audit['blocked_posts'] += 1
                if case in DISCOVERY_CASES:
                    # Shape-only observation: no public RPC is sent and no
                    # application identity/fields are asserted.
                    await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                    return
                metadata = post_metadata(request.get('postData'), destination)
                from verification.direct_reference.arcus_http_probe import observed_guest_read, MAX_BODY, fact_read_candidate, HOST_CONFIG_GETTER
                slot = None
                kind = 'header'
                if (allowed == 'https://salfordcitycouncil.my.site.com' and audit['host_config_http_probe'] is None and
                        any(m.get('descriptor') == HOST_CONFIG_GETTER and
                            m.get('parameter_keys') == [] for m in metadata)):
                    slot = 'host_config_http_probe'
                    kind = 'host_config'
                elif audit['record_http_probe'] is None and fact_read_candidate(metadata):
                    slot = 'record_http_probe'
                    kind = 'record'
                elif audit['name_http_probe'] is None and any(m.get('record_descriptor_slots') ==
                        ['FROZEN_RECORD','undefined','null','null','null','Name','VIEW','false','null','null','null']
                        for m in metadata):
                    # The normal page's exact Name-only read is a separate
                    # bootstrap slot, never a substitute for factual evidence.
                    slot = 'name_http_probe'
                    kind = 'record_name'
                elif audit['http_probe'] is None and any(
                        m.get('namespace') == 'arcuscommunity' and
                        m.get('classname') == 'PublicRegisterViewService' and
                        m.get('method') == 'getRecordHeaderDetails' for m in metadata):
                    slot = 'http_probe'
                if slot:
                    if audit['requests'] >= MAX_REQUESTS or audit['decoded_bytes'] + MAX_BODY > MAX_BYTES:
                        fail('HTTP_BUDGET_UNAVAILABLE')
                        await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                        return
                    response_body=[]
                    audit[slot] = observed_guest_read(url, request.get('postData'), destination, reference, response_body.append,kind=kind)
                    audit['requests'] += int(audit[slot]['attempted'])
                    audit['decoded_bytes'] += audit[slot]['received_bytes']
                    if audit['requests'] > MAX_REQUESTS or audit['decoded_bytes'] > MAX_BYTES:
                        fail('HTTP_AGGREGATE_BOUND')
                    if response_body and not stopped.is_set():
                        await client.send('Fetch.fulfillRequest', {'requestId':event['requestId'], 'responseCode':200, 'responseHeaders':[{'name':'Content-Type','value':'application/json'}], 'body':base64.b64encode(response_body[0]).decode('ascii')})
                        audit[slot]['supplied_to_original_page']=True
                        return
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
                return  # collect other blocked public-page actions; never dispatch them
            if reason:
                fail(reason)
            if audit['failure']:
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
            else:
                await client.send('Fetch.continueRequest', {'requestId':event['requestId']})
        except Exception:
            fail('ROUTE_ERROR')
            try:
                await client.send('Fetch.failRequest', {'requestId':event['requestId'], 'errorReason':'BlockedByClient'})
            except Exception:
                pass

    def response_handler(response):
        audit['responses'] += 1
        headers = response.headers
        if ('attachment' in headers.get('content-disposition', '').lower() or
                headers.get('content-type', '').split(';')[0] in ('application/pdf', 'application/octet-stream')):
            fail('DOWNLOAD_DENIED')
        if response.status >= 400:
            fail('HTTP_ERROR')
        try:
            if int(headers.get('content-length', '0')) > MAX_BYTES:
                fail('BYTE_LIMIT')
        except ValueError:
            fail('INVALID_CONTENT_LENGTH')

    def navigation(frame):
        if frame.parent_frame is not None:
            kind = 'BLANK' if frame.url == 'about:blank' else 'SRCDOC' if frame.url == 'about:srcdoc' else 'NETWORK' if frame.url.startswith('https://') else 'OTHER'
            if len(audit['frame_kinds']) < 4:
                audit['frame_kinds'].append({'kind':kind,'direct_child':frame.parent_frame.parent_frame is None})
            # Permit only bounded local blank/srcdoc frame navigations.
            # This admits no additional network destination; scripts are not presumed inert.
            if frame.url in ('about:blank', 'about:srcdoc') and frame.parent_frame.parent_frame is None:
                audit['local_frames'] += 1
                if audit['local_frames'] > 2:
                    fail('FRAME_LIMIT')
            else:
                fail('FRAME_DENIED')
            return
        audit['navigations'] += 1
        try:
            seen = origin(frame.url)
            if seen not in audit['navigated_origins']:
                audit['navigated_origins'].append(seen)
            if not permitted_navigation(frame.url, destination):
                u=urlsplit(frame.url)
                frozen_id=urlsplit(destination).path.rsplit('/',1)[-1]
                audit['navigation_mismatch']={'same_origin':seen==allowed, 'contains_frozen_record_id':frozen_id in u.path, 'path':u.path if frozen_id in u.path and re.fullmatch(r'/[A-Za-z0-9_/-]{1,160}',u.path) else '[redacted]', 'query_keys':sorted(parse_qs(u.query))[:10], 'query_absent':not u.query, 'fragment_present':bool(u.fragment)}
                fail('UNADMITTED_NAVIGATION')
        except ValueError:
            fail('UNADMITTED_NAVIGATION')
        if audit['navigations'] > 2:
            fail('NAVIGATION_LIMIT')

    try:
        async with async_playwright() as playwright:
            try:
                # Prepared-cache validation happens here, before launch and so before navigation.
                launch_options = browser_launch_options(prepared_font_cache)
                browser = await playwright.chromium.launch(headless=True, **launch_options)
                context = await browser.new_context(service_workers='block', accept_downloads=False)
                await context.route_web_socket('**/*', lambda ws: fail('WEBSOCKET_DENIED'))
                context.on('page', lambda _: (audit.update(pages=audit['pages'] + 1),
                                            fail('PAGE_LIMIT') if audit['pages'] > 1 else None))
                page = await context.new_page()
                page.on('framenavigated', navigation)
                page.on('download', lambda _: fail('DOWNLOAD_DENIED'))
                page.on('worker', lambda _: fail('WORKER_DENIED'))
                page.on('response', response_handler)
                client = await context.new_cdp_session(page)
                await client.send('Network.enable')
                client.on('Network.dataReceived', charge)
                client.on('Fetch.requestPaused', route_handler)
                await client.send('Fetch.enable', {'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
                async def navigate():
                    if case == 'trafford':
                        await page.goto('https://pa.trafford.gov.uk/online-applications/', wait_until='domcontentloaded', timeout=12000)
                        if stopped.is_set():
                            return
                    if deadline is None:
                        await page.goto(destination, wait_until='domcontentloaded', timeout=25000)
                    else:
                        navigation_started = time.monotonic()
                        await page.goto(destination, wait_until='domcontentloaded', timeout=deadline.cap_ms(budget['navigation_seconds']))
                        audit['stage_timings']['NAVIGATION'] = int((time.monotonic() - navigation_started) * 1000)
                nav = asyncio.create_task(navigate())
                stop = asyncio.create_task(stopped.wait())
                done, _ = await asyncio.wait((nav, stop), return_when=asyncio.FIRST_COMPLETED)
                if stop in done:
                    nav.cancel()
                    await asyncio.gather(nav, return_exceptions=True)
                else:
                    await nav
                    if case in UI_CASES:
                        await enumerate_ui(page,audit,stopped,ui_config,**({"retain_proof":True} if retain_proof else {}),**({'budget':budget,'deadline':deadline} if deadline is not None else {}))
                        classify_ui_enumeration(audit, fail)
                    else:
                        if case in DISCOVERY_CASES:
                            # Observe bootstrap metadata only; never inspect application DOM.
                            until = time.monotonic() + 8
                            while not stopped.is_set() and not audit['blocked_posts'] and time.monotonic() < until:
                                await asyncio.sleep(.2)
                        # Read only relevant labels; never export whole HTML/body or people.
                        until = time.monotonic() + 8
                        while case not in DISCOVERY_CASES and not stopped.is_set() and time.monotonic() < until:
                            pairs = await page.evaluate("""() => {
                              const labels = new Set(['Reference','Status','Decision','Decision notice sent date','Decision date','Decision Issued Date']);
                              const out=[], nodes=[];
                              function collect(root) { for(const el of root.querySelectorAll('*')) {
                                nodes.push(el); if(nodes.length>15000)throw Error('DOM_LIMIT');
                                if(el.shadowRoot)collect(el.shadowRoot);
                              }}
                              collect(document);
                              for(const el of nodes.filter(x=>['DT','TH'].includes(x.tagName))) {
                                const key=el.innerText.trim(); if(!labels.has(key))continue;
                                const next=el.nextElementSibling;
                                if(next && ['DD','TD'].includes(next.tagName)) out.push([key,next.innerText.trim().slice(0,161)]);
                              }
                              const hs=out.some(x=>x[0]==='Reference')?[]:nodes.filter(x=>x.tagName==='H1');
                              for(const h of hs) if(h.innerText.trim().length<100 && !h.innerText.includes('Application Summary'))out.push(['Reference',h.innerText.trim()]);
                              return out.slice(0,30);
                            }""")
                            exact, fields = qualify(pairs, reference)
                            audit.update(exact_reference=exact, fields=fields)
                            if (exact and fields['status']['state'] == 'PRESENT_VALUE'
                                    or case != 'trafford' and exact_guest_record(audit, reference)):
                                break
                            await asyncio.sleep(.2)
                        if audit['blocked_posts']:
                            fail('UNREVIEWED_METHOD')
                        elif case != 'trafford' and exact_guest_record(audit, reference):
                            pass  # Partial exact-record evidence does not require DOM status.
                        elif not audit['exact_reference']:
                            fail('IDENTITY_NOT_ESTABLISHED')
                        elif not audit['fields'] or audit['fields']['status']['state'] != 'PRESENT_VALUE':
                            fail('STATUS_NOT_ESTABLISHED')
                stop.cancel()
                await asyncio.gather(stop, return_exceptions=True)
            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()
                audit['cleanup'] = 'CONTEXT_BROWSER_CLOSED' if browser is not None else 'NOT_STARTED'
    except Exception as exc:
        code = getattr(exc, 'code', None)  # fixed prepared-cache refusal code, prepared mode only
        fail(code if prepared_font_cache is not None and isinstance(code, str) and code.startswith('PREPARED_FONT_CACHE_')
             else 'BROWSER_' + type(exc).__name__)
    audit['elapsed_seconds'] = round(time.monotonic() - started, 3)
    if deadline is not None:
        audit['remaining_ms'] = int(deadline.remaining() * 1000)
    if collection_profile is not None:
        from verification.discovery.source_profiles import bind_audit
        audit=bind_audit(collection_profile,audit)
    return audit


def execution_environment_allowed(case, mode, environ):
    if mode == "render-disposable":
        return case == "trafford" and environ.get("RENDER_SERVICE_ID") == "crn-d9sv93vavr4c73f98rb0"
    return (mode == "github-hosted" and environ.get("GITHUB_ACTIONS") == "true"
            and environ.get("RUNNER_ENVIRONMENT") == "github-hosted")


def bounded_worker_audit(path,case,metadata=False):
    bound=512000 if metadata else 65536
    return (json.loads(path.read_text()) if path.exists() and path.stat().st_size<bound
            else {'case':case,'failure':'NO_WORKER_AUDIT','persistence':False})


def supervised(case, output, execution_mode="github-hosted", window=None, metadata=False, *, retain_proof=False, prepared_font_cache=None, execution_budget=None):
    if type(retain_proof) is not bool:raise ValueError('proof selection')
    budget = budget_selection(execution_budget, case)
    # Historical envelope literals stay exact when no budget is named.
    max_seconds = MAX_SECONDS if budget is None else budget['worker_seconds']
    rss_ceiling = 1024**3 if budget is None else budget['rss_ceiling_bytes']
    if prepared_font_cache is not None and (not isinstance(prepared_font_cache, tuple) or len(prepared_font_cache) != 2
            or not all(isinstance(x, str) for x in prepared_font_cache)):raise ValueError('PREPARED_FONT_CACHE_SELECTION')
    campaign_scope=None;collection_profile=None
    if retain_proof:
        from verification.discovery.four_council_proof import require_scope,current_manifest_scope,current_collection_profile
        campaign_scope=current_manifest_scope()
        collection_profile=current_collection_profile()
        if collection_profile is None:
            if case!='discovery_rochdale_ui_window' or window is None or metadata:raise ValueError('PROOF_LISTING_ONLY')
            require_scope('rochdale','VALIDATED',*window)
        else:
            from verification.discovery.source_profiles import validate
            validate(collection_profile,campaign_scope)
            if case!=collection_profile['case'] or list(window or ())!=collection_profile['interval'] or metadata or execution_budget!=collection_profile['execution_budget']:raise ValueError('PROFILE_PROBE_BINDING')
            require_scope(collection_profile['council'],'VALIDATED',*window)
    if metadata and (window is None or case not in UI_CASES):raise ValueError('METADATA_LISTING_ONLY')
    if window is not None:
        from verification.discovery.arcus_ui_config import dated_config
        if case not in UI_CASES:raise ValueError("listing window only")
        dated_config(UI_CASES[case],*window)
    import psutil
    owner_proof=False
    if execution_mode=='four-council-owner-local' and retain_proof:
        # Exact opt-in proof scope was checked above. This is kernel containment,
        # not a caller's claim to be a hosted runner or a new source qualification.
        from verification.discovery.four_council_release import owner_source_context
        owner_source_context(execution_budget)
        owner_proof=True
    if not owner_proof and not execution_environment_allowed(case, execution_mode, os.environ):
        raise ValueError('DISPOSABLE_HOSTED_RUNNER_ONLY')
    if int(Path('/proc/self/stat').read_text().split()[0]) != os.getpid():
        raise ValueError('PROCESS_NAMESPACE_MISMATCH')
    start = time.monotonic()
    seen = {}
    peak = 0
    expired = False
    with tempfile.TemporaryDirectory(prefix='stage4-probe-') as directory:
        child_output = Path(directory) / 'result.json'
        env = dict(PATH='/usr/bin:/bin', HOME=directory, TMPDIR=directory, LANG='C.UTF-8',
                   PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        # Browser package cache only; no inherited database, model or GitHub credentials.
        env['PLAYWRIGHT_BROWSERS_PATH'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path.home()/'.cache/ms-playwright'))
        worker_module = ('verification.discovery.narrow_oldham_source' if case in OLDHAM_TWO_CASES
                         else 'verification.discovery.r0_bolton53_qualification' if case in BOLTON53_CASES
                         else 'verification.discovery.r0_fixed80_qualification' if case in FIXED80_CASES
                         else 'verification.discovery.material_qualification' if case in IDOX_CASES
                         else 'verification.direct_reference.instrumented_probe')
        if prepared_font_cache is not None and worker_module != 'verification.direct_reference.instrumented_probe':
            raise ValueError('PREPARED_FONT_CACHE_UNSUPPORTED_CASE')
        if budget is not None and worker_module != 'verification.direct_reference.instrumented_probe':
            raise ValueError('EXECUTION_BUDGET_SELECTION')
        child = subprocess.Popen([sys.executable, '-m', worker_module, '--worker', '--case', case,
                                  '--output', str(child_output)]+(['--window-start',window[0],'--window-end',window[1]] if window else [])+(['--metadata'] if metadata else [])+(['--retain-four-council-proof'] if retain_proof else [])+(['--prepared-font-cache', prepared_font_cache[0], '--prepared-font-cache-sha256', prepared_font_cache[1]] if prepared_font_cache is not None else [])+(['--execution-budget', budget['name'], '--deadline-origin', repr(start)] if budget is not None else [])+(['--campaign-scope',json.dumps(campaign_scope,sort_keys=True)] if campaign_scope is not None else [])+(['--collection-profile',json.dumps(collection_profile,sort_keys=True)] if collection_profile is not None else []), env=env, start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parent = psutil.Process(child.pid)
        try:
            while child.poll() is None:
                rss = 0
                try:
                    owned = [parent] + parent.children(recursive=True)
                except psutil.NoSuchProcess:
                    break
                for process in owned:
                    try:
                        seen[process.pid] = process.create_time()
                        rss += process.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak = max(peak, rss)
                if time.monotonic() - start > max_seconds or rss > rss_ceiling:
                    expired = True
                    break
                time.sleep(.1)
        finally:
            if child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait(timeout=5)
            killed=[]
            for pid, born in seen.items():
                try:
                    p = psutil.Process(pid)
                    if p.create_time() == born and p.status() != psutil.STATUS_ZOMBIE:
                        p.kill(); killed.append(p)
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(killed, timeout=3)
        survivors = []
        for pid, born in seen.items():
            try:
                p = psutil.Process(pid)
                if p.create_time() == born and p.status() != psutil.STATUS_ZOMBIE:
                    survivors.append(pid)
            except psutil.NoSuchProcess:
                pass
        result = bounded_worker_audit(child_output,case,metadata)
        result.update(supervisor_seconds=round(time.monotonic()-start, 3), peak_owned_rss=peak,
                      owned_processes_seen=len(seen), live_owned_survivors=len(survivors),
                      supervisor_limit_hit=expired, process_cleanup='CLOSED' if not survivors else 'FAILED')
        if result.get('source_contract_failure')=='SOURCE_LOCAL_CRITERIA_CONTROL_TIMEOUT':
            result['containment_accounting_verified']=(child.returncode==0 and not expired and not survivors)
            result['accounting_complete']=result['containment_accounting_verified']
        if collection_profile is not None:
            from verification.discovery.source_profiles import validate_audit
            validate_audit(collection_profile,result)
        if retain_proof and child.returncode!=0:
            result['failure']='PROOF_WORKER_EXIT_NOT_CONFIRMED'
        if budget is not None and result.get('execution_budget') != budget['name']:
            # A worker audit that does not declare the selected budget is never accepted under it.
            result['failure'] = result.get('failure') or 'EXECUTION_BUDGET_MISMATCH'
        if expired or survivors:
            result['failure'] = 'SUPERVISOR_BOUND_OR_CLEANUP'
        if retain_proof:
            from verification.discovery.four_council_proof import write_audit
            write_audit(output,result)
        else:output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('failure') is None else 1


def _main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--execution-mode', choices=('github-hosted', 'render-disposable'), default='github-hosted')
    p.add_argument('--window-start');p.add_argument('--window-end');p.add_argument('--metadata',action='store_true');p.add_argument('--retain-four-council-proof',action='store_true')
    p.add_argument('--prepared-font-cache');p.add_argument('--prepared-font-cache-sha256')
    p.add_argument('--execution-budget');p.add_argument('--deadline-origin', type=float)
    a = p.parse_args()
    if bool(a.window_start)!=bool(a.window_end):raise ValueError('window pair')
    if (a.prepared_font_cache is None)!=(a.prepared_font_cache_sha256 is None):raise ValueError('PREPARED_FONT_CACHE_SELECTION')
    fonts={'prepared_font_cache':(a.prepared_font_cache,a.prepared_font_cache_sha256)} if a.prepared_font_cache is not None else {}
    window=(a.window_start,a.window_end) if a.window_start else None
    if (a.execution_budget is None) != (a.deadline_origin is None) or (a.deadline_origin is not None and not a.worker):
        raise ValueError('EXECUTION_BUDGET_SELECTION')
    if a.execution_budget is not None:fonts['execution_budget']=a.execution_budget
    if any(name in os.environ for name in ('DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')):
        raise ValueError('CREDENTIAL_FREE_ONLY')
    if a.output.exists():
        raise ValueError('EXISTING_OUTPUT')
    if a.worker:
        raw=json.dumps(asyncio.run(probe(a.case,window,a.metadata,**({'retain_proof':True} if a.retain_four_council_proof else {}),**fonts,**({'deadline_origin':a.deadline_origin} if a.deadline_origin is not None else {}))),indent=2)+'\n'
        if len(raw.encode())>=(512000 if a.metadata else 65536):raise ValueError('WORKER_AUDIT_BOUND')
        if a.retain_four_council_proof:
            from verification.discovery.four_council_proof import write_audit
            write_audit(a.output,json.loads(raw))
        else:a.output.write_text(raw)
        return 0
    return supervised(a.case, a.output, a.execution_mode,window,a.metadata,**({"retain_proof":True} if a.retain_four_council_proof else {}),**fonts)


def main():
    if '--campaign-scope' not in sys.argv:
        if '--collection-profile' in sys.argv:raise ValueError('PROFILE_REQUIRES_CAMPAIGN_SCOPE')
        return _main()
    from contextlib import nullcontext
    from verification.discovery.four_council_proof import manifest_scope
    selected=None
    if '--campaign-scope' in sys.argv:
        i=sys.argv.index('--campaign-scope')
        if i+1>=len(sys.argv) or len(sys.argv[i+1])>512:raise ValueError('CAMPAIGN_SCOPE')
        selected=json.loads(sys.argv[i+1]);del sys.argv[i:i+2]
    profile=None
    if '--collection-profile' in sys.argv:
        i=sys.argv.index('--collection-profile')
        if i+1>=len(sys.argv) or len(sys.argv[i+1])>8192:raise ValueError('COLLECTION_PROFILE')
        profile=json.loads(sys.argv[i+1]);del sys.argv[i:i+2]
    with manifest_scope(selected,profile) if selected is not None else nullcontext():
        return _main()


if __name__ == '__main__':
    raise SystemExit(main())
