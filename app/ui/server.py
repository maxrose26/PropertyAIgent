"""Supported launch: streamlit run app/ui/server.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
from starlette.middleware import Middleware
from app.security.middleware import AccessMiddleware

# Read-only verification of the one-time owner configuration. No schema,
# access or collection mutation occurs at application startup.
from app.owner_intake import startup_configuration_readback
startup_configuration_readback()
from app.owner_intake_control import startup_prepare
startup_prepare()

app = st.App(Path(__file__).with_name('streamlit_app.py'), middleware=[Middleware(AccessMiddleware)])
