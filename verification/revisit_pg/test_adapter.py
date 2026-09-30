"""Synthetic Idox-shaped recordings: no claim of real portal capture coverage."""
import json
import socket
import time
import pytest
from app.revisit.idox import RecordedIdox, Deferred
from app.revisit.stage import maybe_run_recorded_stage

HTML = b'<table><tr><th>Description</th><th>Document Type</th></tr><tr><td><a href="/statement.pdf">Affordable Housing Statement</a></td><td>Statement</td></tr></table>'

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args,**kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket,'socket',deny)
    monkeypatch.setattr(socket,'create_connection',deny)


def ticket(stage='documents',reference='dc/093884'):
    return dict(council='stockport',reference=reference,stage=stage,cursor='start')


def adapter(body=b'72 retirement apartments plus 10 private houses', status=200, **limits):
    return RecordedIdox({'stockport/dc/093884/register':{'status':200,'chunks':[HTML]},
        'https://recorded.invalid/statement.pdf':{'status':status,'chunks':[body]}},time.monotonic()+10,**limits)


def test_existing_idox_register_parser_finds_statement_without_summary_change():
    result=adapter().fetch(ticket())
    assert result['documents'][0]['title']=='Affordable Housing Statement'
    assert result['documents'][0]['reference']=='dc/093884'
    assert result['documents'][0]['proposed']=={}
    assert result['documents'][0]['stage']=='unreviewed_document'


def test_same_url_is_read_again_not_cached():
    a=adapter(b'original')
    first=a.fetch(ticket())
    a.recordings['https://recorded.invalid/statement.pdf']['chunks']=[b'revised']
    second=a.fetch(ticket())
    assert first['documents'][0]['url']==second['documents'][0]['url']
    assert first['documents'][0]['body']!=second['documents'][0]['body']
    assert a.calls==4


@pytest.mark.parametrize('status',[304,403,404,429,500])
def test_inaccessible_or_validator_only_is_not_checked(status):
    with pytest.raises(RuntimeError,match='not verified'):
        adapter(status=status).fetch(ticket())


def test_body_cap_stops_stream_and_counts_attempted_bytes():
    a=adapter(b'x'*5000)
    with pytest.raises(Deferred,match='byte budget'):
        a.fetch(ticket())
    assert a.bytes==len(HTML)+4097


def test_total_bytes_and_requests_bound_repeated_unchanged_downloads():
    a=adapter(requests=2)
    a.fetch(ticket())
    with pytest.raises(Deferred,match='budget'):
        a.fetch(ticket())
    a=adapter(total_bytes=len(HTML)+2)
    with pytest.raises(Deferred):
        a.fetch(ticket())


def test_expired_time_never_fetches():
    a=adapter(); a.deadline=0
    with pytest.raises(Deferred):a.fetch(ticket())
    assert a.calls==0


def test_unrecognised_register_not_empty_success():
    a=adapter();a.recordings['stockport/dc/093884/register']['chunks']=[b'access denied']
    with pytest.raises(RuntimeError,match='register'):a.fetch(ticket())


def test_chain_recordings_keep_each_reference_and_route_separate():
    records={}
    for root,child,kind in [('dc/085997','dc/093884','variation'),('dc/093884','dc/094889','discharge')]:
        data=dict(next=None,edges=[dict(council='stockport',reference=child,type=kind,
            citation='synthetic explicit reference '+root,confidence='verified_reference')])
        records['stockport/'+root+'/relationships/start']=dict(status=200,chunks=[json.dumps(data).encode()])
    a=RecordedIdox(records,time.monotonic()+10)
    assert a.fetch(ticket('relationships','dc/085997'))['edges'][0]['reference']=='dc/093884'
    assert a.fetch(ticket('relationships','dc/093884'))['edges'][0]['type']=='discharge'


def test_hyde_body_not_substituted_when_recording_missing():
    with pytest.raises(RuntimeError,match='unavailable'):
        adapter().fetch(ticket(reference='dc/098428'))


def test_unconfigured_entry_is_dormant_without_database(monkeypatch):
    monkeypatch.delenv('PROPERTYAIGENT_REVISIT_RECORDING',raising=False)
    assert maybe_run_recorded_stage(None,'stockport')=={'outcome':'dormant'}


def test_production_recording_rejected_before_file_or_database(monkeypatch):
    monkeypatch.setenv('RENDER','true');monkeypatch.setenv('PROPERTYAIGENT_REVISIT_RECORDING','does-not-exist')
    with pytest.raises(RuntimeError,match='local-only'):
        maybe_run_recorded_stage(None,'stockport')
