"""Run preserved acceptance scripts in an offline synthetic operator context.

Transport adaptation: capture the new delivery helper's exact bytes through
AppTest's old download recorder so every original byte/identity assertion stays
unchanged. This is explicitly NOT browser or HTTP transport acceptance.
"""
import os,sys,tempfile,runpy
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if any(k in os.environ for k in ('DATABASE_URL','OPENAI_API_KEY','ANTHROPIC_API_KEY','SUPABASE_URL')):raise RuntimeError('Reject inherited inputs')
from verification.stage1_test_context import synthetic_context,seed_fixture
from app.db.models import Base
from app.security import access
from app.ui import access as ui_access
from app.ui import protected_download,common
import streamlit as st
original=Base.metadata.create_all
def create_all(bind,*args,**kwargs):
    original(bind,*args,**kwargs);seed_fixture(bind)
mode=sys.argv[1]
with synthetic_context(tempfile.mkdtemp(prefix='stage1-apptest-')) as actor:
    @contextmanager
    def scope():
        with access.actor_scope(actor):yield actor
    def admitted_actor(**kwargs):
        # AppTest script threads require their own explicit context binding.
        access.registry.check(actor)
        access._current.set(actor)
        return actor
    original_get_db=common.get_db
    @contextmanager
    def database_scope():
        with access.actor_scope(actor),original_get_db() as result:yield result
    with patch.object(common,'get_db',database_scope),patch.object(Base.metadata,'create_all',create_all),patch.object(ui_access,'page_scope',scope),patch.object(ui_access,'admitted_actor',admitted_actor),patch.object(protected_download,'download_button',st.download_button):
        if mode=='walkthrough':
            runpy.run_path(str(ROOT/'verification/web_ah/walkthrough.py'),run_name='__main__')
        elif mode=='lifecycle':
            sys.argv=[str(ROOT/'verification/ui_session_apptest.py'),str(ROOT),sys.argv[2]]
            runpy.run_path(sys.argv[0],run_name='__main__')
        else:raise ValueError(mode)
