"""Read-only AH evidence captions shared by buyer-facing detail paths."""
from urllib.parse import urlsplit, quote
import streamlit as st


def render_ah_evidence(assessment, ui=st):
    for note in assessment.evidence_notes():
        ui.caption(note)
    url = assessment.count.source_url
    try:
        valid_url = bool(url and urlsplit(url).scheme in ("https", "http") and urlsplit(url).netloc)
    except ValueError:
        valid_url = False
    if valid_url:
        url = quote(url, safe=":/?#=&%+@;,")
        ui.markdown(f"[View reported AH source](<{url}>)")
    else:
        ui.caption("AH source link: not available. A reported classification is not a verified legal position.")
