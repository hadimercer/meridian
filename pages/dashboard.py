"""
pages/dashboard.py
Portfolio dashboard redesign.
"""

import html
import streamlit as st
import pandas as pd

from pipeline.auth import (
    require_auth,
    get_current_user,
    get_current_user_id,
    get_user_workstreams,
    logout,
)
from pipeline.db import query_df

st.set_page_config(layout="wide")


require_auth()


with st.sidebar:
    st.page_link("pages/dashboard.py", label="\U0001F4CA Portfolio")
    st.page_link("pages/create_workstream.py", label="\u2795 New Workstream")
    st.divider()
    _sidebar_user = get_current_user()
    if _sidebar_user:
        _sidebar_uid = getattr(_sidebar_user, "id", None)
        try:
            _dn_df = query_df(
                "SELECT display_name FROM users WHERE id = %s", (_sidebar_uid,)
            )
            _display_name = (
                _dn_df.iloc[0]["display_name"] if not _dn_df.empty else ""
            )
        except Exception:
            _display_name = ""
        if _display_name:
            st.markdown(f"**{_display_name}**")
        st.caption(getattr(_sidebar_user, "email", ""))
    if st.button("Sign Out", key="sidebar_signout_dash"):
        logout()


if st.session_state.get("pending_invite_token"):
    from pipeline.invite import accept_invite

    token = st.session_state.pop("pending_invite_token")
    success = accept_invite(token, get_current_user_id())
    if success:
        st.success("You've joined the workstream.")
    else:
        st.error("Invite link is no longer valid.")


# Main workstream query (kept)
_SQL = """
    SELECT  w.id,
            w.name,
            w.phase,
            w.start_date,
            w.end_date,
            w.owner_id,
            wm.role,
            wm.joined_at,
            r.rag_status,
            r.composite_score,
            r.schedule_score,
            r.budget_score,
            r.blocker_score,
            r.is_stale,
            r.calculated_at
    FROM    workstreams           w
    JOIN    workstream_members    wm  ON  wm.workstream_id = w.id
    LEFT JOIN rag_scores          r   ON  r.workstream_id  = w.id
    WHERE   wm.user_id          = %s
      AND   wm.is_former_member = FALSE
      AND   w.is_archived       = FALSE
    ORDER BY
        CASE r.rag_status WHEN 'red' THEN 0 WHEN 'amber' THEN 1 ELSE 2 END,
        w.updated_at DESC
"""

current_user_id = get_current_user_id()

try:
    df_all = query_df(_SQL, (current_user_id,))
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if not df_all.empty and "rag_status" in df_all.columns:
    df_all["rag_status"] = df_all["rag_status"].fillna("green")

if "is_stale" not in df_all.columns:
    df_all["is_stale"] = False

# Supplementary fields used by redesigned cards and sorting
if not df_all.empty:
    _ws_ids_for_meta = df_all["id"].dropna().tolist()
    if _ws_ids_for_meta:
        try:
            _meta_df = query_df(
                """
                SELECT id, description, updated_at
                FROM workstreams
                WHERE id = ANY(%s)
                """,
                (_ws_ids_for_meta,),
            )
        except Exception:
            _meta_df = pd.DataFrame(columns=["id", "description", "updated_at"])
        if not _meta_df.empty:
            df_all = df_all.merge(_meta_df, on="id", how="left")

if "description" not in df_all.columns:
    df_all["description"] = ""
if "updated_at" not in df_all.columns:
    df_all["updated_at"] = pd.NaT


# SECTION 1 — PAGE HEADER
col_header_left, col_header_right = st.columns([6, 1])
with col_header_left:
    st.markdown(
        """
        <div style="margin-bottom:0.5rem;">
            <h1 style="margin:0; font-size:2rem; font-weight:700;">My Portfolio</h1>
            <p style="margin:0.25rem 0 0 0; color:rgba(255,255,255,0.66); font-size:0.95rem;">
                Workstream health at a glance
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_header_right:
    st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
    if st.button("+ New Workstream", key="new_workstream_header", use_container_width=True):
        st.session_state["open_workstream_id"] = None
        st.switch_page("pages/create_workstream.py")


if df_all.empty:
    st.info("You don't have any active workstreams. Create one to get started.")
    st.stop()


# SECTION 2 — PORTFOLIO PULSE BAR
workstream_ids = df_all["id"].dropna().tolist()

if workstream_ids:
    try:
        overdue_df = query_df(
            """
            SELECT COUNT(*) as n
            FROM milestones
            WHERE workstream_id = ANY(%s)
              AND status != 'complete'
              AND due_date < CURRENT_DATE
            """,
            (workstream_ids,),
        )
    except Exception:
        overdue_df = pd.DataFrame([{"n": 0}])

    try:
        blockers_df = query_df(
            """
            SELECT COUNT(*) as n
            FROM blockers
            WHERE workstream_id = ANY(%s)
              AND status = 'open'
            """,
            (workstream_ids,),
        )
    except Exception:
        blockers_df = pd.DataFrame([{"n": 0}])
else:
    overdue_df = pd.DataFrame([{"n": 0}])
    blockers_df = pd.DataFrame([{"n": 0}])


def pulse_tile(label, value, bg_color, text_color="#FFFFFF"):
    return f"""
    <div style="background:{bg_color}; border-radius:0.6rem; padding:0.9rem 1rem;
                text-align:center; height:100%;">
        <div style="font-size:1.8rem; font-weight:700; color:{text_color};">{value}</div>
        <div style="font-size:0.78rem; color:rgba(255,255,255,0.82); margin-top:0.2rem;">{label}</div>
    </div>
    """


total_active = len(df_all)
red_count = int((df_all["rag_status"] == "red").sum())
amber_count = int((df_all["rag_status"] == "amber").sum())
green_count = int((df_all["rag_status"] == "green").sum())
overdue_milestones = int(overdue_df.iloc[0]["n"]) if not overdue_df.empty else 0
open_blockers = int(blockers_df.iloc[0]["n"]) if not blockers_df.empty else 0

pulse_cols = st.columns(6)
pulse_cols[0].markdown(pulse_tile("Total Active", total_active, "#1B4F72"), unsafe_allow_html=True)
pulse_cols[1].markdown(pulse_tile("Red", red_count, "#E74C3C"), unsafe_allow_html=True)
pulse_cols[2].markdown(pulse_tile("Amber", amber_count, "#F39C12"), unsafe_allow_html=True)
pulse_cols[3].markdown(pulse_tile("Green", green_count, "#27AE60"), unsafe_allow_html=True)
pulse_cols[4].markdown(pulse_tile("Overdue Milestones", overdue_milestones, "#E67E22"), unsafe_allow_html=True)
pulse_cols[5].markdown(pulse_tile("Open Blockers", open_blockers, "#8E44AD"), unsafe_allow_html=True)

st.markdown("<div style='height:0.85rem;'></div>", unsafe_allow_html=True)


# SECTION 3 — FILTER BAR
st.markdown(
    """
    <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08);
                border-radius:0.6rem; padding:0.8rem 1rem; margin-bottom:1rem;">
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"] button {
        border-radius: 999px !important;
        font-size: 0.82rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.session_state.setdefault("filter_status", "all")
st.session_state.setdefault("filter_phase", "All Phases")
st.session_state.setdefault("filter_role", "All Roles")
st.session_state.setdefault("filter_sort", " Red \u2192 Green")

filter_col_1, filter_col_2, filter_col_3, filter_col_4 = st.columns([3, 2, 2, 2])

with filter_col_1:
    st.caption("Status")
    status_cols = st.columns(5)
    status_options = [
        ("all", "All"),
        ("red", "\U0001F534 Red"),
        ("amber", "\U0001F7E0 Amber"),
        ("green", "\U0001F7E2 Green"),
        ("stale", "\u26A0\uFE0F Stale"),
    ]
    for idx, (status_key, status_label) in enumerate(status_options):
        with status_cols[idx]:
            active = st.session_state.get("filter_status", "all") == status_key
            if st.button(
                status_label,
                key=f"filter_status_{status_key}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state["filter_status"] = status_key
                st.rerun()

with filter_col_2:
    st.selectbox(
        "Phase",
        ["All Phases", "Discovery", "Planning", "In Flight", "Review & Closing"],
        key="filter_phase",
    )

with filter_col_3:
    st.selectbox(
        "Role",
        ["All Roles", "Owner", "Contributor", "Viewer"],
        key="filter_role",
    )

with filter_col_4:
    st.selectbox(
        "Sort",
        [
            " Red \u2192 Green",
            " Green \u2192 Red",
            "\u23F0 Deadline (soonest)",
            " Recently Updated",
        ],
        key="filter_sort",
    )


# SECTION 4 — APPLY FILTERS TO DATAFRAME
df_filtered = df_all.copy()

if "end_date" in df_filtered.columns:
    df_filtered["end_date"] = pd.to_datetime(df_filtered["end_date"], errors="coerce")
if "updated_at" in df_filtered.columns:
    df_filtered["updated_at"] = pd.to_datetime(df_filtered["updated_at"], errors="coerce", utc=True)

# Status filter
if st.session_state.get("filter_status", "all") != "all":
    status_val = st.session_state["filter_status"]
    if status_val == "stale":
        df_filtered = df_filtered[df_filtered["is_stale"] == True]
    else:
        df_filtered = df_filtered[df_filtered["rag_status"] == status_val]

# Phase filter
phase_map = {
    "Discovery": "discovery",
    "Planning": "planning",
    "In Flight": "in_flight",
    "Review & Closing": "review_closing",
}
if st.session_state.get("filter_phase", "All Phases") != "All Phases":
    df_filtered = df_filtered[df_filtered["phase"] == phase_map[st.session_state["filter_phase"]]]

# Role filter
if st.session_state.get("filter_role", "All Roles") != "All Roles":
    df_filtered = df_filtered[df_filtered["role"] == st.session_state["filter_role"].lower()]

# Sort
sort_val = st.session_state.get("filter_sort", " Red \u2192 Green")
rag_order = {"red": 0, "amber": 1, "green": 2}
if sort_val == " Red \u2192 Green":
    df_filtered["_sort"] = df_filtered["rag_status"].map(rag_order)
    df_filtered = df_filtered.sort_values("_sort")
elif sort_val == " Green \u2192 Red":
    df_filtered["_sort"] = df_filtered["rag_status"].map(rag_order)
    df_filtered = df_filtered.sort_values("_sort", ascending=False)
elif sort_val == "\u23F0 Deadline (soonest)":
    df_filtered = df_filtered.sort_values("end_date")
elif sort_val == " Recently Updated":
    df_filtered = df_filtered.sort_values("updated_at", ascending=False)

if "_sort" in df_filtered.columns:
    df_filtered = df_filtered.drop(columns=["_sort"])


# SECTION 5 — WORKSTREAM CARDS
@st.cache_data(show_spinner=False)
def get_owner_display_name(owner_id: str | None) -> str:
    if not owner_id:
        return "Unknown"
    try:
        owner_df = query_df(
            "SELECT display_name FROM public.users WHERE id = %s",
            (owner_id,),
        )
        if owner_df.empty:
            return "Unknown"
        return str(owner_df.iloc[0].get("display_name") or "Unknown")
    except Exception:
        return "Unknown"


@st.cache_data(show_spinner=False)
def get_open_blockers_count(workstream_id: str) -> int:
    try:
        blockers_df_local = query_df(
            "SELECT COUNT(*) as n FROM blockers WHERE workstream_id = %s AND status = 'open'",
            (workstream_id,),
        )
        if blockers_df_local.empty:
            return 0
        return int(blockers_df_local.iloc[0].get("n") or 0)
    except Exception:
        return 0


def score_bar(label, score, color):
    score_num = pd.to_numeric(score, errors="coerce")
    score_int = int(round(float(score_num))) if pd.notna(score_num) else 0
    score_int = max(0, min(100, score_int))
    bar_color = "#27AE60" if score_int >= 70 else "#F39C12" if score_int >= 40 else "#E74C3C"
    return f"""
    <div style="margin-bottom:0.3rem;">
        <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:rgba(255,255,255,0.7); margin-bottom:0.2rem;">
            <span>{label}</span><span style="color:{bar_color}; font-weight:600;">{score_int}</span>
        </div>
        <div style="background:rgba(255,255,255,0.1); border-radius:999px; height:6px;">
            <div style="background:{bar_color}; width:{score_int}%; height:6px; border-radius:999px;"></div>
        </div>
    </div>
    """


def to_int_score(value) -> int:
    value_num = pd.to_numeric(value, errors="coerce")
    if pd.isna(value_num):
        return 0
    return int(round(float(value_num)))


def phase_label(phase_value: str | None) -> str:
    return {
        "in_flight": "In Flight",
        "review_closing": "Review & Closing",
        "discovery": "Discovery",
        "planning": "Planning",
    }.get(str(phase_value or ""), str(phase_value or "-"))


def days_to_deadline(end_date_value) -> int:
    dt = pd.to_datetime(end_date_value, errors="coerce")
    if pd.isna(dt):
        return 0
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")
    return int((dt.normalize() - pd.Timestamp.now(tz="UTC").normalize()).days)


def days_since_updated(updated_value) -> int:
    dt = pd.to_datetime(updated_value, errors="coerce", utc=True)
    if pd.isna(dt):
        return 0
    return max(0, int((pd.Timestamp.now(tz="UTC") - dt).days))


st.markdown(
    """
    <style>
    .portfolio-card-list div[data-testid="stButton"] > button {
        position: relative;
        margin-top: -4.5rem;
        height: 4.5rem;
        background: transparent !important;
        border: none !important;
        color: transparent !important;
        cursor: pointer;
        width: 100%;
    }
    .portfolio-card-list div[data-testid="stButton"] > button:hover {
        background: rgba(255,255,255,0.03) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if df_filtered.empty:
    st.markdown(
        """
        <div style="text-align:center; padding:3rem; color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem; margin-bottom:0.5rem;"></div>
            <div style="font-size:1rem;">No workstreams match the current filters.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown('<div class="portfolio-card-list">', unsafe_allow_html=True)

    for _, ws in df_filtered.iterrows():
        ws_id = ws.get("id")
        ws_name = str(ws.get("name") or "Untitled Workstream")
        ws_desc = str(ws.get("description") or "")
        if len(ws_desc) > 120:
            ws_desc = ws_desc[:120].rstrip() + "..."

        ws_phase = str(ws.get("phase") or "")
        ws_phase_label = phase_label(ws_phase)
        ws_role = str(ws.get("role") or "viewer")
        ws_rag = str(ws.get("rag_status") or "").lower()

        ws_composite = to_int_score(ws.get("composite_score"))
        ws_schedule = to_int_score(ws.get("schedule_score"))
        ws_budget = to_int_score(ws.get("budget_score"))
        ws_blocker_score = to_int_score(ws.get("blocker_score"))

        ws_days = days_to_deadline(ws.get("end_date"))
        ws_updated = days_since_updated(ws.get("updated_at"))
        ws_owner = get_owner_display_name(str(ws.get("owner_id") or ""))
        ws_open_blockers = get_open_blockers_count(str(ws_id))

        rag_colors = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}
        rag_color = rag_colors.get(ws_rag, "#888")
        rag_labels = {"green": " GREEN", "amber": " AMBER", "red": " RED"}
        rag_label = rag_labels.get(ws_rag, "UNKNOWN")

        days_color = "#E74C3C" if ws_days < 14 else "#F39C12" if ws_days < 30 else "#FAFAFA"
        days_label = f"{ws_days}d left" if ws_days >= 0 else f"{abs(ws_days)}d overdue"

        role_colors = {"owner": "#4DB6AC", "contributor": "#5DADE2", "viewer": "#AAB7B8"}
        role_color = role_colors.get(ws_role, "#888")

        ws_name_html = html.escape(ws_name)
        ws_desc_html = html.escape(ws_desc)
        ws_owner_html = html.escape(ws_owner)
        ws_phase_label_html = html.escape(ws_phase_label)

        card_html = f"""
<div style="
    background: rgba(255,255,255,0.04);
    border-radius: 0.75rem;
    border-left: 5px solid {rag_color};
    border: 1px solid rgba(255,255,255,0.08);
    border-left: 5px solid {rag_color};
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    cursor: pointer;
">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
        <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.3rem;">
                <span style="background:{rag_color}; color:#fff; padding:0.2rem 0.7rem; border-radius:999px; font-size:0.78rem; font-weight:700;">{rag_label}</span>
                <span style="background:{role_color}22; color:{role_color}; border:1px solid {role_color}55; padding:0.2rem 0.6rem; border-radius:999px; font-size:0.75rem; font-weight:600;">{ws_role.capitalize()}</span>
                <span style="background:rgba(255,255,255,0.08); color:rgba(255,255,255,0.7); padding:0.2rem 0.6rem; border-radius:999px; font-size:0.75rem;">{ws_phase_label_html}</span>
            </div>
            <div style="font-size:1.2rem; font-weight:700; color:#FAFAFA; margin-bottom:0.3rem;">{ws_name_html}</div>
            <div style="font-size:0.82rem; color:rgba(255,255,255,0.55); margin-bottom:0.6rem;">{ws_desc_html}</div>
        </div>
        <div style="text-align:right; min-width:90px; margin-left:1.5rem;">
            <div style="font-size:2rem; font-weight:700; color:{days_color}; line-height:1;">{abs(ws_days)}</div>
            <div style="font-size:0.72rem; color:rgba(255,255,255,0.6);">{'days left' if ws_days >= 0 else 'days overdue'}</div>
        </div>
    </div>
    <div style="margin-bottom:0.7rem;">
        {score_bar('Schedule', ws_schedule, rag_color)}
        {score_bar('Budget', ws_budget, rag_color)}
        {score_bar('Blockers', ws_blocker_score, rag_color)}
    </div>
    <div style="display:flex; gap:1.4rem; font-size:0.78rem; color:rgba(255,255,255,0.55); border-top:1px solid rgba(255,255,255,0.07); padding-top:0.6rem;">
        <span> {ws_owner_html}</span>
        <span> Updated {ws_updated}d ago</span>
        <span> {ws_open_blockers} open blocker{'s' if ws_open_blockers != 1 else ''}</span>
    </div>
</div>
"""
        st.markdown(card_html, unsafe_allow_html=True)

        if st.button(ws_name, key=f"card_{ws_id}", use_container_width=True):
            st.session_state["open_workstream_id"] = ws_id
            st.switch_page("pages/workstream.py")

    st.markdown("</div>", unsafe_allow_html=True)

