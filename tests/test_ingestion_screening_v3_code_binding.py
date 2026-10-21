"""Code binding of a saved v3 assessment (proposal section 3): dependency coverage, a pinned digest, line-ending independence, and the production option that removes history from assessment execution. Offline."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.ingestion import listing_screening as ls
from app.ingestion.coordinator import Coordinator
from app.ingestion.ledger import Ledger, digest
from app.ingestion.schema import install
from sqlalchemy import create_engine
from tests.test_ingestion_retained_capture_reconciliation import retained

ROOT = Path(__file__).resolve().parents[1]
# The expected binding of the bound modules at this commit. Changing ANY bound byte (even a comment) changes every new v3 identity: update this constant consciously, in the same change.
PINNED_CODE_BINDING = '4e75a267dd0b7d42fbf89a59778ed555e738c55b8efbede4356248fc23e6f4ec'
PINNED_DIGEST_PROBE = 'f1b44b4a4cc0c90b8371afbc85625e7c6043443caa9bdcfa38a1bfa40ccdc082'
EXCLUDED = {'app/ingestion/ledger.py', 'app/ingestion/schema.py'}      # loaded, deliberately not bound by file (ledger.digest is bound by the probe)


def test_the_code_binding_is_pinned_and_a_change_names_the_file():
    got = ls.code_binding()
    per_file = {rel: ls.lf_sha256((ROOT / rel).read_bytes()) for rel in ls.BOUND_MODULES}
    assert got == PINNED_CODE_BINDING, 'a bound module changed; update PINNED_CODE_BINDING consciously. current per-file digests: %s' % json.dumps(per_file, sort_keys=True)
    assert ls.digest_probe() == PINNED_DIGEST_PROBE
    config = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10).config()
    assert config['code_binding'] == got and config['digest_probe'] == PINNED_DIGEST_PROBE


@pytest.mark.parametrize('rel', ls.BOUND_MODULES)
def test_line_endings_do_not_change_a_file_digest_but_stray_carriage_returns_and_boms_are_refused(rel):
    raw = (ROOT / rel).read_bytes()
    lf = raw.replace(b'\r\n', b'\n')
    crlf = lf.replace(b'\n', b'\r\n')
    assert ls.lf_sha256(raw) == ls.lf_sha256(lf) == ls.lf_sha256(crlf)      # Windows autocrlf checkout, Linux checkout and CRLF-transformed copy all agree
    assert not lf.startswith(b'\xef\xbb\xbf')      # no byte-order mark
    assert b'\r' not in lf      # no lone carriage return left after normalisation


def test_an_edit_to_a_bound_byte_changes_the_binding(tmp_path, monkeypatch):
    base = tmp_path / 'app/ingestion'
    base.mkdir(parents=True)
    (tmp_path / 'app/scrapers').mkdir(parents=True)
    for rel in ls.BOUND_MODULES:
        target = tmp_path / rel
        target.write_bytes((ROOT / rel).read_bytes())
    # a copy of the module tree gives the same binding; one extra byte in the qualifier gives a different one
    monkeypatch.setattr(ls, '__file__', str(tmp_path / 'app/ingestion/listing_screening.py'))
    same = ls.code_binding()
    assert same == ls.code_binding() and same == PINNED_CODE_BINDING
    (tmp_path / 'app/scrapers/unit_filter.py').write_bytes((ROOT / 'app/scrapers/unit_filter.py').read_bytes() + b'# x\n')
    assert ls.code_binding() != same
    (tmp_path / 'app/scrapers/unit_filter.py').unlink()
    with pytest.raises(ValueError, match='CODE_BINDING_UNAVAILABLE'):
        ls.code_binding()      # a missing bound file fails closed


def test_the_runtime_closure_of_the_assessment_is_fully_bound():
    """In a fresh interpreter, run the v3 screen and the identity over EVERY retained record (so lazy, branch-dependent imports are exercised) and require every loaded repository module to be bound or a declared exclusion."""
    _, receipt = retained()
    code = ("import sys,json\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "recs=json.loads(sys.stdin.read())\n"
            "before=set(sys.modules)\n"
            "from app.ingestion import listing_screening as ls\n"
            "rule=ls.ScreeningRule(ls.RULE_V3,unit_threshold=10)\n"
            "for r in recs:\n"
            "    rule.screen(r);ls.assessment_identity(r,rule)\n"
            "mods=sorted(m for m in set(sys.modules)-before if m.split('.')[0] in ('app','verification'))\n"
            "files=sorted(sys.modules[m].__file__ for m in mods if getattr(sys.modules[m],'__file__',None))\n"
            "print(json.dumps(files))\n")
    done = subprocess.run([sys.executable, '-I', '-c', code, str(ROOT)], input=json.dumps(receipt['records']), capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-400:]
    loaded = {str(Path(f).resolve().relative_to(ROOT)).replace('\\', '/') for f in json.loads(done.stdout.strip().splitlines()[-1])}
    assert set(ls.BOUND_MODULES) <= loaded
    unbound = {p for p in loaded if p not in set(ls.BOUND_MODULES) and p not in EXCLUDED and not p.endswith('__init__.py')}
    assert not unbound, 'a module entered the assessment path without being bound: %s' % sorted(unbound)


def test_the_embedded_v1_result_is_covered_by_its_own_digest_and_by_the_code(tmp_path):
    _, receipt = retained()
    engine = create_engine('sqlite:///:memory:')
    install(engine)
    ledger = Ledger(engine)
    co = Coordinator(ledger, {}, screening_rules={ls.V3_CONTRACT: ls.ScreeningRule(ls.RULE_V3, unit_threshold=10)})
    key = ledger.enqueue(dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED'), 'LISTING_METADATA', contract='fixture-listing')
    ledger.grant('INGESTION_TEST_c', [key], contracts=['fixture-listing'], expires_at=ledger.clock() + 600)
    claim = ledger.claim(key, 'w', 'INGESTION_TEST_c')
    ledger.checkpoint(claim, receipt)
    children = co._materialize(claim, receipt)
    ledger.grant('INGESTION_TEST_s', children, contracts=[ls.V3_CONTRACT], expires_at=ledger.clock() + 600)
    result = co.screening(ledger.claim(children[0], 'w', 'INGESTION_TEST_s'))
    assert result['qualifier_output_sha256'] == digest(ls.qualifier_output_of(result)) and 'count_assessment' not in ls.qualifier_output_of(result)
    assert result['capture_checkpoint_sha256'] == digest(receipt) == 'd5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee'
    assert result['config']['code_binding'] == ls.code_binding()


def test_production_option_removes_history_scans_from_assessment_execution(monkeypatch):
    import app.ingestion.screening_projection as sp
    _, receipt = retained()
    engine = create_engine('sqlite:///:memory:')
    install(engine)
    ledger = Ledger(engine)
    rule = ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=False)
    assert rule.link_related is False and rule.config() == ls.ScreeningRule(ls.RULE_V3, unit_threshold=10).config()      # not decision-affecting: same identity
    for bad in ('no', 1, None):
        with pytest.raises(ValueError, match='INVALID_LINK_RELATED'):
            ls.ScreeningRule(ls.RULE_V3, unit_threshold=10, link_related=bad)
    monkeypatch.setattr(sp, 'screening_items', lambda *a, **k: pytest.fail('assessment execution scanned the ledger'))
    co = Coordinator(ledger, {}, screening_rules={ls.V3_CONTRACT: rule})
    key = ledger.enqueue(dict(kind='DISCOVERY_SCOPE', council='bolton', start='2026-09-28', end='2026-10-04', semantics='RECEIVED'), 'LISTING_METADATA', contract='fixture-listing')
    ledger.grant('INGESTION_TEST_c', [key], contracts=['fixture-listing'], expires_at=ledger.clock() + 600)
    claim = ledger.claim(key, 'w', 'INGESTION_TEST_c')
    ledger.checkpoint(claim, receipt)
    children = co._materialize(claim, receipt)
    ledger.grant('INGESTION_TEST_s', children, contracts=[ls.V3_CONTRACT], expires_at=ledger.clock() + 600)
    results = [co.screening(ledger.claim(k, 'w', 'INGESTION_TEST_s')) for k in children]
    assert len(results) == 24 and all('related_assessments' not in r and 'related_assessments_total' not in r for r in results)
    assert max(len(json.dumps(r)) for r in results) < 131072      # inside the SQL checkpoint bound


def test_the_qualifier_output_key_set_is_exactly_what_the_v1_screen_returns_for_every_retained_record():
    _, receipt = retained()
    for r in receipt['records']:
        assert sorted(set(ls._screen_v1(r)) - {'rule_version'}) == sorted(ls.V1_RESULT_KEYS)      # a new v1 key must be consciously added to the bound output
