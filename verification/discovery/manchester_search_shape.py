"""Observed public bootstrap getters only; no arbitrary Apex/RPC admission."""
import json
from urllib.parse import parse_qs, urlsplit
from .manchester_shape import DESTINATION
CASE='discovery_manchester_search_shape'
HOST='serviceComponent://ui.force.components.controllers.hostConfig.HostConfigController/ACTION$getConfigData'
APEX='aura://ApexActionController/ACTION$execute'
GETTERS={('DSHLC_HeaderCont','isSelfRegistrationEnabled'),
         *[('DSHLC_ConfigSettings',x) for x in ('getCouncilPrivacyPolicyURL','getCouncilCookieDetailsURL',
             'getCouncilAccessibilityStatementURL','getCouncilTermsAndConditionsURL')]}


def bootstrap_read_allowed(url, body):
    if urlsplit(url)._replace(query='').geturl() != 'https://arcusbe.manchester.gov.uk/pr/s/sfsites/aura': return False
    if not isinstance(body,str) or len(body)>65536: return False
    try:
        form=parse_qs(body,keep_blank_values=True)
        if form.get('aura.token')!=['null'] or len(form.get('message',[]))!=1: return False
        message=json.loads(form['message'][0]); actions=message.get('actions')
        if not isinstance(actions,list) or not 1<=len(actions)<=6: return False
        for a in actions:
            if not isinstance(a,dict): return False
            p=a.get('params',{})
            if a.get('descriptor')==HOST:
                if p!={}: return False
            elif a.get('descriptor')==APEX:
                if not isinstance(p,dict) or set(p)!={'namespace','classname','method','cacheable','isContinuation'}: return False
                if p['namespace']!='' or (p['classname'],p['method']) not in GETTERS: return False
                if type(p['cacheable']) is not bool or p['isContinuation'] is not False: return False
            else: return False
        return True
    except (ValueError,TypeError,AttributeError): return False
