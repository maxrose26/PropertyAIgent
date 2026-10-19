"""Static properties of the qualification workflow: restricted credentials only, single use, no administrative credential, exact authority; the module and the workflow agree."""
import re
from pathlib import Path
from verification.ingestion_storage import stable_qualification as sq

WORKFLOW=Path('.github/workflows/stage4-stable-credential-qualification-once.yml')


def text():return WORKFLOW.read_text()


def test_only_the_two_restricted_secrets_are_referenced_and_no_administrative_or_write_token():
    t=text()
    assert sorted(set(re.findall(r'secrets\.([A-Z0-9_]+)',t)))==['INGESTION_EFFECT_DATABASE_URL','INGESTION_WORKER_DATABASE_URL']
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL' not in t and 'GITHUB_TOKEN' not in t and 'GH_TOKEN' not in t and 'INGESTION_STORAGE' not in t
    assert re.search(r'permissions:\n  contents: read\n',t) and t.count('permissions:')==1


def test_it_is_a_manual_single_use_job_in_the_protected_environment_pinned_to_the_reviewed_sha():
    t=text()
    assert t.count('workflow_dispatch:')==1 and 'push:' not in t and 'schedule:' not in t and 'pull_request' not in t and 'cron' not in t
    assert 'environment: stage4-production-canary' in t and 'GITHUB_RUN_NUMBER" == 1' in t and 'GITHUB_RUN_ATTEMPT" == 1' in t and 'refs/heads/master' in t
    assert '"$PIN" == "$WF" && "$PIN" == "$GITHUB_SHA"' in t and 'ref: ${{ inputs.reviewed_sha }}' in t and 'persist-credentials: false' in t
    assert sq.AUTHORITY in t and 'NOT_AUTHORISED' in t and 'default: NOT_AUTHORISED' in t


def test_the_module_runs_in_a_clean_environment_with_a_hard_timeout_above_its_own_limit():
    t=text()
    assert 'env -i PATH=/usr/bin:/bin' in t and '-I -B' in t and 'verification.ingestion_storage.stable_qualification' in t
    timeout=int(re.search(r'timeout --kill-after=5s (\d+)s',t).group(1))
    assert timeout>sq.OVERALL_SECONDS and int(re.search(r'timeout-minutes: (\d+)',t).group(1))*60>timeout
    assert 'if: always()' in t and 'retention-days: 30' in t


def test_the_module_refuses_administrative_environment_and_has_no_admin_capability():
    import ast
    tree=ast.parse(Path('verification/ingestion_storage/stable_qualification.py').read_text())
    imported={n.module.split('.')[-1] if isinstance(n,ast.ImportFrom) and n.module else a.name for n in ast.walk(tree) for a in (getattr(n,'names',[]) or [None]) if isinstance(n,(ast.Import,ast.ImportFrom))}
    assert not imported&{'operational_owner','operational_publication','operational_runner','credential_mapping','storage_controller','operational_cleanup'}
    names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}|{n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not names&{'Owner','GitHub','put_secret','teardown','register','Runner'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and 'SELECT' in node.value:
            sql=re.sub(r'has_table_privilege\([^)]*\)','',node.value)
            assert not re.search(r'(ALTER|INSERT|UPDATE|DELETE|GRANT|TRUNCATE|CREATE|DROP|pg_authid)',sql),sql[:60]      # reads only
    assert 'DATABASE_URL' in sq.FORBIDDEN_ENV and 'INGESTION_STORAGE_DATABASE_URL' in sq.FORBIDDEN_ENV
