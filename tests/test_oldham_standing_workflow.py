"""Closed dormant workflow opt-in; no dispatch or production credentials read."""
from pathlib import Path
import yaml

PATH=Path('.github/workflows/stage4-oldham-standing.yml')


def assert_standing_workflow():
    raw=PATH.read_text();w=yaml.load(raw,Loader=yaml.BaseLoader)
    assert set(w['on'])=={'workflow_dispatch'}
    assert w['on']['workflow_dispatch']['inputs']['purpose']['default']=='NOT_AUTHORISED'
    assert w['on']['workflow_dispatch']['inputs']['purpose']['options']==['NOT_AUTHORISED','QUALIFY_STANDING_ACCESS','CAPTURE_SCREENING']
    assert set(w['jobs'])=={'restricted'}
    job=w['jobs']['restricted'];assert job['environment']=='stage4-production-canary' and job['timeout-minutes']=='15'
    assert 'secrets.DATABASE_URL' not in raw and 'secrets.INGESTION_APPLICATION_DATABASE_URL' not in raw
    assert '"$PIN" == "$GITHUB_SHA" && "$PIN" == "$WF"' in raw
    assert '"$GITHUB_REF" == refs/heads/master && "$GITHUB_RUN_ATTEMPT" == 1' in raw
    assert '480s sudo -E bash verification/ingestion_storage/hosted_memory_scope.sh' in raw
    assert '--claim-commit "$CLAIM" --release-id "$RELEASE" --manifest-sha256 "$MANIFEST"' in raw
    assert w['concurrency']['cancel-in-progress']=='false'
    for step in job['steps']:
        if 'secrets.' in str(step):
            assert set(step.get('env',{})) in ({'WORKER','EFFECT'},{'TOKEN','WORKER','EFFECT','CLAIM','RELEASE','MANIFEST','WF'})
            assert 'printf' in step['run'] and 'env -i' in step['run']


def test_dormant_standing_workflow_closed_boundary():assert_standing_workflow()
