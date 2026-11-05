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
# This release exposes only an explicit owner-click read-only period07 preflight.
# Do not replay a legacy PREPARE_ONCE action when the web process restarts.

app = st.App(Path(__file__).with_name('streamlit_app.py'), middleware=[Middleware(AccessMiddleware)])
