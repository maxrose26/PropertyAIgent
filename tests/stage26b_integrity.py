"""Explicit historical AND current dependency contract. Test-only, no runtime hooks."""
import ast
import hashlib
import json
from pathlib import Path

RECONCILIATION = 'app/reporting/scheme_reconciliation.py'
MANIFEST = 'tests/fixtures/stage26b/integrity/b11-successor.json'
MANIFEST_SHA256 = 'e399c85982853d54f13db4102fa44af2a402d296a522652a5a1cb2de94eeb109'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def definitions(text):
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            assert node.name not in result, f'duplicate definition: {node.name}'
            result[node.name] = ast.get_source_segment(text, node)
    return result


def assert_historical_and_successor(root, historical_pin):
    """Conjunction, never an archived-hash substitute for the live dependency.

    Immutable v6/v7 archive + original supplied oracle hash + named current B1
    dependency pins. All other original whole-module pins stay at their old gate.
    """
    text = (root / MANIFEST).read_text(encoding='utf-8')
    assert digest(text) == MANIFEST_SHA256, 'successor manifest requires explicit version review'
    contract = json.loads(text)
    assert contract['version'] == 'stage26b-b11-reconciliation-v1'
    predecessor = contract['predecessor']
    prior_text = (root / predecessor['fixture']).read_text(encoding='utf-8')
    assert digest(prior_text) == predecessor['sha256'] == '2ee0824f3e606bd28a73e18ea80cdcc1ee7a86b694010e2b95327a9eed293156'
    prior = json.loads(prior_text)
    assert prior['version'] == predecessor['version'] == 'stage26b-b1-reconciliation-v1'
    for key in ('historical', 'definition_pins', 'binding_envelopes', 'decorator_pins', 'intentional_reconciliation_delta'):
        assert contract[key] == prior[key], f'B1.1 changed unrelated integrity contract: {key}'
    historical = contract['historical']
    source = (root / historical['fixture']).read_text(encoding='utf-8')
    assert digest(source) == historical_pin == historical['sha256'], 'historical source altered'
    raw = source.encode('utf-8')
    assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == historical['git_blob']
    # Constants consumed by the frozen policy/adapters remain live and unchanged.
    def facts(source):
        return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(source).body
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in ('FACT_RESOLVED','FACT_CONFLICT','FACT_NOT_DETERMINED')}
    assert facts((root / RECONCILIATION).read_text()) == facts(source)
    historical_defs = definitions(source)
    current_defs = definitions((root / RECONCILIATION).read_text())
    changed = set(contract['intentional_reconciliation_delta'])
    assert set(current_defs) == set(historical_defs) | changed
    for name in set(historical_defs) - changed:
        assert ast.dump(ast.parse(current_defs[name])) == ast.dump(ast.parse(historical_defs[name])), f'Unreviewed reconciliation change: {name}'
    for path, pin in contract['binding_envelopes'].items():
        tree = ast.parse((root / path).read_text())
        decorators = {n.name: digest(ast.dump(ast.Module(body=n.decorator_list,type_ignores=[])))
                      for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        assert decorators == contract['decorator_pins'][path], f'Definition binding/decorator changed: {path}'
        tree.body = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        assert digest(ast.dump(tree, include_attributes=False)) == pin, f'Execution binding changed: {path}'
    for path, pins in contract['definition_pins'].items():
        current = definitions((root / path).read_text(encoding='utf-8'))
        for name, pin in pins.items():
            assert name in current and digest(current[name]) == pin, f'B1 dependency changed: {path}:{name}'
    for path, pin in contract['module_pins'].items():
        assert digest((root / path).read_text(encoding='utf-8')) == pin, f'B1 eligibility changed: {path}'
