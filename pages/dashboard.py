"""
pages/dashboard.py
Portfolio Dashboard — card grid view of all active workstreams with RAG status.
"""

import streamlit as st
import pandas as pd
from datetime import date

from pipeline.auth import (
    require_auth,
    get_current_user,
    get_current_user_id,
    get_user_workstreams,
    logout,
)
from pipeline.db import query_df

# ─── Colour constants ─────────────────────────────────────────────────────────

C_GREEN  = "#27AE60"
C_AMBER  = "#F39C12"
C_RED    = "#E74C3C"
C_TEAL   = "#4DB6AC"
BG_DARK  = "#0E1117"
BG_CARD  = "#262730"

# ─── Auth guard ───────────────────────────────────────────────────────────────

require_auth()

# ─── Pending invite token ─────────────────────────────────────────────────────

if st.session_state.get("pending_invite_token"):
    from pipeline.invite import accept_invite
    token = st.session_state.pop("pending_invite_token")
    success = accept_invite(token, get_current_user_id())
    if success:
        st.success("You've joined the workstream.")
    else:
        st.error("Invite link is no longer valid.")

# ─── Page header ─────────────────────────────────────────────────────────────

st.markdown(
    """
    <div style="margin-bottom:8px;">
      <h1 style="margin:0;font-size:2rem;font-weight:700;">My Portfolio</h1>
      <p style="margin:4px 0 0;color:#888;font-size:0.95rem;">
        Workstream health at a glance
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ─── Top action row ───────────────────────────────────────────────────────────

col_new, col_signout = st.columns([1, 1])
with col_new:
    if st.button("+ New Workstream", use_container_width=True):
        st.switch_page("pages/create_workstream.py")
with col_signout:
    if st.button("Sign Out", use_container_width=True):
        logout()

st.divider()

# ─── Data loading ─────────────────────────────────────────────────────────────

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

df_all = query_df(_SQL, (get_current_user_id(),))

# New workstreams not yet scored arrive with NULL rag_status → default to green.
if not df_all.empty and "rag_status" in df_all.columns:
    df_all["rag_status"] = df_all["rag_status"].fillna("green")

# ─── Early exit when user has no workstreams at all ──────────────────────────

if df_all.empty:
    st.info("You don't have any active workstreams. Create one to get started.")
    st.stop()

# ─── Summary strip ────────────────────────────────────────────────────────────

total   = len(df_all)
n_green = int((df_all["rag_status"] == "green").sum())
n_amber = int((df_all["rag_status"] == "amber").sum())
n_red   = int((df_all["rag_status"] == "red").sum())
n_stale = int(df_all["is_stale"].fillna(False).sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Active", total)
m2.metric("🟢 Green",     n_green)
m3.metric("🟡 Amber",     n_amber)
m4.metric("🔴 Red",       n_red)
m5.metric("⚠️ Stale",     n_stale)

st.divider()

# ─── Filter row ───────────────────────────────────────────────────────────────

_PHASES = ["discovery", "planning", "in_flight", "review_closing"]

fc1, fc2, fc3, _ = st.columns([2, 2, 2, 4])

with fc1:
    rag_filter = st.multiselect(
        "Status",
        options=["green", "amber", "red"],
        default=["green", "amber", "red"],
    )
with fc2:
    role_filter = st.selectbox("Showing", ["All", "Mine", "Invited"])
with fc3:
    phase_filter = st.multiselect(
        "Phase",
        options=_PHASES,
        default=_PHASES,
    )

# Apply filters
df = df_all.copy()

if rag_filter:
    df = df[df["rag_status"].isin(rag_filter)]

if role_filter == "Mine":
    df = df[df["role"] == "owner"]
elif role_filter == "Invited":
    df = df[df["role"] != "owner"]

if phase_filter:
    df = df[df["phase"].isin(phase_filter)]

if df.empty:
    st.info("No workstreams match the current filters.")
    st.stop()

# ─── Helper functions ─────────────────────────────────────────────────────────

def _rag_colour(status: str) -> str:
    """Return the hex colour for a RAG status string."""
    return {
        "green": C_GREEN,
        "amber": C_AMBER,
        "red":   C_RED,
    }.get(status, C_GREEN)


def _score_colour(score: float | None) -> str:
    """Return the hex colour for a 0-100 sub-score."""
    if score is None:
        return "#888888"
    if score >= 70:
        return C_GREEN
    if score >= 40:
        return C_AMBER
    return C_RED


def _phase_label(phase: str | None) -> str:
    """Return a human-readable phase label."""
    return {
        "discovery":      "Discovery",
        "planning":       "Planning",
        "in_flight":      "In Flight",
        "review_closing": "Review & Closing",
    }.get(phase or "", phase or "—")


def _deadline_html(end_date) -> str:
    """Return deadline HTML with urgency colouring."""
    if end_date is None:
        return "<span style='color:#888;font-size:0.8rem;'>No deadline set</span>"
    try:
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        days = (end_date - date.today()).days
    except Exception:
        return "<span style='color:#888;font-size:0.8rem;'>—</span>"

    if days < 0:
        return (
            f"<span style='color:{C_RED};font-size:0.8rem;font-weight:600;'>"
            f"⚠️ {abs(days)}d overdue</span>"
        )
    if days <= 7:
        return (
            f"<span style='color:{C_AMBER};font-size:0.8rem;font-weight:600;'>"
            f"🟡 {days}d remaining</span>"
        )
    return f"<span style='color:#888;font-size:0.8rem;'>{days}d remaining</span>"


def _score_bar_html(label: str, score: float | None) -> str:
    """Return HTML for a labelled sub-score bar."""
    pct    = int(score or 0)
    colour = _score_colour(score)
    return (
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
        f"  <span style='color:#888;font-size:0.75rem;width:58px;flex-shrink:0;'>{label}</span>"
        f"  <div style='flex:1;background:#333;border-radius:4px;height:6px;'>"
        f"    <div style='width:{pct}%;background:{colour};border-radius:4px;height:6px;'></div>"
        f"  </div>"
        f"  <span style='color:{colour};font-size:0.75rem;width:28px;text-align:right;'>{pct}</span>"
        f"</div>"
    )


# Cache owner display names to avoid one query per card.
@st.cache_data(ttl=120, show_spinner=False)
def _fetch_owner_names(owner_ids: tuple) -> dict:
    """
    Return a {user_id: display_name} dict for the given owner UUIDs.

    Accepts a tuple (not list) so it is hashable for st.cache_data.
    Falls back to an empty dict on any query error.
    """
    if not owner_ids:
        return {}
    placeholders = ",".join(["%s"] * len(owner_ids))
    sql = f"SELECT id, display_name FROM users WHERE id IN ({placeholders})"
    try:
        df_owners = query_df(sql, owner_ids)
        if df_owners.empty:
            return {}
        return dict(zip(df_owners["id"], df_owners["display_name"]))
    except Exception:
        return {}


# Fetch owner names for cards where the viewer is not the owner.
_non_owner_rows = df[df["role"] != "owner"]
_owner_ids = tuple(_non_owner_rows["owner_id"].dropna().unique().tolist())
_owner_names = _fetch_owner_names(_owner_ids)

# ─── Card grid ────────────────────────────────────────────────────────────────

COLS = 3
rows = [df.iloc[i : i + COLS] for i in range(0, len(df), COLS)]

for row_df in rows:
    grid_cols = st.columns(COLS)

    for col, (_, ws) in zip(grid_cols, row_df.iterrows()):
        ws_id     = ws["id"]
        ws_name   = ws["name"] or "Untitled"
        role      = ws.get("role") or "viewer"
        phase     = ws.get("phase")
        rag       = ws.get("rag_status", "green")
        rag_col   = _rag_colour(rag)
        is_stale  = bool(ws.get("is_stale", False))
        owner_id  = ws.get("owner_id")

        sched_score   = ws.get("schedule_score")
        budget_score  = ws.get("budget_score")
        blocker_score = ws.get("blocker_score")

        # ── Role pill ────────────────────────────────────────────────────────
        role_colour = C_TEAL if role == "owner" else "#555"
        role_label  = role.capitalize()
        role_pill = (
            f"<span style='background:{role_colour};color:#fff;"
            f"border-radius:4px;padding:1px 7px;font-size:0.72rem;'>"
            f"{role_label}</span>"
        )

        # ── Stale badge ──────────────────────────────────────────────────────
        stale_badge = (
            "<span style='background:#7B5800;color:#F39C12;"
            "border-radius:4px;padding:1px 7px;font-size:0.72rem;"
            "margin-left:6px;'>⚠️ Stale</span>"
            if is_stale else ""
        )

        # ── Phase badge ──────────────────────────────────────────────────────
        phase_html = (
            f"<span style='color:#aaa;font-size:0.78rem;'>"
            f"{_phase_label(phase)}</span>"
        )

        # ── Owner line (only shown when the viewer is not the owner) ─────────
        if role != "owner" and owner_id:
            owner_display = _owner_names.get(owner_id, "—")
            owner_html = (
                f"<div style='color:#888;font-size:0.75rem;margin-top:4px;'>"
                f"Owner: {owner_display}</div>"
            )
        else:
            owner_html = ""

        # ── Sub-score bars ───────────────────────────────────────────────────
        bars_html = (
            _score_bar_html("Schedule", sched_score)
            + _score_bar_html("Budget",   budget_score)
            + _score_bar_html("Blockers", blocker_score)
        )

        # ── Card shell (everything except the name button) ───────────────────
        with col:
            st.markdown(
                f"""
                <div style="
                    background:{BG_CARD};
                    border:1px solid rgba(255,255,255,0.08);
                    border-left:4px solid {rag_col};
                    border-radius:8px;
                    padding:16px;
                    margin-bottom:12px;
                ">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <span style="color:{rag_col};font-size:1.1rem;">●</span>
                    <span style="color:{rag_col};font-size:0.78rem;font-weight:600;letter-spacing:0.05em;">
                        {rag.upper()}
                    </span>
                    {stale_badge}
                  </div>
                  <div style="margin-bottom:6px;">
                    {role_pill}&nbsp;&nbsp;{phase_html}
                  </div>
                  {_deadline_html(ws.get("end_date"))}
                  <div style="margin-top:12px;">{bars_html}</div>
                  {owner_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Name as a Streamlit button (handles click events natively).
            if st.button(ws_name, key=f"ws_{ws_id}", use_container_width=True):
                st.query_params["id"] = ws_id
                st.switch_page("pages/workstream.py")
