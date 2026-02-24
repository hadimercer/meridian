"""
pages/workstream.py
Workstream detail view — tabs: Overview, Milestones, Budget, Blockers, Updates, Team.
"""

import streamlit as st
from pipeline.auth import require_auth

require_auth()

workstream_id = st.query_params.get("id", None)

if not workstream_id:
    st.error("No workstream specified.")
    st.stop()

# TODO: implement six-tab workstream detail view
st.title("Workstream Detail")
st.caption(f"Workstream ID: {workstream_id}")
st.info("Workstream detail — coming in build phase.")
