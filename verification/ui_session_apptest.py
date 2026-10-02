"""Offline lifecycle regression, usable unchanged against a selected old checkout.

Run under env -i: python verification/ui_session_apptest.py ROOT OUTPUT.json
Retains sessions and AppTests strongly; asserts release before any teardown.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(sys.argv[1]).resolve()
OUTPUT = Path(sys.argv[2]).resolve()
if any(k in os.environ for k in ('DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'SUPABASE_URL')):
    raise RuntimeError('Reject inherited database/model inputs; run under env -i')
if any(p for p in ROOT.glob('.env*') if p.name != '.env.example'):
    raise RuntimeError('Reject repository environment files')
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
fixture = Path(tempfile.mkdtemp(prefix='ui-session-regression-')) / 'disposable.sqlite'
os.environ.update(DATABASE_URL='sqlite:///' + str(fixture), PYTHON_DOTENV_DISABLED='1')
def no_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('Offline acceptance forbids outbound network')
sys.addaudithook(no_network)

from sqlalchemy import event, text
from streamlit.testing.v1 import AppTest
from app.db import session as db
from app.db.models import Base
from app.ui import common

engine = db.get_engine()
Base.metadata.create_all(engine)
sessions, apps, snapshots = [], [], []
counts = {'checkout': 0, 'checkin': 0}
for name in counts:
    event.listen(engine, name, lambda *args, name=name: counts.__setitem__(name, counts[name] + 1))
original_get_session = common.get_session
def acquire():
    session = original_get_session()
    sessions.append(session)
    return session
common.get_session = acquire
baseline = engine.pool.checkedout()

def run(app, stage):
    before = len(sessions)
    app.run(timeout=30)
    snapshot = {'stage': stage, **counts, 'outstanding': engine.pool.checkedout(),
                'transactions': sum(s.in_transaction() for s in sessions),
                'new_sessions': len(sessions) - before,
                'errors': [e.message for e in app.exception]}
    snapshots.append(snapshot)
    OUTPUT.write_text(json.dumps({'baseline': baseline, 'snapshots': snapshots}, indent=2))
    assert not app.exception, snapshot
    assert snapshot['outstanding'] == baseline, snapshot
    assert snapshot['transactions'] == 0, snapshot
    assert counts['checkout'] == counts['checkin'], snapshot
    assert snapshot['new_sessions'] >= 1, snapshot

router = str(ROOT / 'app/ui/streamlit_app.py')
a = AppTest.from_file(router)
apps.append(a)
run(a, 'dashboard')
for i in range(18):
    run(a, f'rerun-{i}')
for page in ('0_Explore', '1_Scheme_Detail', '2_Review_Site_Links', '3_Local_Plan_Sites',
             '3b_Shortlist', '4_Council_Dashboard', '5_Council_Intelligence',
             '6_Council_Intelligence_Detail', '00_Dashboard'):
    a.switch_page(f'pages/{page}.py')
    run(a, f'navigation-{page}')
for i in range(18):
    a = AppTest.from_file(router)
    apps.append(a)
    run(a, f'independent-{i}')
# Register the otherwise unlisted review page with the same relative page paths.
# The temporary entrypoint lives outside the source checkout.
(fixture.parent / 'pages').symlink_to(ROOT / 'app/ui/pages', target_is_directory=True)
review_router = fixture.parent / 'review_router.py'
review_router.write_text(
    "import streamlit as st\nst.navigation(["
    + ",".join(
        f"st.Page({'pages/' + p.name!r}, default={p.name.startswith('2b_')!r})"
        for p in sorted((ROOT / 'app/ui/pages').glob('*.py'))
    ) + "]).run()"
)
a = AppTest.from_file(str(review_router))
apps.append(a)
run(a, 'allocation-site-matches')
for action in ('stop', 'rerun'):
    a = AppTest.from_string('''
import streamlit as st
from sqlalchemy import text
from app.ui.common import get_db
with get_db() as (session, settings):
    session.execute(text('select 1'))
    if not st.session_state.get('interrupted'):
        st.session_state['interrupted'] = True
        st.ACTION()
    st.write('complete')
'''.replace('ACTION', action))
    apps.append(a)
    run(a, action)
assert len({id(s) for s in sessions}) == len(sessions)
print(f'PASS {len(snapshots)} AppTest checkpoints; {len(sessions)} distinct sessions; {counts}; outstanding=0')
