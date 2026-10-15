"""Narrow positive-proof containment, no historical reclassification."""
from urllib.parse import urlsplit
from .arcus_ui_window import LOCAL_TIMEOUT,CRITERIA_OPERATIONS
from . import finite_acceptance as f


def eligible(row,a):
    from .r0_recovery_proposal import resources,identities
    if row['council'] not in f.ARCUS:return False
    config=f.dated_config(f.UI_CASES['discovery_'+row['council']+'_ui_window'],row['start'],row['end'])
    origin='https://'+config.host;t=a.get('criteria_control_timeout',{})
    if not isinstance(t,dict):return False
    return (a.get('accounting_complete') is True and t==dict(code=LOCAL_TIMEOUT,operation=t.get('operation'),exception_contract='PLAYWRIGHT_LOCATOR_TIMEOUT_V1')
        and t.get('operation') in CRITERIA_OPERATIONS and a.get('source_contract_failure')==LOCAL_TIMEOUT
        and a.get('listing_outcome')==LOCAL_TIMEOUT and a.get('listing_stage')=='CRITERIA'
        and a.get('applied_interval') is None and a.get('case')=='discovery_'+row['council']+'_ui_window'
        and a.get('destination')==config.destination and a.get('requested_interval')==[row['start'],row['end']]
        and a.get('date_semantics')==row['semantics'] and a.get('failure') is None
        and a.get('persistence') is False and a.get('safety_failure') is False and a.get('safety_events')==[]
        and a.get('containment_accounting_verified') is True and resources(row,a) is not None and identities(row,a)
        and a.get('requested_origins')==[origin] and a.get('navigated_origins')==[origin]
        and a.get('navigation_mismatch') is None and a.get('blocked_actions')==[] and a.get('blocked_action_metadata')==[]
        and a.get('blocked_posts')==0 and a.get('cleanup')=='CONTEXT_BROWSER_CLOSED'
        and a.get('process_cleanup')=='CLOSED' and type(a.get('live_owned_survivors'))is int and a['live_owned_survivors']==0
        and a.get('supervisor_limit_hit') is False and type(a.get('supervisor_seconds'))in(int,float)
        and 0<=a['supervisor_seconds']<=45 and a.get('pages')==1 and type(a.get('navigations'))is int
        and 1<=a['navigations']<=2 and type(a.get('public_ui_posts'))is int
        and 0<=a['public_ui_posts']<=a['requests'] and a.get('measured_public_ui_posts')==a['public_ui_posts'])
