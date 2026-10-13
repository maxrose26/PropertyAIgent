"""One observed guest read, no cookies/tokens copied and no B2 eligibility."""
import hashlib
import datetime as dt
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 1024 * 1024
RECORD_GETTER = 'serviceComponent://ui.force.components.controllers.recordGlobalValueProvider.RecordGvpController/ACTION$getRecord'
HOST_CONFIG_GETTER = 'serviceComponent://ui.force.components.controllers.hostConfig.HostConfigController/ACTION$getConfigData'
PLANNING_OBJECT = 'arcusbuiltenv__Planning_Application__c'
FACT_FIELDS = {'reference':'Name', 'status':'arcusbuiltenv__Status__c',
               'decision':'arcusbuiltenv__Current_Decision__c',
               'decision_date':'arcusbuiltenv__Decision_Notice_Sent_Date_Manual__c'}


def record_observation(data, record_id, reference):
    """Only the observed exact application subtree, never surrounding text."""
    providers=data.get('context',{}).get('globalValueProviders',[])
    maps=[p['values']['records'] for p in providers if isinstance(p,dict)
          and isinstance(p.get('values'),dict) and isinstance(p['values'].get('records'),dict)
          and p['values']['records']]
    if len(maps)!=1 or set(maps[0])!={record_id}:
        raise ValueError('RESPONSE_RECORD_SCOPE')
    typed=maps[0][record_id]
    if not isinstance(typed,dict) or set(typed)!={PLANNING_OBJECT}:
        raise ValueError('RESPONSE_OBJECT_SCOPE')
    scoped=typed[PLANNING_OBJECT]
    if not isinstance(scoped,dict):
        raise ValueError('RECORD_SHAPE')
    record=scoped.get('record')
    if not isinstance(record,dict) or not isinstance(record.get('fields'),dict):
        raise ValueError('RECORD_SHAPE')
    fields=record['fields']
    identity=fields.get('Id',{})
    if not isinstance(identity,dict):
        raise ValueError('RECORD_IDENTITY')
    ids=[value for value in (record.get('id'),identity.get('value')) if value is not None]
    if not ids or any(value!=record_id for value in ids):
        raise ValueError('RECORD_IDENTITY')
    name=fields.get('Name',{})
    if not isinstance(name,dict) or name.get('value')!=reference or name.get('displayValue') not in (None,reference):
        raise ValueError('REFERENCE_IDENTITY')
    result={}
    for field,api in FACT_FIELDS.items():
        node=fields.get(api)
        item={'api_field':api,'location':'context.globalValueProviders[].values.records.<exact-id>.'+PLANNING_OBJECT+'.record.fields.'+api}
        if api not in fields:
            item.update(state='NOT_PRESENT',value=None)
        elif not isinstance(node,dict) or 'value' not in node:
            item.update(state='UNPARSEABLE',value=None)
        elif node['value'] is None:
            item.update(state='UNKNOWN',value=None,raw_null=True)
        elif not isinstance(node['value'],str) or len(node['value'])>160:
            item.update(state='UNPARSEABLE',value=None)
        else:
            item.update(state='PRESENT_VALUE' if node['value'].strip() else 'PRESENT_BLANK',value=node['value'])
        if isinstance(node,dict) and 'displayValue' in node:
            display=node['displayValue']
            if display is None or isinstance(display,str) and len(display)<=160:
                item['display_value']=display
            if field!='decision_date' and display not in (None,item['value']):
                item['state']='CONFLICTING'
            elif field=='decision_date' and display is not None:
                # Compare the observed ISO/raw and UK/display encodings only.
                # Both formats already occur in lapse_tracking's accepted parser.
                try:
                    raw_date=dt.datetime.strptime(item['value'],'%Y-%m-%d').date()
                    shown_date=dt.datetime.strptime(display,'%d/%m/%Y').date()
                    if raw_date!=shown_date:
                        item['state']='CONFLICTING'
                except (ValueError,TypeError):
                    item['state']='UNPARSEABLE'
        result[field]=item
    # Qualification metadata only: compare exact known public UI literals, never
    # export arbitrary source values or assign semantics from text matching.
    ui_matches={}
    display_matches={}
    if reference=='PA/2025/1084':
        for label,literal in (('Status','Decision Made'),('Decision','Approve with Conditions')):
            ui_matches[label]=sorted(api for api,node in fields.items()
                if isinstance(api,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',api)
                and isinstance(node,dict) and node.get('value')==literal)[:10]
            # Diagnostic only. A display-value coincidence is not a qualified
            # source mapping. Export neither arbitrary values nor labels.
            display_matches[label]=[
                {'api_field':api, 'raw_type':type(node.get('value')).__name__,
                 'label_matches':node.get('label') == label}
                for api,node in sorted(fields.items())
                if isinstance(api,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,100}',api)
                and isinstance(node,dict) and node.get('displayValue')==literal][:10]
    return {'exact_record_id_present':True,'exact_reference_value_present':True,
            'other_record_identity_count':0,'record_identity_sources':len(ids),
            'record_field_states':result,'known_public_ui_literal_candidate_keys':ui_matches,
            'known_public_ui_display_candidates':display_matches}


def record_descriptor_matches(value, record_id):
    if not isinstance(value, str) or len(value)>256:
        return False
    # Exact control sequence observed from the ordinary public page in run 11.
    return value == record_id + '.undefined.FULL.null.null.null.VIEW.true.null.null.null'


def fact_read_candidate(metadata):
    """Do not consume the single fact-read slot for an unrelated partial read."""
    return any(m.get('descriptor')==RECORD_GETTER and
               m.get('record_descriptor_closed_shape') is True for m in metadata)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def bootstrap_action_shape(body):
    """Diagnostic keys/types only; never authorise an unknown envelope key.

    Host-config rejection currently identifies no actual extra key. Retain the
    minimum evidence needed to assess that envelope instead of guessing that a
    commonly used Aura property is the property this page supplied.
    """
    if not isinstance(body, str) or len(body) > 65536:
        return []
    try:
        form = parse_qs(body, keep_blank_values=True)
        if len(form.get('message', [])) != 1:
            return []
        message = json.loads(form['message'][0], object_pairs_hook=unique_object)
        actions = message.get('actions')
        if not isinstance(actions, list) or len(actions) != 1:
            return []
        action = actions[0]
        if (not isinstance(action, dict) or len(action) > 20 or
                action.get('descriptor') != HOST_CONFIG_GETTER):
            return []
        return [{'key': key if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', key)
                 else 'UNRETAINED', 'type': type(value).__name__}
                for key, value in sorted(action.items())]
    except (ValueError, TypeError, AttributeError):
        return []


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
    allowed_action_keys = {'id','descriptor','callingDescriptor','params'}
    if kind == 'host_config':
        # Observed as a boolean in frozen Salford run 38469427347. Salesforce
        # documents storable as the action-response caching flag, not authority
        # to call additional methods. Preserve its observed value unchanged.
        # https://developer.salesforce.com/docs/platform/aura-platform/guide/controllers-server-storable-actions.html
        allowed_action_keys.add('storable')
        if 'storable' in action and type(action['storable']) is not bool:
            raise ValueError('STORABLE_FLAG')
    if set(action) - allowed_action_keys:
        raise ValueError('UNREVIEWED_ACTION_KEYS')
    if kind in ('record', 'record_name'):
        if action.get('descriptor') != RECORD_GETTER:
            raise ValueError('RECORD_ACTION_DESCRIPTOR')
        params = action.get('params', {})
        record_id = urlsplit(destination).path.rsplit('/',1)[-1]
        expected = (record_descriptor_matches(params.get('recordDescriptor'), record_id)
                    if kind == 'record' else params.get('recordDescriptor') ==
                    record_id + '.undefined.null.null.null.Name.VIEW.false.null.null.null')
        if set(params) != {'recordDescriptor'} or not expected:
            raise ValueError('RECORD_DESCRIPTOR_SCOPE')
    elif kind == 'host_config':
        # Parameterless public framework read observed in the frozen Salford
        # page. Bootstrap only: it cannot establish application identity/facts.
        if (urlsplit(destination).netloc != 'salfordcitycouncil.my.site.com' or
                action.get('descriptor') != HOST_CONFIG_GETTER or
                action.get('params', {}) != {}):
            raise ValueError('HOST_CONFIG_SCOPE')
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
            if ('value' in value or 'displayValue' in value) and isinstance(label,str) and label.strip().lower() in labels and isinstance(literal,(str,type(None))):
                if literal is None or len(literal)<160:
                    pairs.append([label,literal])
            for key,child in value.items():
                key_path=key if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}',key) else '[key]'
                child_path=path+'.'+key_path
                if key in set(FACT_FIELDS.values()) and isinstance(child,dict):
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
        allowed_query={'r', 'aura.ApexAction.execute'} if kind=='header' else (
            {'r','ui-force-components-controllers-hostConfig.HostConfig.getConfigData'} if kind=='host_config'
            else {'r','ui-force-components-controllers-recordGlobalValueProvider.RecordGvp.getRecord'})
        if any(key not in allowed_query or len(values)!=1 or not re.fullmatch(r'[0-9]{1,10}', values[0]) for key,values in query.items()):
            raise ValueError('UNREVIEWED_QUERY')
        if kind == 'host_config':
            result['request_action_shape'] = bootstrap_action_shape(body)
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
                if kind == 'host_config':
                    # Do not retain configuration values or recursively extract
                    # facts from a framework response unrelated to one record.
                    result.update(exact_reference_value_present=False,
                                  outcome='GUEST_BOOTSTRAP_OBSERVED')
                    if consumer is not None:
                        consumer(bytes(content))
                    result['elapsed_seconds']=round(time.monotonic()-started,3)
                    return result
                if kind in ('record', 'record_name'):
                    result.update(record_observation(data,source.path.rsplit('/',1)[-1],reference))
                else:
                    result.update(response_summary(data,reference))
                result['outcome']='GUEST_JSON_OBSERVED' if result['exact_reference_value_present'] else 'IDENTITY_NOT_ESTABLISHED'
                if consumer is not None and result['outcome']=='GUEST_JSON_OBSERVED':
                    consumer(bytes(content))
    except Exception as exc:
        result['outcome']=str(exc) if type(exc) is ValueError and str(exc).isupper() else type(exc).__name__
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
