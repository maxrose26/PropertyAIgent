"""One observed guest read, no cookies/tokens copied and no B2 eligibility."""
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 1024 * 1024
RECORD_GETTER = 'serviceComponent://ui.force.components.controllers.recordGlobalValueProvider.RecordGvpController/ACTION$getRecord'


def record_descriptor_matches(value, record_id):
    if not isinstance(value, str) or len(value)>256:
        return False
    # Exact control sequence observed from the ordinary public page in run 11.
    return value == record_id + '.undefined.FULL.null.null.null.VIEW.true.null.null.null'


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def guest_envelope(body, destination, kind='header'):
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
    if kind == 'record':
        if action.get('descriptor') != RECORD_GETTER:
            raise ValueError('RECORD_ACTION_DESCRIPTOR')
        params = action.get('params', {})
        if set(params) != {'recordDescriptor'} or not record_descriptor_matches(
                params['recordDescriptor'], urlsplit(destination).path.rsplit('/',1)[-1]):
            raise ValueError('RECORD_DESCRIPTOR_SCOPE')
    elif kind != 'header':
        raise ValueError('READ_KIND')
    if kind == 'header' and action.get('descriptor') != 'aura://ApexActionController/ACTION$execute':
        raise ValueError('ACTION_DESCRIPTOR')
    params = action.get('params', {})
    if kind == 'header' and set(params) - {'namespace','classname','method','params','cacheable','isContinuation'}:
        raise ValueError('UNREVIEWED_PARAMS')
    if kind == 'header' and (params.get('namespace'), params.get('classname'), params.get('method')) != (
            'arcuscommunity', 'PublicRegisterViewService', 'getRecordHeaderDetails'):
        raise ValueError('ACTION_IDENTITY')
    if 'cacheable' in params and type(params['cacheable']) is not bool:
        raise ValueError('CACHEABLE_FLAG')
    if params.get('isContinuation', False) is not False:
        raise ValueError('CONTINUATION_FLAG')
    url = urlsplit(destination)
    if kind == 'header' and params.get('params') != {'recordId': url.path.rsplit('/',1)[-1], 'registerName':'Arcus_BE_Public_Register'}:
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
        detail=route.rsplit('/',1)[0]+'/detail'
        pages.extend([detail,detail+'?'+url.query])
    if form.get('aura.pageURI',[None])[0] not in pages:
        raise ValueError('PAGE_IDENTITY')
    # Preserve observed body exactly; no constructed context, token or new action.
    return body


def response_summary(data, reference):
    schema = set()
    pairs = []
    field_slices = []
    found = False
    labels = {'reference','application reference','status','decision','decision date',
              'decision notice sent date','decision issued date'}
    nodes = 0
    def visit(value, depth=0, path='$'):
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
            for key,child in value.items():
                key_path=key if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',key) else '[key]'
                child_path=path+'.'+key_path
                if key in {'Name','arcusbuiltenv__Status__c','arcusbuiltenv__Decision__c','arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c'} and isinstance(child,dict):
                    selected={k:v for k,v in child.items() if k in ('label','value','displayValue') and (v is None or isinstance(v,str) and len(v)<=160)}
                    if key!='Name' or child.get('value')==reference:
                        field_slices.append({'path':child_path,'field':key,'selected':selected})
                visit(child,depth+1,child_path)
        elif isinstance(value,list):
            for index,child in enumerate(value):
                visit(child,depth+1,path+'['+str(index)+']')
        elif value == reference:
            found=True
    visit(data)
    return {'response_keys':sorted(schema)[:80], 'exact_reference_value_present':found,
            'planning_label_values':pairs[:20], 'planning_field_slices':field_slices[:20]}


def observed_guest_read(url, body, destination, reference, consumer=None, kind='header'):
    result={'attempted':False,'b2_eligible':False,'received_bytes':0,'outcome':'UNQUALIFIED'}
    started=time.monotonic()
    try:
        source=urlsplit(destination); target=urlsplit(url)
        if (target.scheme!='https' or target.netloc!=source.netloc or
                target.path!='/pr/s/sfsites/aura' or target.fragment or target.username):
            raise ValueError('EXACT_ENDPOINT')
        query = parse_qs(target.query, keep_blank_values=True)
        result['query_shape']=[{'key':key if re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',key) else 'UNRETAINED', 'numeric_single':len(values)==1 and bool(re.fullmatch(r'[0-9]{1,10}',values[0]))} for key,values in list(query.items())[:8]]
        allowed_query={'r', 'aura.ApexAction.execute'} if kind=='header' else {'r','ui-force-components-controllers-recordGlobalValueProvider.RecordGvp.getRecord'}
        if any(key not in allowed_query or len(values)!=1 or not re.fullmatch(r'[0-9]{1,10}', values[0]) for key,values in query.items()):
            raise ValueError('UNREVIEWED_QUERY')
        payload=guest_envelope(body,destination,kind)
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
                if kind == 'record':
                    target_id=source.path.rsplit('/',1)[-1]
                    values=[]
                    def collect(value, depth=0):
                        if depth>15 or len(values)>10000:
                            raise ValueError('RECORD_COMPLEXITY')
                        if isinstance(value,dict):
                            for key,child in value.items():
                                if key in ('id','Id','recordId') and isinstance(child,str) and re.fullmatch(r'[A-Za-z0-9]{18}',child):
                                    values.append(child)
                                collect(child,depth+1)
                        elif isinstance(value,list):
                            for child in value: collect(child,depth+1)
                    collect(actions[0].get('returnValue'))
                    result['exact_record_id_present']=target_id in values
                    result['other_record_identity_count']=len(set(values)-{target_id})
                    if target_id not in values or set(values)-{target_id}:
                        raise ValueError('RESPONSE_RECORD_SCOPE')
                result['outcome']='GUEST_JSON_OBSERVED' if result['exact_reference_value_present'] else 'IDENTITY_NOT_ESTABLISHED'
                if consumer is not None and result['outcome']=='GUEST_JSON_OBSERVED':
                    consumer(bytes(content))
    except Exception as exc:
        result['outcome']=str(exc) if type(exc) is ValueError and str(exc).isupper() else type(exc).__name__
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
