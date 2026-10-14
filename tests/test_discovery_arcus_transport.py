import pytest
from verification.discovery.arcus_ui_transport import measure_post, MAX_BYTES, AURA, combined_bytes


def run(coro):
    with pytest.raises(StopIteration) as result:coro.send(None)
    return result.value.value


def event(body='message=ordinary',**changes):
    r={'requestId':'fetch-id','networkId':'network-id','request':{'method':'POST','url':AURA+'?r=1','headers':{'Content-Type':'application/x-www-form-urlencoded'},'postData':body}}
    r['request'].update(changes)
    return r


class Client:
    def __init__(self,body=None,fail=False):self.body=body;self.fail=fail;self.calls=[]
    async def send(self,method,args):
        self.calls.append((method,args))
        if self.fail:raise RuntimeError('local protocol unavailable')
        return {'postData':self.body}


def test_omitted_body_is_measured_locally_without_replay():
    a={'decoded_bytes':10,'encoded_bytes':8};c=Client('message=ordinary')
    assert run(measure_post(event(None),c,a)) is None
    assert c.calls==[('Network.getRequestPostData',{'requestId':'network-id'})]
    assert a['outbound_payload_bytes']==16 and a['post_body_cdp_reads']==1
    assert 'ordinary' not in str(a)


def test_aggregate_budget_replaces_unqualified_individual_limit():
    a={'decoded_bytes':100,'encoded_bytes':80};c=Client()
    assert run(measure_post(event('x'*65537),c,a)) is None
    assert combined_bytes(a)==65637 and c.calls==[]
    a={'decoded_bytes':MAX_BYTES-3,'encoded_bytes':10}
    assert run(measure_post(event('abcd'),c,a))=='POST_AGGREGATE_BYTE_LIMIT'
    assert a.get('outbound_payload_bytes',0)==0
    assert run(measure_post(event('x'*(MAX_BYTES+1)),c,{}))=='POST_AGGREGATE_BYTE_LIMIT'


def test_unknown_unqualified_or_ambiguous_payload_cannot_continue():
    assert run(measure_post(event('x',headers={'Content-Type':'application/x-www-form-urlencoded','Content-Encoding':'gzip'}),Client(),{}))=='POST_CONTENT_ENCODING'
    assert run(measure_post(event(None),Client(fail=True),{}))=='POST_BODY_UNAVAILABLE'
    assert run(measure_post(event('x',headers={'Content-Type':'multipart/form-data'}),Client(),{}))=='POST_MEDIA_TYPE'
    assert run(measure_post(event('x',headers={'Content-Type':'application/x-www-form-urlencoded','Content-Length':'2'}),Client(),{}))=='POST_BODY_LENGTH_MISMATCH'
    for changes in ({'method':'PUT'},{'url':AURA+'/other'},{'url':'https://other.example/aura'}):
        c=Client();assert run(measure_post(event(None,**changes),c,{}))=='POST_DESTINATION';assert c.calls==[]
