"""CSV-safe display copies; never mutate source facts or action identifiers."""
import pandas as pd
import streamlit as st
from app.reporting.csv_safety import safe_dataframe
from app.security.access import require_admitted


def dataframe(data, *args, **kwargs):
    require_admitted()
    frame = data if isinstance(data,pd.DataFrame) else pd.DataFrame(data)
    return st.dataframe(safe_dataframe(frame), *args, **kwargs)


def data_editor(data, *args, **kwargs):
    require_admitted()
    return st.data_editor(safe_dataframe(data), *args, **kwargs)
