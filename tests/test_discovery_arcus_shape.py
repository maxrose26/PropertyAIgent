import base64
import json
from urllib.parse import urlsplit, parse_qs
from verification.discovery.manchester_shape import DESTINATION, CASE, FILTERS
from verification.direct_reference.instrumented_probe import CASES, request_failure


def test_observed_manchester_query_is_fixed_and_unfiltered():
    payload = json.loads(base64.b64decode(parse_qs(urlsplit(DESTINATION).query)['c__q'][0]))
    filters = payload['requests'][0]['searchFilters']
    populated = [(f['fieldDeveloperName'], f['fieldValue']) for f in filters if f['fieldValue']]
    assert populated == [('PA_ADV_DateValidFrom', '2026-09-28'), ('PA_ADV_DateValidTo', '2026-10-04')]
    assert FILTERS[0][0] == 'arcusbuiltenv__Site_Address__c'  # not Salford's custom address field
    assert CASES[CASE] == (None, None, DESTINATION)
    assert request_failure(DESTINATION, 'GET', 'Document', DESTINATION, 1) is None
    assert request_failure(DESTINATION, 'POST', 'XHR', DESTINATION, 2) == 'UNREVIEWED_METHOD'
    assert request_failure('https://example.com/', 'GET', 'Document', DESTINATION, 1) == 'UNADMITTED_ORIGIN'


def test_shape_observation_cannot_claim_coverage_or_hide_resource_failure():
    from verification.discovery.shape_audit import validate
    import pytest
    a = dict(case=CASE, destination=DESTINATION, application_id=None, reference=None,
        exact_reference=False, fields=None, persistence=False, completeness='UNKNOWN', failure='UNREVIEWED_METHOD',
        safety_failure=False, safety_events=[], supervisor_limit_hit=False,
        cleanup='CONTEXT_BROWSER_CLOSED', process_cleanup='CLOSED', live_owned_survivors=0,
        requests=20, decoded_bytes=1000, encoded_bytes=1000, pages=1, navigations=1,
        blocked_posts=1, supervisor_seconds=10, blocked_action_metadata=[{'method':'unqualified'}])
    assert validate(a)['production_admission'] is False
    for changes in ({'completeness':'COMPLETE'}, {'live_owned_survivors':1},
                    {'fields':{}}, {'exact_reference':True}, {'requests':81}, {'safety_failure':True}, {'record_http_probe':{}}):
        with pytest.raises(ValueError): validate(dict(a, **changes))


def test_only_observed_guest_bootstrap_getters_can_execute():
    from urllib.parse import urlencode
    from verification.discovery.manchester_search_shape import bootstrap_read_allowed, HOST, APEX
    url='https://arcusbe.manchester.gov.uk/pr/s/sfsites/aura'
    def body(a,token='null'):
        return urlencode({'aura.token':token,'message':json.dumps({'actions':[a]})})
    host={'descriptor':HOST,'params':{}}
    assert bootstrap_read_allowed(url,body(host))
    assert bootstrap_read_allowed(url,body({'descriptor':HOST}))
    assert not bootstrap_read_allowed(url,body(host,'secret'))
    assert not bootstrap_read_allowed(url.replace('manchester','evil'),body(host))
    params=dict(namespace='',classname='DSHLC_HeaderCont',method='isSelfRegistrationEnabled',cacheable=True,isContinuation=False)
    assert bootstrap_read_allowed(url,body({'descriptor':APEX,'params':params}))
    assert bootstrap_read_allowed(url,body({'descriptor':APEX,'params':dict(params,cacheable=False)}))
    for changes in ({'method':'registerUser'},{'cacheable':'true'},{'params':{'email':'private'}},{'namespace':'other'}):
        assert not bootstrap_read_allowed(url,body({'descriptor':APEX,'params':dict(params,**changes)}))
