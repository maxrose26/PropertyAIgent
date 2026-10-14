import pytest
from verification.discovery.arcus_ui_window import public_ui_post, qualify_segment, AURA


def card(ref='PLA-2026-001',key='a1DSl000007WJ1tMAG',valid='02/10/2026'):
    return {'links':[{'text':ref,'href':f'https://arcusbe.manchester.gov.uk/pr/s/detail/{key}?c__r=Arcus_BE_Public_Register'}],
        'fields':[{'label':'Reference','value':ref},{'label':'Valid Date','value':valid}]}


def test_public_ui_transport_is_only_observed_endpoint_and_post():
    assert public_ui_post('POST',AURA,'ordinary browser-generated form')
    for method,url,body in [('PUT',AURA,'x'),('POST',AURA+'/other','x'),('POST',AURA.replace('manchester','other'),'x'),('POST',AURA,'x'*65537)]:
        assert not public_ui_post(method,url,body)


def test_exact_displayed_identity_and_date_literals():
    first,last,total,rows=qualify_segment('Showing 1 to 1 of 1 results',[card()],1)
    assert (first,last,total)==(1,1,1)
    assert rows[0]['validated_date']['literal']=='02/10/2026'
    assert rows[0]['materiality']=='POTENTIALLY_MATERIAL'


def test_pagination_and_identity_fail_closed():
    for marker,cards,first,total in [
        ('Showing 2 to 2 of 2 results',[card()],1,None),
        ('Showing 1 to 1 of 2 results',[card()],1,1),
        ('Showing 1 to 2 of 2 results',[card(),card()],1,None),
        ('Showing 1 to 1 of 1 results',[card(valid='05/10/2026')],1,None),
        ('Showing 1 to 1 of 1 results',[dict(card(),fields=[])],1,None),
        ('Showing 1 to 1 of 1 results',[card(key='wrong')],1,None),
    ]:
        with pytest.raises(ValueError): qualify_segment(marker,cards,first,total)


def test_audit_rejects_partial_or_unbounded_output():
    from verification.discovery.arcus_ui_audit import validate
    from verification.discovery.arcus_ui_window import CASE,DESTINATION
    a=dict(case=CASE,destination=DESTINATION,persistence=False,failure=None,safety_failure=False,safety_events=[],
        cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,supervisor_limit_hit=False,
        enumeration_evidence='COUNT_RECONCILED',applied_interval=['2026-09-28','2026-10-04'],completeness='UNKNOWN',
        requests=20,decoded_bytes=1000,encoded_bytes=800,supervisor_seconds=5,pages=1,navigations=1,
        listing_records=[{'reference':'TEST/26','source_record_id':'X'}],listing_segments=[{'first':1,'last':1,'total':1}])
    assert validate(a)['production_admission'] is False
    for changes in ({'listing_failure':'X'},{'completeness':'COMPLETE'},{'encoded_bytes':30_000_000},{'pages':2},{'navigations':3},
                    {'listing_segments':a['listing_segments']*7}):
        with pytest.raises(ValueError):validate(dict(a,**changes))
