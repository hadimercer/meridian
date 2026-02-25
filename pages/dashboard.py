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
    logout,
)
from pipeline.db import query_df

st.set_page_config(layout="wide")

require_auth()

with st.sidebar:
    st.page_link("pages/dashboard.py", label="📊 Portfolio")
    st.page_link("pages/create_workstream.py", label="➕ New Workstream")
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


# ── Main workstream query ──────────────────────────────────────────────────────
_SQL = """
    SELECT  w.id,
            w.name,
            w.description,
            w.phase,
            w.start_date,
            w.end_date,
            w.updated_at,
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

for col in ["is_stale", "description", "updated_at"]:
    if col not in df_all.columns:
        df_all[col] = False if col == "is_stale" else ("" if col == "description" else pd.NaT)


# ── SECTION 1 — PAGE HEADER ────────────────────────────────────────────────────
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


# ── SECTION 2 — PORTFOLIO PULSE BAR ───────────────────────────────────────────
workstream_ids = df_all["id"].dropna().tolist()

try:
    overdue_df = query_df(
        "SELECT COUNT(*) as n FROM milestones WHERE workstream_id = ANY(%s) AND status != 'complete' AND due_date < CURRENT_DATE",
        (workstream_ids,),
    )
except Exception:
    overdue_df = pd.DataFrame([{"n": 0}])

try:
    blockers_df = query_df(
        "SELECT COUNT(*) as n FROM blockers WHERE workstream_id = ANY(%s) AND status = 'open'",
        (workstream_ids,),
    )
except Exception:
    blockers_df = pd.DataFrame([{"n": 0}])

total_active       = len(df_all)
red_count          = int((df_all["rag_status"] == "red").sum())
amber_count        = int((df_all["rag_status"] == "amber").sum())
green_count        = int((df_all["rag_status"] == "green").sum())
overdue_milestones = int(overdue_df.iloc[0]["n"]) if not overdue_df.empty else 0
open_blockers      = int(blockers_df.iloc[0]["n"]) if not blockers_df.empty else 0


def pulse_tile(label, value, bg_color):
    return (
        f'<div style="background:{bg_color}; border-radius:0.6rem; padding:0.9rem 1rem; text-align:center;">'
        f'<div style="font-size:1.8rem; font-weight:700; color:#FFFFFF;">{value}</div>'
        f'<div style="font-size:0.78rem; color:rgba(255,255,255,0.82); margin-top:0.2rem;">{label}</div>'
        f'</div>'
    )


pulse_cols = st.columns(6)
pulse_data = [
    ("Total Active",       total_active,       "#1B4F72"),
    ("🔴 Red",             red_count,          "#E74C3C"),
    ("🟡 Amber",           amber_count,        "#F39C12"),
    ("🟢 Green",           green_count,        "#27AE60"),
    ("⚠️ Overdue Milestones", overdue_milestones, "#E67E22"),
    ("🚧 Open Blockers",   open_blockers,      "#8E44AD"),
]
for col, (label, value, color) in zip(pulse_cols, pulse_data):
    col.markdown(pulse_tile(label, value, color), unsafe_allow_html=True)

st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)


# ── SECTION 3 — FILTER BAR ────────────────────────────────────────────────────
st.session_state.setdefault("filter_status", "all")
st.session_state.setdefault("filter_phase",  "All Phases")
st.session_state.setdefault("filter_role",   "All Roles")
st.session_state.setdefault("filter_sort",   "🔴 Red → Green")

with st.container():
    filter_col_1, filter_col_2, filter_col_3, filter_col_4 = st.columns([3, 2, 2, 2])

    with filter_col_1:
        st.caption("Status")
        pill_cols = st.columns(5)
        status_options = [
            ("all",   "All"),
            ("red",   "🔴 Red"),
            ("amber", "🟡 Amber"),
            ("green", "🟢 Green"),
            ("stale", "⚠️ Stale"),
        ]
        for idx, (skey, slabel) in enumerate(status_options):
            with pill_cols[idx]:
                active = st.session_state["filter_status"] == skey
                btn_type = "primary" if active else "secondary"
                if st.button(slabel, key=f"pill_{skey}", use_container_width=True, type=btn_type):
                    st.session_state["filter_status"] = skey
                    st.rerun()

    with filter_col_2:
        st.selectbox("Phase", ["All Phases", "Discovery", "Planning", "In Flight", "Review & Closing"], key="filter_phase")

    with filter_col_3:
        st.selectbox("Role", ["All Roles", "Owner", "Contributor", "Viewer"], key="filter_role")

    with filter_col_4:
        st.selectbox("Sort", ["🔴 Red → Green", "🟢 Green → Red", "⏰ Deadline (soonest)", "🕐 Recently Updated"], key="filter_sort")

st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)


# ── SECTION 4 — APPLY FILTERS ─────────────────────────────────────────────────
df_filtered = df_all.copy()
df_filtered["end_date"]   = pd.to_datetime(df_filtered["end_date"],   errors="coerce")
df_filtered["updated_at"] = pd.to_datetime(df_filtered["updated_at"], errors="coerce", utc=True)

fstatus = st.session_state["filter_status"]
if fstatus != "all":
    if fstatus == "stale":
        df_filtered = df_filtered[df_filtered["is_stale"] == True]
    else:
        df_filtered = df_filtered[df_filtered["rag_status"] == fstatus]

phase_map = {"Discovery": "discovery", "Planning": "planning", "In Flight": "in_flight", "Review & Closing": "review_closing"}
fphase = st.session_state["filter_phase"]
if fphase != "All Phases":
    df_filtered = df_filtered[df_filtered["phase"] == phase_map.get(fphase, fphase)]

frole = st.session_state["filter_role"]
if frole != "All Roles":
    df_filtered = df_filtered[df_filtered["role"] == frole.lower()]

fsort = st.session_state["filter_sort"]
rag_order = {"red": 0, "amber": 1, "green": 2}
if fsort == "🔴 Red → Green":
    df_filtered["_s"] = df_filtered["rag_status"].map(rag_order)
    df_filtered = df_filtered.sort_values("_s").drop(columns=["_s"])
elif fsort == "🟢 Green → Red":
    df_filtered["_s"] = df_filtered["rag_status"].map(rag_order)
    df_filtered = df_filtered.sort_values("_s", ascending=False).drop(columns=["_s"])
elif fsort == "⏰ Deadline (soonest)":
    df_filtered = df_filtered.sort_values("end_date")
elif fsort == "🕐 Recently Updated":
    df_filtered = df_filtered.sort_values("updated_at", ascending=False)


# ── SECTION 5 — HELPER FUNCTIONS ──────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_owner_name(owner_id: str) -> str:
    if not owner_id:
        return "Unknown"
    try:
        df = query_df("SELECT display_name FROM public.users WHERE id = %s", (owner_id,))
        return str(df.iloc[0]["display_name"]) if not df.empty else "Unknown"
    except Exception:
        return "Unknown"


@st.cache_data(show_spinner=False)
def get_blocker_count(ws_id: str) -> int:
    try:
        df = query_df("SELECT COUNT(*) as n FROM blockers WHERE workstream_id = %s AND status = 'open'", (ws_id,))
        return int(df.iloc[0]["n"]) if not df.empty else 0
    except Exception:
        return 0


def to_score(val) -> int:
    n = pd.to_numeric(val, errors="coerce")
    return int(round(float(n))) if pd.notna(n) else 0


def phase_display(p) -> str:
    return {"in_flight": "In Flight", "review_closing": "Review & Closing", "discovery": "Discovery", "planning": "Planning"}.get(str(p or ""), str(p or "-"))


def calc_days(end_date_val) -> int:
    dt = pd.to_datetime(end_date_val, errors="coerce")
    if pd.isna(dt):
        return 0
    dt = dt.tz_localize("UTC") if dt.tzinfo is None else dt.tz_convert("UTC")
    return int((dt.normalize() - pd.Timestamp.now(tz="UTC").normalize()).days)


def calc_updated(updated_val) -> int:
    dt = pd.to_datetime(updated_val, errors="coerce", utc=True)
    if pd.isna(dt):
        return 0
    return max(0, int((pd.Timestamp.now(tz="UTC") - dt).days))


def make_score_bar(label: str, score: int) -> str:
    bar_color = "#27AE60" if score >= 70 else "#F39C12" if score >= 40 else "#E74C3C"
    # Build without f-string interpolation of the score to avoid curly brace issues
    pct = str(score)
    return (
        '<div style="margin-bottom:0.3rem;">'
        '<div style="display:flex; justify-content:space-between; font-size:0.75rem;'
        ' color:rgba(255,255,255,0.7); margin-bottom:0.2rem;">'
        '<span>' + label + '</span>'
        '<span style="color:' + bar_color + '; font-weight:600;">' + pct + '</span>'
        '</div>'
        '<div style="background:rgba(255,255,255,0.1); border-radius:999px; height:6px;">'
        '<div style="background:' + bar_color + '; width:' + pct + '%; height:6px; border-radius:999px;"></div>'
        '</div>'
        '</div>'
    )


# ── SECTION 6 — CARD RENDERING ────────────────────────────────────────────────
if df_filtered.empty:
    st.markdown(
        '<div style="text-align:center; padding:3rem; color:rgba(255,255,255,0.4);">'
        '<div style="font-size:2.5rem; margin-bottom:0.5rem;">🔍</div>'
        '<div style="font-size:1rem;">No workstreams match the current filters.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    rag_colors  = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}
    rag_labels  = {"green": "🟢 GREEN", "amber": "🟡 AMBER", "red": "🔴 RED"}
    role_colors = {"owner": "#4DB6AC", "contributor": "#5DADE2", "viewer": "#AAB7B8"}

    for _, ws in df_filtered.iterrows():
        ws_id    = str(ws.get("id") or "")
        ws_name  = str(ws.get("name") or "Untitled Workstream")
        ws_desc  = str(ws.get("description") or "")
        if len(ws_desc) > 120:
            ws_desc = ws_desc[:120].rstrip() + "…"

        ws_rag      = str(ws.get("rag_status") or "").lower()
        ws_role     = str(ws.get("role") or "viewer").lower()
        ws_phase    = phase_display(ws.get("phase"))
        ws_schedule = to_score(ws.get("schedule_score"))
        ws_budget   = to_score(ws.get("budget_score"))
        ws_blockers = to_score(ws.get("blocker_score"))
        ws_days     = calc_days(ws.get("end_date"))
        ws_updated  = calc_updated(ws.get("updated_at"))
        ws_owner    = get_owner_name(str(ws.get("owner_id") or ""))
        ws_nb       = get_blocker_count(ws_id)

        rag_color  = rag_colors.get(ws_rag, "#888")
        rag_label  = rag_labels.get(ws_rag, ws_rag.upper())
        role_color = role_colors.get(ws_role, "#AAB7B8")
        days_color = "#E74C3C" if ws_days < 14 else "#F39C12" if ws_days < 30 else "#FAFAFA"
        days_text  = "days left" if ws_days >= 0 else "days overdue"

        # Pre-build score bars using string concatenation (no nested f-strings with %)
        bar_schedule = make_score_bar("Schedule", ws_schedule)
        bar_budget   = make_score_bar("Budget",   ws_budget)
        bar_blockers = make_score_bar("Blockers", ws_blockers)

        # HTML-escape all user-supplied strings
        name_e  = html.escape(ws_name)
        desc_e  = html.escape(ws_desc)
        owner_e = html.escape(ws_owner)
        phase_e = html.escape(ws_phase)
        role_e  = html.escape(ws_role.capitalize())
        blocker_word = "blocker" if ws_nb == 1 else "blockers"

        card = (
            f'<div style="background:rgba(255,255,255,0.04); border-radius:0.75rem;'
            f' border:1px solid rgba(255,255,255,0.08); border-left:5px solid {rag_color};'
            f' padding:1.2rem 1.4rem; margin-bottom:0.8rem;">'

            # Top row
            f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">'
            f'<div style="flex:1;">'
            f'<div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.3rem;">'
            f'<span style="background:{rag_color}; color:#fff; padding:0.2rem 0.7rem;'
            f' border-radius:999px; font-size:0.78rem; font-weight:700;">{rag_label}</span>'
            f'<span style="background:{role_color}22; color:{role_color};'
            f' border:1px solid {role_color}55; padding:0.2rem 0.6rem;'
            f' border-radius:999px; font-size:0.75rem; font-weight:600;">{role_e}</span>'
            f'<span style="background:rgba(255,255,255,0.08); color:rgba(255,255,255,0.7);'
            f' padding:0.2rem 0.6rem; border-radius:999px; font-size:0.75rem;">{phase_e}</span>'
            f'</div>'
            f'<div style="font-size:1.2rem; font-weight:700; color:#FAFAFA; margin-bottom:0.3rem;">{name_e}</div>'
            f'<div style="font-size:0.82rem; color:rgba(255,255,255,0.55); margin-bottom:0.6rem;">{desc_e}</div>'
            f'</div>'

            # Days remaining block
            f'<div style="text-align:right; min-width:90px; margin-left:1.5rem;">'
            f'<div style="font-size:2rem; font-weight:700; color:{days_color}; line-height:1;">{abs(ws_days)}</div>'
            f'<div style="font-size:0.72rem; color:rgba(255,255,255,0.6);">{days_text}</div>'
            f'</div>'
            f'</div>'

            # Score bars (pre-built strings, no % interpolation here)
            f'<div style="margin-bottom:0.7rem;">'
            + bar_schedule + bar_budget + bar_blockers +
            f'</div>'

            # Footer row
            f'<div style="display:flex; gap:1.4rem; font-size:0.78rem; color:rgba(255,255,255,0.55);'
            f' border-top:1px solid rgba(255,255,255,0.07); padding-top:0.6rem;">'
            f'<span>👤 {owner_e}</span>'
            f'<span>🕐 Updated {ws_updated}d ago</span>'
            f'<span>🚧 {ws_nb} open {blocker_word}</span>'
            f'</div>'
            f'</div>'
        )

        st.markdown(card, unsafe_allow_html=True)

        # Open button — right-aligned, small
        _, btn_col = st.columns([5, 1])
        with btn_col:
            if st.button("Open →", key=f"open_{ws_id}", use_container_width=True):
                st.session_state["open_workstream_id"] = ws_id
                st.switch_page("pages/workstream.py")