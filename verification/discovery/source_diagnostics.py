"""Bounded shape-only failure diagnostics. No values, URLs, HTML or exceptions."""
import hashlib
import re
from bs4 import BeautifulSoup

STAGES={'DESTINATION','REQUEST','HEADERS','BODY','DECODE','STRUCTURE','SUMMARY_PARSE',
        'EXACT_REFERENCE','OBSERVATION','FORM_PARSE','ZERO_CHECK','SORT_FORM_PARSE',
        'SORT_VERIFY','PAGE_PARSE','CRITERIA_ECHO','UNKNOWN',
        'FORM_REQUEST','SEARCH_REQUEST','SORT_REQUEST','PAGE_REQUEST','REFINE_REQUEST'}
CODES={'PARSER_FAILURE','PARTIAL_RETRIEVAL','AMBIGUOUS_SOURCE_RESULT','TIMEOUT',
       'SOURCE_UNAVAILABLE','RATE_LIMITED','SOURCE_CONTRACT_REJECTED','UNCLASSIFIED_FAILURE',
       'SORT_SELECTOR_COUNT','DUPLICATE_REFERENCE','UNKNOWN'}
COUNTS={'summary_tables','reference_labels','status_labels','decision_labels','decision_date_labels',
        'order_by_selects','forms'}


def shape(body,stage,code):
    if stage not in STAGES:stage='UNKNOWN'
    if code not in CODES:code='UNKNOWN'
    out=dict(version=1,stage=stage,code=code,body_bytes=len(body),
             body_sha256=hashlib.sha256(body).hexdigest(),shape_available=False)
    # Diagnostic parsing has its own finite structural ceiling. Failure to obtain
    # shape never changes the source failure or permits another call.
    if not isinstance(body,bytes) or not body or len(body)>1_000_000 or body.count(b'<')>20000:return out
    try:
        soup=BeautifulSoup(body.decode('utf-8','strict'),'html.parser')
        counts={'summary_tables':len(soup.select('#simpleDetailsTable')),
                'order_by_selects':len(soup.select('select[name="orderBy"]')),'forms':len(soup.find_all('form'))}
        labels={'Reference':'reference_labels','Status':'status_labels','Decision':'decision_labels','Decision Issued Date':'decision_date_labels'}
        counts.update({k:0 for k in labels.values()})
        for row in soup.select('#simpleDetailsTable tr'):
            cells=row.find_all(['th','td'])
            if len(cells)==2 and cells[0].get_text(strip=True) in labels:
                counts[labels[cells[0].get_text(strip=True)]]+=1
        out.update(shape_available=True,counts=counts)
    except Exception:pass
    return out


def validate(value):
    keys={'version','stage','code','body_bytes','body_sha256','shape_available'}
    if not isinstance(value,dict) or set(value) not in (keys,keys|{'counts'}):raise ValueError('DIAGNOSTIC_SCHEMA')
    if (type(value['version']) is not int or value['version']!=1 or value['stage'] not in STAGES or value['code'] not in CODES
        or type(value['body_bytes']) is not int or not 0<=value['body_bytes']<=2_000_000
        or not isinstance(value['body_sha256'],str) or re.fullmatch('[0-9a-f]{64}',value['body_sha256']) is None
        or type(value['shape_available']) is not bool):raise ValueError('DIAGNOSTIC_SCHEMA')
    if value['shape_available']:
        c=value.get('counts')
        if not isinstance(c,dict) or set(c)!=COUNTS or any(type(n) is not int or not 0<=n<=20000 for n in c.values()):raise ValueError('DIAGNOSTIC_SCHEMA')
    elif 'counts' in value:raise ValueError('DIAGNOSTIC_SCHEMA')
    return dict(value)
