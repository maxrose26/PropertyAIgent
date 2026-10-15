import json
from pathlib import Path
import sys
from .arcus_ui_window import CASE, DESTINATION
from .arcus_ui_config import UI_CASES
from .arcus_ui_transport import combined_bytes, MAX_BYTES


def validate(a,config=None):
    config=UI_CASES.get(a.get('case')) if config is None else config
    if config is None:raise ValueError('unadmitted case')
    if (a.get('destination')!=config.destination or a.get('persistence') is not False
        or a.get('failure') is not None or a.get('safety_failure') is not False or a.get('safety_events')!=[]
        or a.get('cleanup')!='CONTEXT_BROWSER_CLOSED' or a.get('process_cleanup')!='CLOSED'
        or a.get('live_owned_survivors')!=0 or a.get('supervisor_limit_hit') is not False
        or a.get('enumeration_evidence')!='COUNT_RECONCILED' or a.get('listing_failure') is not None
        or a.get('completeness')!='UNKNOWN'
        or a.get('applied_interval')!=[config.start,config.end]): raise ValueError('UI window failed')
    if not (1<=a['requests']<=80 and 0<=a['decoded_bytes']<=20*1024*1024 and 0<=a['supervisor_seconds']<=45):
        raise ValueError('UI resource bound')
    if not (0<=a['encoded_bytes']<=20*1024*1024 and a['pages']==1 and 1<=a['navigations']<=2):
        raise ValueError('UI navigation/wire bound')
    if (type(a.get('outbound_payload_bytes')) is not int or a['outbound_payload_bytes']<0
        or combined_bytes(a)>MAX_BYTES or a.get('measured_public_ui_posts')!=a.get('public_ui_posts')
        or not 1<=a.get('public_ui_posts',0)<=a['requests']):
        raise ValueError('UI outbound accounting')
    rows=a['listing_records'];pages=a['listing_segments']
    if not 1<=len(pages)<=6: raise ValueError('segment bound')
    if not pages or pages[-1]['last']!=pages[-1]['total'] or len(rows)!=pages[-1]['total']: raise ValueError('total mismatch')
    if not rows:
        if (pages!=[dict(ordinal=1,first=0,last=0,total=0,evidence_sha256=__import__('hashlib').sha256(b'No results found').hexdigest())]
            or a.get('explicit_zero_evidence')!='EXACT_VISIBLE_ZERO_AND_RETAINED_CRITERIA_NO_ROWS_OR_NEXT'):
            raise ValueError('zero evidence')
        return {'outcome':'PUBLIC_UI_EXPLICIT_ZERO_AND_CRITERIA_QUALIFIED','completeness':'UNKNOWN',
            'source_registry_qualified':False,'production_admission':False,'records':0,'segments':1}
    cursor=1; total=pages[-1]['total']
    for segment in pages:
        if segment['first']!=cursor or segment['last']<cursor or segment['total']!=total:
            raise ValueError('segment continuity')
        cursor=segment['last']+1
    if len({r['reference'] for r in rows})!=len(rows) or len({r['source_record_id'] for r in rows})!=len(rows):
        raise ValueError('duplicate identities')
    return {'outcome':'PUBLIC_UI_COUNT_AND_IDENTITY_QUALIFIED','completeness':'UNKNOWN',
        'source_registry_qualified':False,'production_admission':False,'records':len(rows),'segments':len(pages)}


if __name__=='__main__':
    p=Path(sys.argv[1])
    if p.stat().st_size>=65536: raise ValueError('audit size')
    print(json.dumps(validate(json.loads(p.read_bytes()))))
