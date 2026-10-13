"""One observed guest read, no cookies/tokens copied and no B2 eligibility."""
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def guest_envelope(body, destination):
    if not body or len(body) > 65536:
        raise ValueError('BODY_BOUND')
    form = parse_qs(body, keep_blank_values=True)
    if form.get('aura.token') != ['null']:
        raise ValueError('NOT_NULL_GUEST_TOKEN')
    if any(len(values) != 1 for values in form.values()):
        raise ValueError('DUPLICATE_FORM_KEYS')
    if set(form) - {'message', 'aura.context', 'aura.pageURI', 'aura.token'}:
        raise ValueError('UNREVIEWED_FORM_KEYS')
    message = json.loads(form['message'][0], object_pairs_hook=unique_object)
    if set(message) != {'actions'} or len(message['actions']) != 1:
        raise ValueError('SINGLE_ACTION_REQUIRED')
    action = message['actions'][0]
    if set(action) - {'id','descriptor','callingDescriptor','params'}:
        raise ValueError('UNREVIEWED_ACTION_KEYS')
    if action.get('descriptor') != 'aura://ApexActionController/ACTION$execute':
        raise ValueError('ACTION_DESCRIPTOR')
    params = action.get('params', {})
    if set(params) - {'namespace','classname','method','params','cacheable','isContinuation'}:
        raise ValueError('UNREVIEWED_PARAMS')
    if (params.get('namespace'), params.get('classname'), params.get('method')) != (
            'arcuscommunity', 'PublicRegisterViewService', 'getRecordHeaderDetails'):
        raise ValueError('ACTION_IDENTITY')
    if 'cacheable' in params and type(params['cacheable']) is not bool:
        raise ValueError('CACHEABLE_FLAG')
    if params.get('isContinuation', False) is not False:
        raise ValueError('CONTINUATION_FLAG')
    url = urlsplit(destination)
    if params.get('params') != {'recordId': url.path.rsplit('/',1)[-1], 'registerName':'Arcus_BE_Public_Register'}:
        raise ValueError('EXACT_RECORD_REGISTER')
    context = json.loads(form['aura.context'][0], object_pairs_hook=unique_object)
    if not isinstance(context,dict) or set(context) - {'mode','fwuid','app','loaded','dn','globals','uad'}:
        raise ValueError('UNREVIEWED_CONTEXT_KEYS')
    globals_ = context.get('globals')
    if globals_ is not None:
        if not isinstance(globals_, dict) or len(globals_)>20:
            raise ValueError('GLOBALS_SHAPE')
        for key,value in globals_.items():
            if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_.$]{0,79}',key):
                raise ValueError('GLOBALS_KEY')
            if re.search(r'token|secret|auth|session|password|cookie',key,re.I):
                raise ValueError('GLOBALS_SENSITIVE_KEY')
            if type(value) not in (str,bool,int,float,type(None)) or (isinstance(value,str) and len(value)>160):
                raise ValueError('GLOBALS_VALUE_SHAPE')
    expected_page = url.path + ('?' + url.query if url.query else '')
    pages=[expected_page]
    if url.netloc=='salfordcitycouncil.my.site.com':
        route='/pr/s/planning-application/'+url.path.rsplit('/',1)[-1]+'/pa20251084'
        pages.extend([route,route+'?'+url.query])
    if form.get('aura.pageURI',[None])[0] not in pages:
        raise ValueError('PAGE_IDENTITY')
    # Preserve observed body exactly; no constructed context, token or new action.
    return body


def response_summary(data, reference):
    schema = set()
    pairs = []
    found = False
    labels = {'reference','application reference','status','decision','decision date',
              'decision notice sent date','decision issued date'}
    nodes = 0
    def visit(value, depth=0):
        nonlocal nodes, found
        nodes += 1
        if depth > 15 or nodes > 10000:
            raise ValueError('JSON_COMPLEXITY')
        if isinstance(value,dict):
            schema.update(k for k in value if isinstance(k,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',k))
            label=value.get('label',value.get('fieldLabel'))
            literal=value.get('value',value.get('displayValue'))
            if isinstance(label,str) and label.strip().lower() in labels and isinstance(literal,(str,type(None))):
                if literal is None or len(literal)<160:
                    pairs.append([label,literal])
            for child in value.values():
                visit(child,depth+1)
        elif isinstance(value,list):
            for child in value:
                visit(child,depth+1)
        elif value == reference:
            found=True
    visit(data)
    return {'response_keys':sorted(schema)[:80], 'exact_reference_value_present':found,
            'planning_label_values':pairs[:20]}


def observed_guest_read(url, body, destination, reference):
    result={'attempted':False,'b2_eligible':False,'received_bytes':0,'outcome':'UNQUALIFIED'}
    started=time.monotonic()
    try:
        source=urlsplit(destination); target=urlsplit(url)
        if (target.scheme!='https' or target.netloc!=source.netloc or
                target.path!='/pr/s/sfsites/aura' or target.fragment or target.username):
            raise ValueError('EXACT_ENDPOINT')
        query = parse_qs(target.query, keep_blank_values=True)
        if any(not re.fullmatch(r'(r|aura\.[A-Za-z.]+)', key) or len(values)!=1 or not re.fullmatch(r'[0-9]{1,10}', values[0]) for key,values in query.items()):
            raise ValueError('UNREVIEWED_QUERY')
        payload=guest_envelope(body,destination)
        import requests
        with requests.Session() as session:
            session.trust_env=False
            result['attempted']=True
            with session.post(url, data=payload, headers={
                    'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
                    'User-Agent':'PropertyAIgent-Stage4-BoundedPublicProbe',
                    'Origin':source.scheme+'://'+source.netloc, 'Referer':destination},
                    stream=True, allow_redirects=False, timeout=(2,2)) as response:
                result['http_status']=response.status_code
                if response.status_code!=200:
                    raise ValueError('HTTP_NOT_200')
                if response.headers.get('Content-Type','').split(';')[0].strip() not in ('application/json','text/json'):
                    raise ValueError('NON_JSON_RESPONSE')
                content=bytearray()
                for chunk in response.iter_content(65536):
                    result['received_bytes']+=len(chunk)
                    if result['received_bytes']>MAX_BODY or time.monotonic()-started>5:
                        raise ValueError('HTTP_PROBE_BOUND')
                    content.extend(chunk)
                if time.monotonic()-started>5:
                    raise ValueError('HTTP_PROBE_BOUND')
                result['response_sha256']=hashlib.sha256(content).hexdigest()
                data=json.loads(content, object_pairs_hook=unique_object)
                request_id=json.loads(parse_qs(payload)['message'][0])['actions'][0].get('id')
                actions=data.get('actions',[])
                if len(actions)!=1 or actions[0].get('id')!=request_id:
                    raise ValueError('RESPONSE_ACTION_IDENTITY')
                if any(action.get('state')!='SUCCESS' for action in data.get('actions',[])) or not data.get('actions'):
                    raise ValueError('AURA_NOT_SUCCESS')
                result.update(response_summary(data,reference))
                result['outcome']='GUEST_JSON_OBSERVED' if result['exact_reference_value_present'] else 'IDENTITY_NOT_ESTABLISHED'
    except Exception as exc:
        result['outcome']=str(exc) if type(exc) is ValueError and str(exc).isupper() else type(exc).__name__
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
