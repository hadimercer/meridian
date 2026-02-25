"""
pages/home.py
Portfolio command center landing page.
"""

import html
import pandas as pd
import streamlit as st

from pipeline.auth import (
    get_current_user,
    get_current_user_id,
    logout,
    require_auth,
)
from pipeline.db import query_df

st.set_page_config(layout="wide")

require_auth()

with st.sidebar:
    st.page_link("pages/home.py", label="Home")
    st.page_link("pages/dashboard.py", label="Portfolio")
    st.page_link("pages/analytics.py", label=" Analytics")
    st.page_link("pages/create_workstream.py", label="New Workstream")
    st.divider()
    _sidebar_user = get_current_user()
    if _sidebar_user:
        _sidebar_uid = getattr(_sidebar_user, "id", None)
        try:
            _dn_df = query_df(
                "SELECT display_name FROM users WHERE id = %s", (_sidebar_uid,)
            )
            _display_name = _dn_df.iloc[0]["display_name"] if not _dn_df.empty else ""
        except Exception:
            _display_name = ""
        if _display_name:
            st.markdown(f"**{_display_name}**")
        st.caption(getattr(_sidebar_user, "email", ""))
    if st.button("Sign Out", key="sidebar_signout_home"):
        logout()

current_user_id = get_current_user_id()

_SQL = """
    SELECT  w.id, w.name, w.phase, w.end_date, w.owner_id,
            wm.role,
            r.rag_status, r.composite_score, r.schedule_score,
            r.budget_score, r.blocker_score, r.is_stale
    FROM    workstreams        w
    JOIN    workstream_members wm ON wm.workstream_id = w.id
    LEFT JOIN rag_scores       r  ON r.workstream_id  = w.id
    WHERE   wm.user_id          = %s
      AND   wm.is_former_member = FALSE
      AND   w.is_archived       = FALSE
"""

try:
    df_all = query_df(_SQL, (current_user_id,))
except Exception as error:
    st.error(f"Database error: {error}")
    st.stop()

if not df_all.empty and "rag_status" in df_all.columns:
    df_all["rag_status"] = df_all["rag_status"].fillna("green")
if "is_stale" not in df_all.columns:
    df_all["is_stale"] = False

st.markdown(
    """
<div style="background:linear-gradient(90deg,#1B4F72 0%,#2E86C1 100%);
            border-radius:0.6rem; padding:1rem 1.4rem 0.9rem; margin-bottom:1.2rem;">
  <h1 style="color:#FFFFFF; font-size:1.8rem; font-weight:700; margin:0 0 0.2rem 0;">
    Welcome back
  </h1>
  <p style="color:rgba(255,255,255,0.82); font-size:0.88rem; margin:0;">
    Here's what needs your attention today.
  </p>
</div>
""",
    unsafe_allow_html=True,
)

workstream_ids = [str(i) for i in df_all["id"].dropna().tolist()]

if workstream_ids:
    ws_placeholders = ",".join(["%s"] * len(workstream_ids))
    ws_params = tuple(workstream_ids)
    try:
        overdue_df = query_df(
            f"""
            SELECT COUNT(*) as n
            FROM milestones
            WHERE workstream_id::text IN ({ws_placeholders})
              AND status != 'complete'
              AND due_date < CURRENT_DATE
            """,
            ws_params,
        )
    except Exception:
        overdue_df = pd.DataFrame([{"n": 0}])

    try:
        blockers_df = query_df(
            f"""
            SELECT COUNT(*) as n
            FROM blockers
            WHERE workstream_id::text IN ({ws_placeholders})
              AND status = 'open'
            """,
            ws_params,
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
red_count = int((df_all["rag_status"] == "red").sum()) if not df_all.empty else 0
amber_count = int((df_all["rag_status"] == "amber").sum()) if not df_all.empty else 0
green_count = int((df_all["rag_status"] == "green").sum()) if not df_all.empty else 0
overdue_milestones = int(overdue_df.iloc[0]["n"]) if not overdue_df.empty else 0
open_blockers = int(blockers_df.iloc[0]["n"]) if not blockers_df.empty else 0

pulse_cols = st.columns(6)
pulse_cols[0].markdown(pulse_tile("Total Active", total_active, "#1B4F72"), unsafe_allow_html=True)
pulse_cols[1].markdown(pulse_tile("Red", red_count, "#E74C3C"), unsafe_allow_html=True)
pulse_cols[2].markdown(pulse_tile("Amber", amber_count, "#F39C12"), unsafe_allow_html=True)
pulse_cols[3].markdown(pulse_tile("Green", green_count, "#27AE60"), unsafe_allow_html=True)
pulse_cols[4].markdown(
    pulse_tile("Overdue Milestones", overdue_milestones, "#E67E22"), unsafe_allow_html=True
)
pulse_cols[5].markdown(pulse_tile("Open Blockers", open_blockers, "#8E44AD"), unsafe_allow_html=True)

st.markdown("<div style='height:0.9rem;'></div>", unsafe_allow_html=True)

st.markdown(
    """
<style>
div[data-testid="stButton"] > button[kind="tertiary"] {
    margin-top: -5.6rem;
    height: 5.6rem;
    width: 100%;
    background: transparent !important;
    border: 1px solid transparent !important;
    color: transparent !important;
    border-radius: 0.6rem !important;
}
div[data-testid="stButton"] > button[kind="tertiary"]:hover {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

rag_colors = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}

col_left, col_right = st.columns([6, 4])

with col_left:
    overdue_sql = """
        SELECT  m.name        AS milestone,
                w.name        AS workstream,
                w.id          AS workstream_id,
                m.due_date,
                (CURRENT_DATE - m.due_date) AS days_overdue,
                r.rag_status
        FROM    milestones  m
        JOIN    workstreams w ON w.id = m.workstream_id
        LEFT JOIN rag_scores r ON r.workstream_id = w.id
        JOIN    workstream_members wm ON wm.workstream_id = w.id
        WHERE   wm.user_id          = %s
          AND   wm.is_former_member = FALSE
          AND   m.status           != 'complete'
          AND   m.due_date          < CURRENT_DATE
        ORDER BY days_overdue DESC
    """
    try:
        overdue_items_df = query_df(overdue_sql, (current_user_id,))
    except Exception:
        overdue_items_df = pd.DataFrame()

    st.markdown("### Overdue Milestones")
    if overdue_items_df.empty:
        st.success("No overdue milestones - you're on track!")
    else:
        for idx, row in overdue_items_df.iterrows():
            ws_id = row.get("workstream_id")
            ws_name = html.escape(str(row.get("workstream") or "Unnamed Workstream"))
            milestone_name = html.escape(str(row.get("milestone") or "Untitled Milestone"))
            rag_status = str(row.get("rag_status") or "green").lower()
            ws_color = rag_colors.get(rag_status, "#888")

            days_overdue_num = pd.to_numeric(row.get("days_overdue"), errors="coerce")
            days_overdue = int(days_overdue_num) if pd.notna(days_overdue_num) else 0
            if days_overdue > 14:
                row_bg = "#E74C3C22"
                day_color = "#E74C3C"
            elif days_overdue >= 7:
                row_bg = "#F39C1222"
                day_color = "#F39C12"
            else:
                row_bg = "#F39C1211"
                day_color = "#F39C12"

            due_date_dt = pd.to_datetime(row.get("due_date"), errors="coerce")
            due_date_text = due_date_dt.strftime("%Y-%m-%d") if pd.notna(due_date_dt) else "Unknown"

            st.markdown(
                f"""
                <div style="background:{row_bg}; border-radius:0.6rem; border:1px solid rgba(255,255,255,0.08);
                            padding:0.8rem 0.95rem; margin-bottom:0.45rem; min-height:5.6rem;">
                    <div style="display:flex; justify-content:space-between; gap:0.8rem;">
                        <div>
                            <div style="font-size:0.85rem; color:{ws_color}; font-weight:700;">{ws_name}</div>
                            <div style="font-size:0.98rem; color:#FFFFFF; font-weight:600; margin-top:0.1rem;">{milestone_name}</div>
                            <div style="font-size:0.78rem; color:rgba(255,255,255,0.68); margin-top:0.15rem;">Due: {due_date_text}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:1.35rem; color:{day_color}; font-weight:800;">{days_overdue}</div>
                            <div style="font-size:0.74rem; color:rgba(255,255,255,0.65);">days overdue</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Open overdue {idx}",
                key=f"open_overdue_{idx}_{ws_id}",
                use_container_width=True,
                type="tertiary",
            ):
                st.session_state["open_workstream_id"] = ws_id
                st.switch_page("pages/workstream.py")

with col_right:
    blockers_sql = """
        SELECT  b.description,
                b.date_raised,
                (CURRENT_DATE - b.date_raised) AS age_days,
                w.name  AS workstream,
                w.id    AS workstream_id,
                r.rag_status
        FROM    blockers    b
        JOIN    workstreams w  ON w.id = b.workstream_id
        LEFT JOIN rag_scores r ON r.workstream_id = w.id
        JOIN    workstream_members wm ON wm.workstream_id = w.id
        WHERE   wm.user_id          = %s
          AND   wm.is_former_member = FALSE
          AND   b.status            = 'open'
        ORDER BY age_days DESC
        LIMIT 6
    """
    try:
        blocker_items_df = query_df(blockers_sql, (current_user_id,))
    except Exception:
        blocker_items_df = pd.DataFrame()

    st.markdown("### Oldest Open Blockers")
    if blocker_items_df.empty:
        st.info("No open blockers")
    else:
        for idx, row in blocker_items_df.iterrows():
            ws_id = row.get("workstream_id")
            ws_name = html.escape(str(row.get("workstream") or "Unnamed Workstream"))
            rag_status = str(row.get("rag_status") or "green").lower()
            ws_color = rag_colors.get(rag_status, "#888")

            age_days_num = pd.to_numeric(row.get("age_days"), errors="coerce")
            age_days = int(age_days_num) if pd.notna(age_days_num) else 0
            if age_days > 7:
                age_color = "#E74C3C"
            elif age_days >= 3:
                age_color = "#F39C12"
            else:
                age_color = "#27AE60"

            description = str(row.get("description") or "")
            if len(description) > 100:
                description = description[:100].rstrip() + "..."
            description_html = html.escape(description)

            st.markdown(
                f"""
                <div style="background:rgba(255,255,255,0.04); border-radius:0.55rem;
                            border:1px solid rgba(255,255,255,0.08); border-left:4px solid {age_color};
                            padding:0.75rem 0.9rem; margin-bottom:0.5rem; min-height:5.6rem;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.8rem;">
                        <div style="font-size:0.84rem; color:{ws_color}; font-weight:700;">{ws_name}</div>
                        <div style="font-size:1.35rem; color:{age_color}; font-weight:800; line-height:1;">{age_days}</div>
                    </div>
                    <div style="font-size:0.8rem; color:rgba(255,255,255,0.82); margin-top:0.25rem;">{description_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Open blocker {idx}",
                key=f"open_blocker_{idx}_{ws_id}",
                use_container_width=True,
                type="tertiary",
            ):
                st.session_state["open_workstream_id"] = ws_id
                st.switch_page("pages/workstream.py")


def time_ago(created_at) -> str:
    ts = pd.to_datetime(created_at, errors="coerce", utc=True)
    if pd.isna(ts):
        return "unknown"
    delta_minutes = int((pd.Timestamp.now(tz="UTC") - ts).total_seconds() // 60)
    if delta_minutes < 60:
        return f"{max(delta_minutes, 1)}m ago"
    if delta_minutes < 24 * 60:
        return f"{delta_minutes // 60}h ago"
    return f"{delta_minutes // (24 * 60)}d ago"


activity_sql = """
    SELECT  'update'      AS item_type,
            u.title       AS content_title,
            u.body        AS content_body,
            u.post_type   AS sub_type,
            usr.display_name AS author,
            w.name        AS workstream,
            w.id          AS workstream_id,
            u.created_at
    FROM    updates u
    JOIN    workstreams w           ON w.id  = u.workstream_id
    JOIN    public.users usr        ON usr.id = u.author_id
    JOIN    workstream_members wm   ON wm.workstream_id = w.id
    WHERE   wm.user_id          = %s
      AND   wm.is_former_member = FALSE
    UNION ALL
    SELECT  'comment'     AS item_type,
            NULL          AS content_title,
            c.body        AS content_body,
            c.entity_type AS sub_type,
            usr.display_name AS author,
            w.name        AS workstream,
            w.id          AS workstream_id,
            c.created_at
    FROM    comments c
    JOIN    workstreams w           ON w.id  = c.entity_id AND c.entity_type = 'workstream'
    JOIN    public.users usr        ON usr.id = c.author_id
    JOIN    workstream_members wm   ON wm.workstream_id = w.id
    WHERE   wm.user_id          = %s
      AND   wm.is_former_member = FALSE
    ORDER BY created_at DESC
    LIMIT 15
"""

try:
    activity_df = query_df(activity_sql, (current_user_id, current_user_id))
except Exception:
    activity_df = pd.DataFrame()

st.markdown("### Recent Activity")
if activity_df.empty:
    st.info("No recent activity yet.")
else:
    for act_idx, (_, row) in enumerate(activity_df.iterrows()):
        author = str(row.get("author") or "Unknown")
        author_initial = author.strip()[0].upper() if author.strip() else "?"
        author_html = html.escape(author)
        workstream_html = html.escape(str(row.get("workstream") or "Unknown Workstream"))

        item_type = str(row.get("item_type") or "")
        action_text = "posted an update to" if item_type == "update" else "commented on"

        title = str(row.get("content_title") or "").strip()
        body = str(row.get("content_body") or "").strip()
        preview_source = f"{title} - {body}" if title else body
        if len(preview_source) > 80:
            preview_source = preview_source[:80].rstrip() + "..."
        preview_html = html.escape(preview_source)
        time_text = time_ago(row.get("created_at"))
        ws_id_act = str(row.get("workstream_id") or "")

        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.9rem;
                        background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
                        border-radius:0.55rem; padding:0.65rem 0.8rem; margin-bottom:0.42rem; min-height:5.6rem;">
                <div style="display:flex; align-items:flex-start; gap:0.7rem; min-width:0;">
                    <div style="width:28px; height:28px; border-radius:50%; background:#4DB6AC; color:#FFFFFF;
                                display:flex; align-items:center; justify-content:center; font-size:0.75rem; font-weight:700; flex-shrink:0;">
                        {author_initial}
                    </div>
                    <div style="min-width:0;">
                        <div style="font-size:0.82rem; color:rgba(255,255,255,0.86);">
                            <span style="color:#4DB6AC; font-weight:700;">{author_html}</span>
                            {action_text}
                            <span style="color:#FFFFFF; font-weight:700;">{workstream_html}</span>
                        </div>
                        <div style="font-size:0.78rem; color:rgba(255,255,255,0.58); margin-top:0.1rem;">
                            {preview_html}
                        </div>
                    </div>
                </div>
                <div style="font-size:0.75rem; color:rgba(255,255,255,0.55); white-space:nowrap;">{time_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            f"Open activity {act_idx}",
            key=f"act_{act_idx}_{ws_id_act}",
            use_container_width=True,
            type="tertiary",
        ):
            st.session_state["open_workstream_id"] = ws_id_act
            st.switch_page("pages/workstream.py")

if workstream_ids:
    try:
        for ws_id in workstream_ids:
            query_df(
                """
                INSERT INTO user_workstream_last_seen (user_id, workstream_id, last_seen_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id, workstream_id)
                DO UPDATE SET last_seen_at = NOW()
                """,
                (current_user_id, ws_id),
            )
    except Exception:
        pass
