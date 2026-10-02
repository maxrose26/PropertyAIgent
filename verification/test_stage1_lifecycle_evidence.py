import pytest
from verification.stage1_lifecycle_evidence import EXPECTED, validate


def fixture():
    rows = [dict(stage=stage, checkout=i+1, checkin=i+1, outstanding=0,
                 transactions=0, new_sessions=1, errors=[]) for i, stage in enumerate(EXPECTED)]
    return {'baseline': 0, 'snapshots': rows}, "PASS 49 AppTest checkpoints; 49 distinct sessions; {'checkout': 49, 'checkin': 49}; outstanding=0\n"


def test_complete():
    evidence, log = fixture()
    assert validate(evidence, log)['checkpoints'] == 49


@pytest.mark.parametrize('stage', EXPECTED)
def test_every_named_checkpoint_required(stage):
    evidence, log = fixture()
    evidence['snapshots'] = [s for s in evidence['snapshots'] if s['stage'] != stage]
    with pytest.raises(ValueError):
        validate(evidence, log)


@pytest.mark.parametrize('mutation', ['marker', 'marker_count', 'truncated', 'duplicate', 'order', 'checkout', 'outstanding', 'transactions', 'errors', 'new_sessions', 'baseline'])
def test_invalid_evidence(mutation):
    evidence, log = fixture()
    if mutation == 'marker': log = ''
    elif mutation == 'marker_count': log = log.replace('49 AppTest', '47 AppTest')
    elif mutation == 'truncated': evidence['snapshots'] = evidence['snapshots'][:-2]
    elif mutation == 'duplicate': evidence['snapshots'][-1] = evidence['snapshots'][-2].copy()
    elif mutation == 'order': evidence['snapshots'].reverse()
    elif mutation == 'baseline': evidence['baseline'] = 1
    else: evidence['snapshots'][-1][mutation] = ['failure'] if mutation == 'errors' else (0 if mutation == 'new_sessions' else 1)
    with pytest.raises(ValueError): validate(evidence, log)
