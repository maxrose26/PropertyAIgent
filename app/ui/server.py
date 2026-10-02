"""Supported launch: streamlit run app/ui/server.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
from starlette.middleware import Middleware
from app.security.middleware import AccessMiddleware

app = st.App(Path(__file__).with_name('streamlit_app.py'), middleware=[Middleware(AccessMiddleware)])
