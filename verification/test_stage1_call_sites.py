"""Structural inventory gates complement runtime denial/positive tests."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_no_native_private_media_delivery():
    forbidden=[]
    for path in (ROOT/'app/ui').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='st' and node.func.attr in ('image','download_button'):
                forbidden.append(f'{path.relative_to(ROOT)}:{node.lineno}')
    assert forbidden==[]

def test_all_ten_page_scopes_preserved():
    pages=list((ROOT/'app/ui/pages').glob('*.py'))
    assert len(pages)==10
    for path in pages:
        tree=ast.parse(path.read_text())
        scopes=[n for n in ast.walk(tree) if isinstance(n,ast.With) and any(isinstance(item.context_expr,ast.Call) and isinstance(item.context_expr.func,ast.Name) and item.context_expr.func.id=='page_scope' for item in n.items)]
        assert len(scopes)==1,path
        assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='get_db' for n in ast.walk(scopes[0])),path

def test_testing_adapters_never_imported_by_application():
    for path in (ROOT/'app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom):assert not (node.module or '').startswith('verification'),path
            if isinstance(node,ast.Import):assert all(not alias.name.startswith('verification') for alias in node.names),path
