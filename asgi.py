"""Seismographic as an ASGI app, for hosts that run Python web apps rather than `streamlit run` (e.g. Vercel).

Run it locally with:   uvicorn asgi:app --port 8501
"""

from pathlib import Path

import streamlit as st

app = st.App(Path(__file__).resolve().parent / "streamlit_app.py")
