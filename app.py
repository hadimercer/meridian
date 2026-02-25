"""
app.py
Meridian — Workstream Portfolio Health Dashboard
Entry point. Handles routing and session initialisation.
"""

import streamlit as st
from pipeline.auth import is_authenticated

st.set_page_config(
    page_title   = "Meridian",
    page_icon    = "🟢",
    layout       = "wide",
    initial_sidebar_state = "expanded",
)

# ── Session state initialisation ─────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state["user"] = None

# ── Routing ───────────────────────────────────────────────────────────────────
if not is_authenticated():
    st.switch_page("pages/login.py")
else:
    st.switch_page("pages/home.py")
