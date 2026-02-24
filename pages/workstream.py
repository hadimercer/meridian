"""
pages/workstream.py
Workstream detail view — tabs: Overview, Milestones, Budget, Blockers, Updates, Team.
"""

import streamlit as st
import pandas as pd
from pipeline.auth import require_auth, get_current_user_id, get_user_role, is_contributor_or_above
from pipeline.db import query_df


def rag_badge(status: str) -> str:
    """Return the uppercase RAG status label."""
    return str(status or "unknown").upper()


require_auth()

workstream_id = st.query_params.get("id", None)
if workstream_id is None:
    st.error("No workstream specified.")
    st.stop()

if isinstance(workstream_id, list):
    workstream_id = workstream_id[0] if workstream_id else None
if not workstream_id:
    st.error("No workstream specified.")
    st.stop()

df = query_df(
    """
    SELECT w.*, wz.q1_work_type, wz.q2_deadline_nature, wz.q8_update_frequency,
           r.rag_status, r.composite_score, r.schedule_score,
           r.budget_score, r.blocker_score, r.is_stale
    FROM workstreams w
    LEFT JOIN wizard_config wz ON wz.workstream_id = w.id
    LEFT JOIN rag_scores r ON r.workstream_id = w.id
    WHERE w.id = %s
    """,
    (workstream_id,),
)

if df.empty:
    st.error("Workstream not found.")
    st.stop()

ws = df.iloc[0].to_dict()

user_role = get_user_role(workstream_id, get_current_user_id())
if user_role is None:
    st.error("You don't have access to this workstream.")
    st.stop()

status = str(ws.get("rag_status") or "unknown").lower()
rag_colours = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}
rag_colour = rag_colours.get(status, "#888")

end_date = pd.to_datetime(ws.get("end_date"), errors="coerce")
if pd.isna(end_date):
    deadline_text = "No deadline set"
else:
    if end_date.tzinfo is None:
        end_date = end_date.tz_localize("UTC")
    else:
        end_date = end_date.tz_convert("UTC")

    today_utc = pd.Timestamp.now(tz="UTC").normalize()
    days_to_deadline = int((end_date.normalize() - today_utc).days)
    if days_to_deadline >= 0:
        deadline_text = f"{days_to_deadline} days to deadline"
    else:
        deadline_text = f"{abs(days_to_deadline)} days overdue"

col_back, col_title, col_rag, col_deadline = st.columns([1.2, 4.0, 1.3, 1.8])

with col_back:
    if st.button("← Portfolio"):
        st.switch_page("pages/dashboard.py")

with col_title:
    st.markdown(f"# {ws.get('name', 'Untitled Workstream')}")

with col_rag:
    st.markdown(
        f"""
        <div style="margin-top: 0.7rem;">
            <span style="background:{rag_colour}; color:#FFFFFF; padding:0.35rem 0.75rem; border-radius:999px; font-weight:600; font-size:0.85rem;">
                {rag_badge(status)}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_deadline:
    st.markdown(
        f"""<div style="margin-top: 0.8rem; font-weight:600;">{deadline_text}</div>""",
        unsafe_allow_html=True,
    )

is_stale = ws.get("is_stale")
if pd.notna(is_stale) and bool(is_stale):
    st.warning("This workstream is stale and needs an update.")

# is_contributor_or_above is imported for upcoming Phase 4 tab actions/permissions.
_ = is_contributor_or_above

tab_overview, tab_milestones, tab_budget, tab_blockers, tab_updates, tab_team = st.tabs([
    " Overview", " Milestones", " Budget",
    " Blockers", " Updates", " Team"
])

with tab_overview:
    # PHASE 4 PROMPT 8 — Overview tab content goes here
    st.info("Overview tab — coming in Phase 4.")

with tab_milestones:
    # PHASE 4 PROMPT 9 — Milestones tab content goes here
    st.info("Milestones tab — coming in Phase 4.")

with tab_budget:
    # PHASE 4 PROMPT 10 — Budget tab content goes here
    st.info("Budget tab — coming in Phase 4.")

with tab_blockers:
    # PHASE 4 PROMPT 11 — Blockers tab content goes here
    st.info("Blockers tab — coming in Phase 4.")

with tab_updates:
    # PHASE 4 PROMPT 12 — Updates tab content goes here
    st.info("Updates tab — coming in Phase 4.")

with tab_team:
    # PHASE 4 PROMPT 13 — Team tab content goes here
    st.info("Team tab — coming in Phase 4.")
