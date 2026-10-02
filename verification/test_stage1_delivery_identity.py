from types import SimpleNamespace
import pytest
from streamlit.components.v2.bidi_component.main import _make_trigger_id
from app.ui import protected_download as delivery


@pytest.fixture
def capture(monkeypatch):
    state = {'active_buyer_key': 'buyer-a'}
    actor = SimpleNamespace(lease_id='normal-lease', revision='revision-a')
    calls = []
    monkeypatch.setattr(delivery.st, 'session_state', state)
    monkeypatch.setattr(delivery, 'require_admitted', lambda: actor)
    monkeypatch.setattr(delivery, '_DELIVER', lambda **kwargs: calls.append(kwargs))
    return actor, state, calls


@pytest.mark.parametrize('lease', ['normal-lease', '__', 'a__b', 'a___b'])
def test_safe_stable_component_id(capture, lease):
    actor, state, calls = capture
    actor.lease_id = lease
    for _ in range(2): delivery._payload(b'data', 'text/csv', 'report.csv', key='download_selected_report__x')
    assert calls[0] == calls[1]
    key = calls[0]['key']
    assert '__' not in key
    assert 'download_selected_report' in key
    assert _make_trigger_id(key, 'event')


@pytest.mark.parametrize('field', ['lease', 'revision', 'buyer', 'key', 'data', 'mime', 'filename', 'image', 'width'])
def test_distinct_contexts(capture, field):
    actor, state, calls = capture
    kwargs = dict(data=b'a', mime='text/csv', filename='a.csv', key='x__y')
    delivery._payload(**kwargs)
    if field == 'lease': actor.lease_id = 'other'
    elif field == 'revision': actor.revision = 'other'
    elif field == 'buyer': state['active_buyer_key'] = 'other'
    else: kwargs[field] = dict(key='x_y', data=b'b', mime='application/pdf', filename='b.csv', image=True, width=321)[field]
    delivery._payload(**kwargs)
    assert calls[0]['key'] != calls[1]['key']


@pytest.mark.parametrize('entry', ['payload', 'image', 'download'])
def test_denied_before_delivery(capture, monkeypatch, entry):
    def deny(): raise PermissionError('not admitted')
    monkeypatch.setattr(delivery, 'require_admitted', deny)
    with pytest.raises(PermissionError):
        if entry == 'payload': delivery._payload(b'a', 'text/csv', 'a.csv')
        elif entry == 'image': delivery.image('/not/read')
        else: delivery.download_button('save', b'a')
    assert not capture[2]


def test_rechecked_before_component(capture, monkeypatch):
    calls = 0
    def admission():
        nonlocal calls
        calls += 1
        if calls == 2: raise PermissionError('revoked')
        return capture[0]
    monkeypatch.setattr(delivery, 'require_admitted', admission)
    with pytest.raises(PermissionError): delivery._payload(b'a', 'text/csv', 'a.csv')
    assert not capture[2]
