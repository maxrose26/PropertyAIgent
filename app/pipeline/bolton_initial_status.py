"""Narrow initial literal evidence contract; no semantic planning interpretation."""
import re
from urllib.parse import urlsplit, parse_qs

LABELS = {'reference':'Reference','status':'Status','decision':'Decision','decision_date':'Decision Issued Date'}


def route(council, url):
    try:
        u = urlsplit(url)
        q = parse_qs(u.query, keep_blank_values=True)
        return (council == 'bolton' and u.scheme == 'https'
            and u.netloc == 'paplanning.bolton.gov.uk'
            and u.path == '/online-applications/applicationDetails.do'
            and not u.fragment and '\\' not in url and '%' not in url
            and set(q) == {'activeTab', 'keyVal'} and q['activeTab'] == ['summary']
            and len(q['keyVal']) == 1 and re.fullmatch('[A-Za-z0-9_-]{1,100}',q['keyVal'][0]) is not None)
    except (ValueError, TypeError, AttributeError):
        return False


def evidence(council, url, reference, fields, values):
    if (not route(council,url) or not isinstance(reference,str) or not reference
        or fields != {'Reference':reference,'Status':'Deposited'}
        or not isinstance(values,dict) or set(values)!=set(LABELS)):
        return False
    for key,item in values.items():
        if not isinstance(item,dict) or set(item)!={'state','value'}:return False
        if key in {'reference','status'}:
            if item!={'state':'PRESENT_VALUE','value':fields[LABELS[key]]}:return False
        elif item['state'] in {'NOT_PRESENT','UNKNOWN','CONFLICTING','UNPARSEABLE'}:
            if item['value'] is not None:return False
        elif item['state']=='PRESENT_BLANK':
            if not isinstance(item['value'],str) or item['value'].strip() or len(item['value'])>160:return False
        else:return False
    return True
