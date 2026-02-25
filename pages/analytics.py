"""
pages/analytics.py
Portfolio deep-dive intelligence page.
"""

import html
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
            _display_name = (
                _dn_df.iloc[0]["display_name"] if not _dn_df.empty else ""
            )
        except Exception:
            _display_name = ""
        if _display_name:
            st.markdown(f"**{_display_name}**")
        st.caption(getattr(_sidebar_user, "email", ""))
    if st.button("Sign Out", key="sidebar_signout_analytics"):
        logout()

current_user_id = get_current_user_id()

_SQL = """
    SELECT  w.id, w.name, w.phase, w.start_date, w.end_date,
            wm.role,
            r.rag_status, r.composite_score, r.schedule_score,
            r.budget_score, r.blocker_score, r.is_stale,
            r.calculated_at
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

if df_all.empty:
    st.info("No workstream data available yet.")
    st.stop()

df_all["rag_status"] = df_all["rag_status"].fillna("green")
for score_col in ["composite_score", "schedule_score", "budget_score", "blocker_score"]:
    df_all[score_col] = pd.to_numeric(df_all[score_col], errors="coerce").fillna(0)

st.markdown(
    """
<div style="background:linear-gradient(90deg,#1B4F72 0%,#2E86C1 100%);
            border-radius:0.6rem; padding:1rem 1.4rem 0.9rem; margin-bottom:1.2rem;">
  <h1 style="color:#FFFFFF; font-size:1.8rem; font-weight:700; margin:0 0 0.2rem 0;">
     Portfolio Analytics
  </h1>
  <p style="color:rgba(255,255,255,0.82); font-size:0.88rem; margin:0;">
    Deep-dive intelligence across all your workstreams.
  </p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("## Portfolio Health Snapshot")

history_sql = """
    SELECT  h.snapshot_date,
            h.composite_score,
            w.name AS workstream
    FROM    rag_score_history h
    JOIN    workstreams w ON w.id = h.workstream_id
    JOIN    workstream_members wm ON wm.workstream_id = w.id
    WHERE   wm.user_id = %s
      AND   wm.is_former_member = FALSE
    ORDER BY h.snapshot_date ASC
"""
try:
    history_df = query_df(history_sql, (current_user_id,))
except Exception:
    history_df = pd.DataFrame()

if history_df.empty:
    st.info("No score history available yet.")
else:
    history_df["snapshot_date"] = pd.to_datetime(history_df["snapshot_date"], errors="coerce")
    history_df["composite_score"] = pd.to_numeric(history_df["composite_score"], errors="coerce")
    history_df = history_df.dropna(subset=["snapshot_date", "composite_score", "workstream"])

    if history_df.empty:
        st.info("No score history available yet.")
    else:
        ws_names = sorted(history_df["workstream"].unique().tolist())
        options = ["All Workstreams"] + ws_names
        selected = st.selectbox("Filter by workstream:", options, key="trend_ws_select")

        if selected != "All Workstreams":
            chart_df = history_df[history_df["workstream"] == selected]
        else:
            chart_df = history_df

        fig1 = go.Figure()

        fig1.add_hrect(y0=70, y1=100, fillcolor="rgba(39,174,96,0.08)", line_width=0, layer="below")
        fig1.add_hrect(y0=40, y1=70, fillcolor="rgba(243,156,18,0.08)", line_width=0, layer="below")
        fig1.add_hrect(y0=0, y1=40, fillcolor="rgba(231,76,60,0.08)", line_width=0, layer="below")

        fig1.add_hline(y=70, line_dash="dash", line_color="rgba(39,174,96,0.4)", line_width=1)
        fig1.add_hline(y=40, line_dash="dash", line_color="rgba(243,156,18,0.4)", line_width=1)

        line_colors = ["#4DB6AC", "#5DADE2", "#F39C12", "#E74C3C", "#9B59B6", "#E67E22", "#1ABC9C", "#E91E63"]
        for idx, ws_name in enumerate(chart_df["workstream"].unique()):
            ws_data = chart_df[chart_df["workstream"] == ws_name].sort_values("snapshot_date")
            color = line_colors[idx % len(line_colors)]
            fig1.add_trace(
                go.Scatter(
                    x=ws_data["snapshot_date"],
                    y=ws_data["composite_score"],
                    mode="lines+markers",
                    name=ws_name,
                    line=dict(color=color, width=2.5),
                    marker=dict(size=5, color=color),
                    hovertemplate=f"<b>{ws_name}</b><br>Date: %{{x}}<br>Score: %{{y:.0f}}<extra></extra>",
                )
            )

        fig1.update_layout(
            height=420,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA", family="Arial"),
            yaxis=dict(
                range=[0, 100],
                gridcolor="rgba(255,255,255,0.08)",
                tickfont=dict(color="#FAFAFA"),
                title="Composite Health Score",
                title_font=dict(color="#FAFAFA"),
                tickvals=[0, 20, 40, 60, 70, 80, 100],
            ),
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.06)",
                tickfont=dict(color="#FAFAFA"),
                title="Date",
                title_font=dict(color="#FAFAFA"),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                font=dict(color="#FAFAFA", size=11),
                bgcolor="rgba(255,255,255,0.06)",
                bordercolor="rgba(255,255,255,0.15)",
                borderwidth=1,
            ),
            margin=dict(t=80, b=50, l=70, r=30),
            hoverlabel=dict(bgcolor="#1E2530", font_color="#FAFAFA"),
        )

        fig1.add_annotation(
            x=1.01,
            y=85,
            xref="paper",
            yref="y",
            text=" Green",
            showarrow=False,
            font=dict(color="rgba(39,174,96,0.8)", size=11),
            xanchor="left",
        )
        fig1.add_annotation(
            x=1.01,
            y=55,
            xref="paper",
            yref="y",
            text=" Amber",
            showarrow=False,
            font=dict(color="rgba(243,156,18,0.8)", size=11),
            xanchor="left",
        )
        fig1.add_annotation(
            x=1.01,
            y=20,
            xref="paper",
            yref="y",
            text=" Red",
            showarrow=False,
            font=dict(color="rgba(231,76,60,0.8)", size=11),
            xanchor="left",
        )

        st.plotly_chart(fig1, use_container_width=True)
        st.caption(
            "Composite score = weighted average of Schedule (40%), Budget (35%), and Blocker (25%) health dimensions. Bands show RAG thresholds."
        )

st.markdown("## Schedule vs Budget Matrix")

df_all["rag_color"] = df_all["rag_status"].map(
    {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}
).fillna("#888")

fig2 = px.scatter(
    df_all,
    x="schedule_score",
    y="budget_score",
    color="rag_status",
    color_discrete_map={"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"},
    text="name",
    size="composite_score",
    size_max=40,
    labels={"schedule_score": "Schedule Score", "budget_score": "Budget Score", "rag_status": "Status"},
    hover_data={"composite_score": True, "blocker_score": True},
)
fig2.update_traces(textposition="top center", textfont=dict(color="#FAFAFA", size=11))
fig2.update_layout(
    height=500,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#FAFAFA", family="Arial"),
    xaxis=dict(
        range=[0, 105],
        gridcolor="rgba(255,255,255,0.08)",
        tickfont=dict(color="#FAFAFA"),
        title_font=dict(color="#FAFAFA"),
    ),
    yaxis=dict(
        range=[0, 105],
        gridcolor="rgba(255,255,255,0.08)",
        tickfont=dict(color="#FAFAFA"),
        title_font=dict(color="#FAFAFA"),
    ),
    legend=dict(font=dict(color="#FAFAFA"), bgcolor="rgba(255,255,255,0.06)"),
    margin=dict(t=40, b=60, l=60, r=30),
)
fig2.add_hline(y=70, line_dash="dash", line_color="rgba(255,255,255,0.2)")
fig2.add_vline(x=70, line_dash="dash", line_color="rgba(255,255,255,0.2)")
for label, x_val, y_val in [
    ("✅ Healthy", 85, 85),
    ("⚠️ Budget Risk", 85, 20),
    ("⚠️ Schedule Risk", 20, 85),
    (" At Risk", 20, 20),
]:
    fig2.add_annotation(
        x=x_val,
        y=y_val,
        text=label,
        showarrow=False,
        font=dict(color="rgba(255,255,255,0.35)", size=11),
    )
st.plotly_chart(fig2, use_container_width=True)
st.caption(
    "Each bubble represents one workstream. "
    "X axis = Schedule Health score (0–100). "
    "Y axis = Budget Health score (0–100). "
    "Bubble size = composite score — larger means healthier overall. "
    "Color = current RAG status. "
    "Top-right quadrant = on schedule AND on budget. "
    "Bottom-left = at risk on both dimensions. "
    "Dashed lines mark the Green threshold (70) on each axis."
)

st.markdown("## Milestone Velocity")

milestone_sql = """
    SELECT  w.id AS workstream_id,
            w.name AS workstream,
            r.rag_status,
            COUNT(m.id)                                          AS total,
            COUNT(m.id) FILTER (WHERE m.status = 'complete')    AS complete,
            COUNT(m.id) FILTER (WHERE m.status = 'in_progress') AS in_progress,
            COUNT(m.id) FILTER (WHERE m.status = 'not_started') AS not_started,
            COUNT(m.id) FILTER (WHERE m.status != 'complete' AND m.due_date < CURRENT_DATE) AS overdue
    FROM    workstreams w
    JOIN    workstream_members wm ON wm.workstream_id = w.id
    LEFT JOIN milestones m ON m.workstream_id = w.id
    LEFT JOIN rag_scores r ON r.workstream_id = w.id
    WHERE   wm.user_id = %s
      AND   wm.is_former_member = FALSE
      AND   w.is_archived = FALSE
    GROUP BY w.id, w.name, r.rag_status
    ORDER BY overdue DESC, total DESC
"""
try:
    milestone_df = query_df(milestone_sql, (current_user_id,))
except Exception:
    milestone_df = pd.DataFrame()

if not milestone_df.empty:
    for col in ["total", "complete", "in_progress", "not_started", "overdue"]:
        milestone_df[col] = pd.to_numeric(milestone_df[col], errors="coerce").fillna(0).astype(int)
    milestone_df["completion_rate"] = (
        milestone_df["complete"] / milestone_df["total"].replace(0, 1) * 100
    ).round(0).astype(int)

    rag_colors = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}

    def make_score_bar(rate_value: int) -> str:
        rate_clamped = max(0, min(100, int(rate_value)))
        bar_color = "#27AE60" if rate_clamped >= 70 else "#F39C12" if rate_clamped >= 40 else "#E74C3C"
        return (
            "<div style='background:rgba(255,255,255,0.1); border-radius:999px; height:8px; width:130px;'>"
            + "<div style='background:"
            + bar_color
            + "; width:"
            + str(rate_clamped)
            + "%; height:8px; border-radius:999px;'></div></div>"
        )

    table_html = """
    <div style="border:1px solid rgba(255,255,255,0.08); border-radius:0.6rem; overflow:hidden; margin-bottom:1rem;">
      <div style="display:grid; grid-template-columns:2.2fr 1.2fr 1fr 1fr 1.4fr; gap:0.4rem; background:rgba(255,255,255,0.06); padding:0.6rem 0.8rem; font-size:0.78rem; font-weight:700; color:#FAFAFA;">
        <div>Workstream</div><div>Not Started</div><div>In Progress</div><div>Overdue</div><div>Completion Rate</div>
      </div>
    """

    for idx, row in milestone_df.iterrows():
        row_bg = "rgba(255,255,255,0.02)" if idx % 2 == 0 else "rgba(255,255,255,0.04)"
        rag_status = str(row.get("rag_status") or "green").lower()
        ws_color = rag_colors.get(rag_status, "#888")
        ws_name = html.escape(str(row.get("workstream") or "Unknown"))

        not_started = int(row["not_started"])
        in_progress = int(row["in_progress"])
        overdue = int(row["overdue"])
        completion_rate = int(row["completion_rate"])

        overdue_style = "color:#E74C3C; font-weight:800;" if overdue > 0 else "color:#27AE60; font-weight:700;"
        in_progress_style = "color:#F39C12;" if in_progress > 0 else "color:rgba(255,255,255,0.5);"

        table_html += (
            "<div style='display:grid; grid-template-columns:2.2fr 1.2fr 1fr 1fr 1.4fr; gap:0.4rem; background:"
            + row_bg
            + "; padding:0.62rem 0.8rem; font-size:0.8rem; color:rgba(255,255,255,0.86); align-items:center;'>"
            + "<div style='color:"
            + ws_color
            + "; font-weight:700;'>"
            + ws_name
            + "</div>"
            + "<div style='color:rgba(255,255,255,0.6);'>"
            + str(not_started)
            + "</div>"
            + "<div style='"
            + in_progress_style
            + "'>"
            + str(in_progress)
            + "</div>"
            + "<div style='"
            + overdue_style
            + "'>"
            + str(overdue)
            + "</div>"
            + "<div style='display:flex; align-items:center; gap:0.45rem;'>"
            + make_score_bar(completion_rate)
            + "<span style='font-size:0.74rem;'>"
            + str(completion_rate)
            + "%</span></div></div>"
        )

    table_html += "</div>"
    st.markdown(table_html, unsafe_allow_html=True)
else:
    st.info("No milestone data yet.")

st.markdown("## Open Blocker Age Analysis")

blocker_sql = """
    SELECT  b.description,
            b.date_raised,
            (CURRENT_DATE - b.date_raised) AS age_days,
            w.name AS workstream,
            w.id   AS workstream_id,
            r.rag_status,
            COUNT(c.id) AS comment_count
    FROM    blockers b
    JOIN    workstreams w ON w.id = b.workstream_id
    LEFT JOIN rag_scores r ON r.workstream_id = w.id
    LEFT JOIN comments c ON c.entity_id = b.id AND c.entity_type = 'blocker'
    JOIN    workstream_members wm ON wm.workstream_id = w.id
    WHERE   wm.user_id          = %s
      AND   wm.is_former_member = FALSE
      AND   b.status            = 'open'
    GROUP BY b.id, b.description, b.date_raised, w.name, w.id, r.rag_status
    ORDER BY age_days DESC
"""
try:
    blocker_df = query_df(blocker_sql, (current_user_id,))
except Exception:
    blocker_df = pd.DataFrame()

if blocker_df.empty:
    st.success("No open blockers across your portfolio ✅")
else:
    rag_colors = {"green": "#27AE60", "amber": "#F39C12", "red": "#E74C3C"}
    for _, row in blocker_df.iterrows():
        age_days_raw = pd.to_numeric(row.get("age_days"), errors="coerce")
        age_days = int(age_days_raw) if pd.notna(age_days_raw) else 0
        if age_days > 7:
            age_color = "#E74C3C"
            row_bg = "#E74C3C18"
        elif age_days >= 3:
            age_color = "#F39C12"
            row_bg = "#F39C1218"
        else:
            age_color = "#27AE60"
            row_bg = "rgba(255,255,255,0.03)"

        rag_status = str(row.get("rag_status") or "green").lower()
        ws_color = rag_colors.get(rag_status, "#888")
        ws_name = html.escape(str(row.get("workstream") or "Unknown"))

        description = str(row.get("description") or "")
        description_html = html.escape(description)
        comments_count = int(pd.to_numeric(row.get("comment_count"), errors="coerce") or 0)
        comment_text = f"{comments_count} comment{'s' if comments_count != 1 else ''}"

        st.markdown(
            f"""
            <div style="display:grid; grid-template-columns:0.7fr 1.6fr 3fr 1fr; gap:0.7rem; align-items:center;
                        background:{row_bg}; border-left:4px solid {age_color}; border-radius:0.45rem;
                        border:1px solid rgba(255,255,255,0.08); padding:0.62rem 0.8rem; margin-bottom:0.38rem;">
                <div style="font-size:1.2rem; font-weight:800; color:{age_color}; text-align:center;">{age_days}</div>
                <div style="font-size:0.84rem; font-weight:700; color:{ws_color};">{ws_name}</div>
                <div style="font-size:0.8rem; color:rgba(255,255,255,0.85);">{description_html}</div>
                <div style="font-size:0.76rem; color:rgba(255,255,255,0.65); text-align:right;">{comment_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    blocker_counts = blocker_df.groupby("workstream").size().reset_index(name="count").sort_values("count", ascending=True)
    fig4 = go.Figure(
        go.Bar(
            x=blocker_counts["count"],
            y=blocker_counts["workstream"],
            orientation="h",
            marker_color="#8E44AD",
        )
    )
    fig4.update_layout(
        height=max(200, len(blocker_counts) * 45),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#FAFAFA", family="Arial"),
        xaxis=dict(tickfont=dict(color="#FAFAFA"), gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(tickfont=dict(color="#FAFAFA")),
        margin=dict(t=20, b=30, l=160, r=30),
        title=dict(text="Open Blockers by Workstream", font=dict(color="#FAFAFA", size=16)),
    )
    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
    st.plotly_chart(fig4, use_container_width=True)
