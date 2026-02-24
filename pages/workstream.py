"""
pages/workstream.py
Workstream detail view — tabs: Overview, Milestones, Budget, Blockers, Updates, Team.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timezone
from pipeline.auth import (
    require_auth,
    get_current_user,
    get_current_user_id,
    get_user_role,
    is_contributor_or_above,
    logout,
)
from pipeline.db import query_df, run_query
from pipeline.invite import generate_invite_link, get_active_invite_url
from pipeline.scoring import calculate_rag


def rag_badge(status: str) -> str:
    """Return the uppercase RAG status label."""
    return str(status or "unknown").upper()


require_auth()

# ─── Sidebar navigation ───────────────────────────────────────────────────────

with st.sidebar:
    st.page_link("pages/dashboard.py", label="📊 Portfolio")
    st.page_link("pages/create_workstream.py", label="➕ New Workstream")
    st.divider()
    _sidebar_user = get_current_user()
    if _sidebar_user:
        _sidebar_uid = _sidebar_user.get("id")
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
        st.caption(_sidebar_user.get("email", ""))
    if st.button("Sign Out", key="sidebar_signout_ws"):
        logout()

workstream_id = st.query_params.get("id", None)
if workstream_id is None:
    st.error("No workstream specified.")
    st.stop()

if isinstance(workstream_id, list):
    workstream_id = workstream_id[0] if workstream_id else None
if not workstream_id:
    st.error("No workstream specified.")
    st.stop()

try:
    df = query_df(
        """
        SELECT w.*,
               wz.q1_work_type, wz.q2_deadline_nature, wz.q3_deliverable_type,
               wz.q4_budget_exposure, wz.q5_dependency_level, wz.q6_risk_level,
               wz.q7_phase, wz.q8_update_frequency, wz.q9_audience,
               r.rag_status, r.composite_score, r.schedule_score,
               r.budget_score, r.blocker_score, r.is_stale
        FROM workstreams w
        LEFT JOIN wizard_config wz ON wz.workstream_id = w.id
        LEFT JOIN rag_scores r ON r.workstream_id = w.id
        WHERE w.id = %s
        """,
        (workstream_id,),
    )
except Exception:
    st.error("Unable to connect to database. Please try again.")
    st.stop()

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

tab_overview, tab_milestones, tab_budget, tab_blockers, tab_updates, tab_team = st.tabs([
    " Overview", " Milestones", " Budget",
    " Blockers", " Updates", " Team"
])

with tab_overview:
    # PHASE 4 PROMPT 8 — Overview tab content

    def _relative_time_ov(dt):
        dt = pd.to_datetime(dt, errors="coerce")
        if pd.isna(dt):
            return "unknown"
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        else:
            dt = dt.tz_convert("UTC")
        delta = datetime.now(timezone.utc) - dt.to_pydatetime()
        if delta.days >= 1:
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours}h ago"
        return f"{delta.seconds // 60}m ago"

    def _score_status(score):
        if score >= 70:
            return "On Track", "#27AE60"
        elif score >= 40:
            return "Monitor", "#F39C12"
        return "At Risk", "#E74C3C"

    # ── ROW 1 — Score cards ──────────────────────────────────────────────────
    milestone_counts_df = query_df(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END), 0) AS completed
        FROM milestones
        WHERE workstream_id = %s
        """,
        (workstream_id,),
    )
    ms_total = int(milestone_counts_df.iloc[0]["total"]) if not milestone_counts_df.empty else 0
    ms_complete = int(milestone_counts_df.iloc[0]["completed"] or 0) if not milestone_counts_df.empty else 0

    spend_ov_df = query_df(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM spend_entries WHERE workstream_id = %s",
        (workstream_id,),
    )
    actual_spend_ov = float(spend_ov_df.iloc[0]["total"]) if not spend_ov_df.empty else 0.0
    planned_budget_ov = float(ws.get("planned_budget") or 0)

    blocker_count_df = query_df(
        "SELECT COUNT(*) AS cnt FROM blockers WHERE workstream_id = %s AND status = 'open'",
        (workstream_id,),
    )
    open_blockers = int(blocker_count_df.iloc[0]["cnt"]) if not blocker_count_df.empty else 0

    schedule_score = int(ws.get("schedule_score") or 0)
    budget_score = int(ws.get("budget_score") or 0)
    blocker_score = int(ws.get("blocker_score") or 0)

    col_sched, col_budg, col_block = st.columns(3)

    with col_sched:
        s_label, s_colour = _score_status(schedule_score)
        st.markdown("**Schedule Health**")
        st.markdown(
            f"<span style='font-size:2rem; font-weight:700;'>{schedule_score} / 100</span>",
            unsafe_allow_html=True,
        )
        st.progress(schedule_score / 100)
        st.markdown(
            f"<span style='color:{s_colour}; font-weight:600;'>{s_label}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"{ms_complete} of {ms_total} milestones complete")

    with col_budg:
        b_label, b_colour = _score_status(budget_score)
        st.markdown("**Budget Health**")
        st.markdown(
            f"<span style='font-size:2rem; font-weight:700;'>{budget_score} / 100</span>",
            unsafe_allow_html=True,
        )
        st.progress(budget_score / 100)
        st.markdown(
            f"<span style='color:{b_colour}; font-weight:600;'>{b_label}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"£{actual_spend_ov:,.0f} spent of £{planned_budget_ov:,.0f} planned")

    with col_block:
        bl_label, bl_colour = _score_status(blocker_score)
        st.markdown("**Blocker Health**")
        st.markdown(
            f"<span style='font-size:2rem; font-weight:700;'>{blocker_score} / 100</span>",
            unsafe_allow_html=True,
        )
        st.progress(blocker_score / 100)
        st.markdown(
            f"<span style='color:{bl_colour}; font-weight:600;'>{bl_label}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"{open_blockers} open blocker{'s' if open_blockers != 1 else ''}")

    st.divider()

    # ── ROW 2 — Details + Wizard Config ──────────────────────────────────────
    col_details, col_wizard = st.columns([3, 2])

    with col_details:
        st.markdown("### Details")

        owner_id = ws.get("owner_id")
        owner_df = query_df(
            "SELECT display_name FROM users WHERE id = %s",
            (owner_id,),
        )
        owner_name = owner_df.iloc[0]["display_name"] if not owner_df.empty else "Unknown"

        phase_raw = str(ws.get("phase") or "")
        phase_labels_map = {
            "discovery": "Discovery",
            "planning": "Planning",
            "in_flight": "In Flight",
            "review_closing": "Review & Closing",
        }
        phase_label = phase_labels_map.get(phase_raw, phase_raw.replace("_", " ").title())

        start_ts = pd.to_datetime(ws.get("start_date"), errors="coerce")
        end_ts = pd.to_datetime(ws.get("end_date"), errors="coerce")
        start_str = start_ts.strftime("%Y-%m-%d") if pd.notna(start_ts) else "Not set"
        end_str = end_ts.strftime("%Y-%m-%d") if pd.notna(end_ts) else "Not set"

        if pd.notna(end_ts):
            end_ts_tz = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts.tz_convert("UTC")
            today_utc_ov = pd.Timestamp.now(tz="UTC").normalize()
            days_rem = int((end_ts_tz.normalize() - today_utc_ov).days)
            days_remaining_str = (
                f"{days_rem} days" if days_rem >= 0 else f"Overdue by {abs(days_rem)} days"
            )
        else:
            days_remaining_str = "No deadline"

        st.markdown(f"**Name:** {ws.get('name', '')}")
        desc = ws.get("description") or ""
        if desc:
            st.markdown(f"**Description:** {desc}")
        st.markdown(f"**Start date:** {start_str}")
        st.markdown(f"**End date:** {end_str}")
        st.markdown(f"**Days remaining:** {days_remaining_str}")
        st.markdown(f"**Phase:** {phase_label}")
        st.markdown(f"**Owner:** {owner_name}")

    with col_wizard:
        st.markdown("### Scoring Profile")

        WIZARD_LABELS = {
            "q1_work_type": ("Work Type", {
                "delivery": "Delivery", "analysis": "Analysis",
                "process_improvement": "Process Improvement", "reporting": "Reporting",
                "strategy": "Strategy", "other": "Other",
            }),
            "q2_deadline_nature": ("Deadline Nature", {
                "hard_contractual": "Hard / Contractual", "business_driven": "Business-Driven",
                "self_imposed": "Self-Imposed", "ongoing": "Ongoing",
            }),
            "q3_deliverable_type": ("Deliverable Type", {
                "document_report": "Document / Report", "decision_approval": "Decision / Approval",
                "built_solution": "Built Solution", "process_change": "Process Change",
                "recommendation": "Recommendation",
            }),
            "q4_budget_exposure": ("Budget Exposure", {
                "client_billable": "Client-Billable", "approved_internal": "Approved Internal Budget",
                "informal_none": "Informal / No Budget",
            }),
            "q5_dependency_level": ("Dependency Level", {
                "self_contained": "Self-Contained", "depends_1_2": "Depends on 1-2 Others",
                "depends_multiple": "Depends on Multiple Teams",
                "blocked_external": "Blocked by External Party",
            }),
            "q6_risk_level": ("Stakeholder Sensitivity", {
                "low": "Low", "medium": "Medium", "high": "High", "critical": "Critical",
            }),
            "q7_phase": ("Current Phase", {
                "discovery": "Discovery", "planning": "Planning",
                "in_flight": "In Flight", "review_closing": "Review & Closing",
            }),
            "q8_update_frequency": ("Update Frequency", {
                "daily": "Daily", "weekly": "Weekly", "biweekly": "Bi-Weekly", "monthly": "Monthly",
            }),
            "q9_audience": ("Audience", {
                "just_me": "Just Me", "my_team": "My Team",
                "senior_leadership": "Senior Leadership", "external_client": "External Client",
            }),
        }

        wizard_rows = []
        for col_key, (label, mapping) in WIZARD_LABELS.items():
            raw_val = str(ws.get(col_key) or "")
            human_val = mapping.get(raw_val, raw_val.replace("_", " ").title()) if raw_val else "—"
            wizard_rows.append({"Question": label, "Answer": human_val})

        st.dataframe(pd.DataFrame(wizard_rows), use_container_width=True, hide_index=True)

        if user_role == "owner":
            if st.button("Re-run wizard", key="overview_rerun_wizard"):
                st.info("Wizard re-run coming soon.")

    st.divider()

    # ── ROW 3 — Discussion ────────────────────────────────────────────────────
    st.markdown("### Discussion")

    ws_comments_df = query_df(
        """
        SELECT c.body, c.created_at, c.is_former_member, u.display_name
        FROM comments c
        JOIN users u ON u.id = c.author_id
        WHERE c.entity_type = 'workstream' AND c.entity_id = %s
        ORDER BY c.created_at ASC
        """,
        (workstream_id,),
    )

    if ws_comments_df.empty:
        st.caption("No comments yet.")
    else:
        for _, ws_comment in ws_comments_df.iterrows():
            author = str(ws_comment.get("display_name") or "Unknown")
            is_former = bool(ws_comment.get("is_former_member"))
            time_ago = _relative_time_ov(ws_comment.get("created_at"))
            body = str(ws_comment.get("body") or "")

            former_suffix = (
                " · <span style='color:#9AA0A6;'>Former member</span>" if is_former else ""
            )
            st.markdown(
                f"**{author}** · {time_ago}{former_suffix}",
                unsafe_allow_html=True,
            )
            st.write(body)
            st.divider()

    if user_role in ("owner", "contributor"):
        current_user_id_ov = get_current_user_id()
        new_ws_comment = st.text_area(
            "Add a comment",
            key="overview_new_comment",
            height=100,
        )
        if st.button("Post", key="overview_post_comment"):
            if not (new_ws_comment or "").strip():
                st.warning("Comment cannot be empty.")
            elif current_user_id_ov is None:
                st.error("You must be signed in to post comments.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO comments (entity_type, entity_id, body, author_id)
                        VALUES ('workstream', %s, %s, %s)
                        """,
                        (workstream_id, new_ws_comment.strip(), current_user_id_ov),
                    )
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))

with tab_milestones:
    milestones_df = query_df(
        """
        SELECT m.id, m.name, m.due_date, m.status, m.created_at,
               u.display_name as created_by_name
        FROM milestones m
        JOIN users u ON u.id = m.created_by
        WHERE m.workstream_id = %s
        ORDER BY m.due_date ASC
        """,
        (workstream_id,),
    )

    total_milestones = len(milestones_df)
    complete_milestones = 0
    if total_milestones > 0:
        complete_milestones = int((milestones_df["status"] == "complete").sum())

    st.markdown(f"**{complete_milestones} of {total_milestones} milestones complete**")
    st.progress((complete_milestones / total_milestones) if total_milestones > 0 else 0.0)

    can_edit_milestones = user_role in ("owner", "contributor")
    current_user_id = get_current_user_id()
    today_date = date.today()

    if milestones_df.empty:
        st.info("No milestones yet.")
    else:
        status_colours = {
            "not_started": "#7F8C8D",
            "in_progress": "#4DB6AC",
            "complete": "#27AE60",
        }
        valid_statuses = ["not_started", "in_progress", "complete"]

        for _, milestone in milestones_df.iterrows():
            milestone_id = str(milestone["id"])
            milestone_name = milestone.get("name") or "Untitled milestone"
            milestone_status = str(milestone.get("status") or "not_started")
            milestone_due_ts = pd.to_datetime(milestone.get("due_date"), errors="coerce")
            milestone_due_date = (
                milestone_due_ts.date() if pd.notna(milestone_due_ts) else today_date
            )
            created_at_ts = pd.to_datetime(milestone.get("created_at"), errors="coerce")
            created_at_display = (
                created_at_ts.strftime("%Y-%m-%d %H:%M") if pd.notna(created_at_ts) else "Unknown"
            )
            created_by_name = milestone.get("created_by_name") or "Unknown"

            with st.expander(milestone_name, expanded=False):
                badge_colour = status_colours.get(milestone_status, "#7F8C8D")
                st.markdown(
                    f"""
                    <span style="background:{badge_colour}; color:#FFFFFF; padding:0.2rem 0.6rem; border-radius:999px; font-weight:600; font-size:0.78rem;">
                        {milestone_status.replace('_', ' ').upper()}
                    </span>
                    """,
                    unsafe_allow_html=True,
                )
                st.write(f"Due date: {milestone_due_date.isoformat()}")

                if milestone_due_date < today_date and milestone_status != "complete":
                    overdue_days = (today_date - milestone_due_date).days
                    st.markdown(
                        f"<span style='color:#E74C3C;'>⚠️ Overdue by {overdue_days} days</span>",
                        unsafe_allow_html=True,
                    )

                st.caption(f"Created by {created_by_name} on {created_at_display}")

                if can_edit_milestones:
                    status_index = (
                        valid_statuses.index(milestone_status)
                        if milestone_status in valid_statuses
                        else 0
                    )
                    updated_status = st.selectbox(
                        "Status",
                        valid_statuses,
                        index=status_index,
                        key=f"milestone_status_{milestone_id}",
                    )
                    updated_due_date = st.date_input(
                        "Due date",
                        value=milestone_due_date,
                        key=f"milestone_due_{milestone_id}",
                    )

                    col_save, col_delete = st.columns(2)
                    with col_save:
                        if st.button("Save Changes", key=f"save_milestone_{milestone_id}"):
                            try:
                                run_query(
                                    """
                                    UPDATE milestones
                                    SET status = %s, due_date = %s, updated_at = NOW()
                                    WHERE id = %s
                                    """,
                                    (updated_status, updated_due_date, milestone_id),
                                )
                                calculate_rag(workstream_id)
                                query_df.clear()
                                st.rerun()
                            except Exception as error:
                                st.error(str(error))

                    delete_flag_key = f"confirm_delete_milestone_{milestone_id}"
                    with col_delete:
                        if st.button("Delete", key=f"delete_milestone_{milestone_id}"):
                            st.session_state[delete_flag_key] = True

                    if st.session_state.get(delete_flag_key, False):
                        st.warning("Delete this milestone permanently?")
                        col_confirm_delete, col_cancel_delete = st.columns(2)
                        with col_confirm_delete:
                            if st.button("Confirm Delete", key=f"confirm_delete_btn_{milestone_id}"):
                                try:
                                    run_query(
                                        "DELETE FROM milestones WHERE id = %s",
                                        (milestone_id,),
                                    )
                                    st.session_state.pop(delete_flag_key, None)
                                    calculate_rag(workstream_id)
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))
                        with col_cancel_delete:
                            if st.button("Cancel", key=f"cancel_delete_btn_{milestone_id}"):
                                st.session_state.pop(delete_flag_key, None)
                                st.rerun()

                    with st.expander("Comments", expanded=False):
                        comments_df = query_df(
                            """
                            SELECT c.id, c.body, c.created_at, c.is_former_member,
                                   u.display_name AS author_name
                            FROM comments c
                            JOIN users u ON u.id = c.author_id
                            WHERE c.entity_type = 'milestone' AND c.entity_id = %s
                            ORDER BY c.created_at ASC
                            """,
                            (milestone_id,),
                        )

                        if comments_df.empty:
                            st.caption("No comments yet.")
                        else:
                            for _, comment in comments_df.iterrows():
                                comment_author = comment.get("author_name") or "Unknown"
                                if bool(comment.get("is_former_member")):
                                    comment_author = f"{comment_author} (Former member)"

                                comment_created_at = pd.to_datetime(
                                    comment.get("created_at"), errors="coerce"
                                )
                                comment_created_display = (
                                    comment_created_at.strftime("%Y-%m-%d %H:%M")
                                    if pd.notna(comment_created_at)
                                    else "Unknown"
                                )
                                st.markdown(f"**{comment_author}** · {comment_created_display}")
                                st.write(comment.get("body", ""))
                                st.divider()

                        new_comment = st.text_area(
                            "Add comment",
                            key=f"new_milestone_comment_{milestone_id}",
                            height=80,
                        )
                        if st.button("Post", key=f"post_milestone_comment_{milestone_id}"):
                            if not (new_comment or "").strip():
                                st.warning("Comment cannot be empty.")
                            elif current_user_id is None:
                                st.error("You must be signed in to post comments.")
                            else:
                                try:
                                    run_query(
                                        """
                                        INSERT INTO comments (entity_type, entity_id, body, author_id)
                                        VALUES ('milestone', %s, %s, %s)
                                        """,
                                        (milestone_id, new_comment.strip(), current_user_id),
                                    )
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))

                    note_df = query_df(
                        """
                        SELECT body
                        FROM notes
                        WHERE entity_type = 'milestone' AND entity_id = %s
                        LIMIT 1
                        """,
                        (milestone_id,),
                    )

                    note_editing_key = f"editing_milestone_note_{milestone_id}"
                    if not note_df.empty:
                        existing_note = str(note_df.iloc[0]["body"])
                        st.markdown(
                            f"""
                            <div style="background:#FFF7CC; border:1px solid #E6D27A; color:#3D3D3D; padding:0.6rem 0.75rem; border-radius:0.5rem; margin:0.5rem 0;">
                                <strong>Note:</strong> {existing_note}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("Edit Note", key=f"edit_milestone_note_{milestone_id}"):
                            st.session_state[note_editing_key] = True

                        if st.session_state.get(note_editing_key, False):
                            edited_note = st.text_area(
                                "Edit note",
                                value=existing_note,
                                key=f"edit_note_body_{milestone_id}",
                            )
                            if st.button("Save Note", key=f"save_note_{milestone_id}"):
                                if not (edited_note or "").strip():
                                    st.warning("Note cannot be empty.")
                                elif current_user_id is None:
                                    st.error("You must be signed in to save notes.")
                                else:
                                    try:
                                        run_query(
                                            """
                                            INSERT INTO notes (entity_type, entity_id, body, author_id)
                                            VALUES ('milestone', %s, %s, %s)
                                            ON CONFLICT (entity_id)
                                            DO UPDATE
                                            SET body = EXCLUDED.body,
                                                author_id = EXCLUDED.author_id,
                                                updated_at = NOW()
                                            """,
                                            (milestone_id, edited_note.strip(), current_user_id),
                                        )
                                        st.session_state[note_editing_key] = False
                                        query_df.clear()
                                        st.rerun()
                                    except Exception as error:
                                        st.error(str(error))
                    else:
                        new_note = st.text_input(
                            "Add note",
                            key=f"new_milestone_note_{milestone_id}",
                        )
                        if st.button("Save", key=f"save_new_note_{milestone_id}"):
                            if not (new_note or "").strip():
                                st.warning("Note cannot be empty.")
                            elif current_user_id is None:
                                st.error("You must be signed in to save notes.")
                            else:
                                try:
                                    run_query(
                                        """
                                        INSERT INTO notes (entity_type, entity_id, body, author_id)
                                        VALUES ('milestone', %s, %s, %s)
                                        ON CONFLICT (entity_id)
                                        DO UPDATE
                                        SET body = EXCLUDED.body,
                                            author_id = EXCLUDED.author_id,
                                            updated_at = NOW()
                                        """,
                                        (milestone_id, new_note.strip(), current_user_id),
                                    )
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))

    if can_edit_milestones:
        st.markdown("### Add New Milestone")
        new_milestone_name = st.text_input("Milestone name", key="new_milestone_name")
        new_milestone_due_date = st.date_input(
            "Due date",
            min_value=today_date,
            value=today_date,
            key="new_milestone_due_date",
        )
        new_milestone_status = st.selectbox(
            "Status",
            ["not_started", "in_progress", "complete"],
            index=0,
            key="new_milestone_status",
        )

        if st.button("Add Milestone", key="add_milestone_button"):
            if not (new_milestone_name or "").strip():
                st.warning("Milestone name is required.")
            elif current_user_id is None:
                st.error("You must be signed in to add milestones.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO milestones (workstream_id, name, due_date, status, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            workstream_id,
                            new_milestone_name.strip(),
                            new_milestone_due_date,
                            new_milestone_status,
                            current_user_id,
                        ),
                    )
                    calculate_rag(workstream_id)
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))

with tab_budget:
    budget_exposure = ws.get("q4_budget_exposure")
    planned_budget_raw = ws.get("planned_budget")
    if budget_exposure == "informal_none" or planned_budget_raw is None:
        st.info(
            "Budget is not formally tracked for this workstream. Budget Health is suppressed in scoring."
        )

    total_spend_df = query_df(
        """
        SELECT COALESCE(SUM(amount), 0) as total_spent
        FROM spend_entries
        WHERE workstream_id = %s
        """,
        (workstream_id,),
    )

    planned_budget = float(planned_budget_raw or 0)
    actual_spend = (
        float(total_spend_df.iloc[0]["total_spent"])
        if not total_spend_df.empty and total_spend_df.iloc[0]["total_spent"] is not None
        else 0.0
    )
    remaining = planned_budget - actual_spend
    pct_spent = (actual_spend / planned_budget * 100.0) if planned_budget > 0 else 0.0

    col_plan, col_spent, col_remaining, col_pct = st.columns(4)
    with col_plan:
        st.metric("Planned Budget", f"£{planned_budget:,.0f}")
    with col_spent:
        st.metric("Spent to Date", f"£{actual_spend:,.0f}")
    with col_remaining:
        if remaining < 0:
            st.markdown("**Remaining**")
            st.markdown(
                f"<span style='color:#E74C3C; font-size:1.5rem; font-weight:700;'>£{remaining:,.0f}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.metric("Remaining", f"£{remaining:,.0f}")
    with col_pct:
        st.metric("% Spent", f"{pct_spent:.1f}%")

    st.progress(min(pct_spent / 100.0, 1.0))

    spend_log_df = query_df(
        """
        SELECT s.id, s.amount, s.entry_date, s.category, s.description,
               u.display_name as logged_by
        FROM spend_entries s
        JOIN users u ON u.id = s.created_by
        WHERE s.workstream_id = %s
        ORDER BY s.entry_date DESC
        """,
        (workstream_id,),
    )

    st.markdown("### Spend Log")
    if spend_log_df.empty:
        st.info("No spend entries logged yet.")
    else:
        spend_display_df = spend_log_df.copy()
        spend_display_df["Date"] = pd.to_datetime(
            spend_display_df["entry_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        spend_display_df["Category"] = spend_display_df["category"].fillna("")
        spend_display_df["Amount (£)"] = spend_display_df["amount"].apply(
            lambda v: f"£{float(v):,.2f}"
        )
        spend_display_df["Description"] = spend_display_df["description"].fillna("")
        spend_display_df["Logged by"] = spend_display_df["logged_by"].fillna("")

        st.dataframe(
            spend_display_df[["Date", "Category", "Amount (£)", "Description", "Logged by"]],
            use_container_width=True,
            hide_index=True,
        )

    if user_role in ("owner", "contributor"):
        st.markdown("### Add Spend Entry")
        today_date = date.today()
        spend_amount = st.number_input(
            "Amount",
            min_value=0.01,
            step=0.01,
            format="%.2f",
            key="spend_amount_input",
        )
        spend_entry_date = st.date_input(
            "Date",
            value=today_date,
            max_value=today_date,
            key="spend_date_input",
        )
        spend_category = st.text_input(
            "Category",
            placeholder="e.g. Consultancy, Software, Travel",
            key="spend_category_input",
        )
        spend_description = st.text_area(
            "Description (optional)",
            key="spend_description_input",
        )

        if st.button("Log Spend", key="log_spend_button"):
            current_user_id = get_current_user_id()
            if current_user_id is None:
                st.error("You must be signed in to log spend.")
            elif not (spend_category or "").strip():
                st.warning("Category is required.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO spend_entries (
                            workstream_id, amount, entry_date, category, description, created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            workstream_id,
                            float(spend_amount),
                            spend_entry_date,
                            spend_category.strip(),
                            (spend_description or "").strip() or None,
                            current_user_id,
                        ),
                    )
                    calculate_rag(workstream_id)
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))

with tab_blockers:
    # PHASE 4 PROMPT 11 — Blockers tab content

    # ── Wizard-adjusted age thresholds ───────────────────────────────────────
    recent_days = 3
    aging_days = 7

    if ws.get("q5_dependency_level") == "blocked_external":
        recent_days = 1
        aging_days = 3

    q6 = str(ws.get("q6_risk_level") or "")
    if q6 in ("high", "critical"):
        factor = 0.95 if q6 == "high" else 0.90
        recent_days = max(1, int(recent_days * factor))
        aging_days = max(1, int(aging_days * factor))

    def blocker_colour(age_days):
        if age_days < recent_days:
            return "#27AE60"
        elif age_days <= aging_days:
            return "#F39C12"
        return "#E74C3C"

    # ── Load blockers ─────────────────────────────────────────────────────────
    blockers_df = query_df(
        """
        SELECT b.id, b.description, b.date_raised, b.status,
               b.resolution_note, b.resolved_at,
               u.display_name AS raised_by
        FROM blockers b
        JOIN users u ON u.id = b.created_by
        WHERE b.workstream_id = %s
        ORDER BY b.status ASC, b.date_raised ASC
        """,
        (workstream_id,),
    )

    today_date_bl = date.today()
    current_user_id_bl = get_current_user_id()
    can_edit_blockers = user_role in ("owner", "contributor")

    open_bl = blockers_df[blockers_df["status"] == "open"] if not blockers_df.empty else blockers_df
    resolved_bl = (
        blockers_df[blockers_df["status"] == "resolved"] if not blockers_df.empty else blockers_df
    )

    # resolved today
    resolved_today = 0
    if not resolved_bl.empty:
        resolved_at_ts = pd.to_datetime(resolved_bl["resolved_at"], errors="coerce")
        resolved_today = int((resolved_at_ts.dt.date == today_date_bl).sum())

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.markdown(
        f"**{len(open_bl)} open** · **{resolved_today} resolved today**"
    )

    if not open_bl.empty:
        open_ages = []
        for _, ob in open_bl.iterrows():
            dr = pd.to_datetime(ob.get("date_raised"), errors="coerce")
            age = (today_date_bl - dr.date()) if pd.notna(dr) else None
            open_ages.append(age.days if age is not None else 0)
        aged_count = sum(1 for a in open_ages if a > aging_days)
        if aged_count > 0:
            st.markdown(
                f"<div style='background:#FDEDEC; border-left:4px solid #E74C3C; padding:0.6rem 0.9rem; border-radius:0.3rem; margin-bottom:0.75rem;'>"
                f"⚠️ <strong>{aged_count} blocker{'s' if aged_count != 1 else ''} have been open "
                f"for more than {aging_days} days.</strong></div>",
                unsafe_allow_html=True,
            )

    # ── Open blockers ─────────────────────────────────────────────────────────
    if open_bl.empty:
        st.info("No open blockers.")
    else:
        for _, bl in open_bl.iterrows():
            blocker_id = str(bl["id"])
            description = str(bl.get("description") or "")
            date_raised_ts = pd.to_datetime(bl.get("date_raised"), errors="coerce")
            age_days = (
                (today_date_bl - date_raised_ts.date()).days if pd.notna(date_raised_ts) else 0
            )
            date_raised_str = (
                date_raised_ts.strftime("%Y-%m-%d") if pd.notna(date_raised_ts) else "Unknown"
            )
            raised_by = str(bl.get("raised_by") or "Unknown")
            dot_colour = blocker_colour(age_days)

            header_text = (description[:60] + "…") if len(description) > 60 else description
            header_html = (
                f"<span style='color:{dot_colour}; font-size:0.9rem;'>●</span> {header_text}"
            )

            with st.expander(header_text, expanded=False):
                st.markdown(
                    f"<span style='color:{dot_colour}; font-weight:600;'>● {age_days} days open</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Raised by {raised_by} on {date_raised_str}")
                st.write(description)

                if can_edit_blockers:
                    resolve_key = f"resolve_blocker_{blocker_id}"
                    if st.button("Mark Resolved", key=f"resolve_btn_{blocker_id}"):
                        st.session_state[resolve_key] = True

                    if st.session_state.get(resolve_key, False):
                        resolution_note = st.text_area(
                            "Resolution note (optional)",
                            key=f"resolution_note_{blocker_id}",
                            height=80,
                        )
                        col_confirm_res, col_cancel_res = st.columns(2)
                        with col_confirm_res:
                            if st.button("Confirm Resolve", key=f"confirm_resolve_{blocker_id}"):
                                try:
                                    run_query(
                                        """
                                        UPDATE blockers
                                        SET status = 'resolved',
                                            resolution_note = %s,
                                            resolved_at = NOW()
                                        WHERE id = %s
                                        """,
                                        (
                                            (resolution_note or "").strip() or None,
                                            blocker_id,
                                        ),
                                    )
                                    st.session_state.pop(resolve_key, None)
                                    calculate_rag(workstream_id)
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))
                        with col_cancel_res:
                            if st.button("Cancel", key=f"cancel_resolve_{blocker_id}"):
                                st.session_state.pop(resolve_key, None)
                                st.rerun()

                    # Comment thread
                    with st.expander("Comments", expanded=False):
                        bl_comments_df = query_df(
                            """
                            SELECT c.id, c.body, c.created_at, c.is_former_member,
                                   u.display_name AS author_name
                            FROM comments c
                            JOIN users u ON u.id = c.author_id
                            WHERE c.entity_type = 'blocker' AND c.entity_id = %s
                            ORDER BY c.created_at ASC
                            """,
                            (blocker_id,),
                        )

                        if bl_comments_df.empty:
                            st.caption("No comments yet.")
                        else:
                            for _, bl_comment in bl_comments_df.iterrows():
                                bl_author = bl_comment.get("author_name") or "Unknown"
                                if bool(bl_comment.get("is_former_member")):
                                    bl_author = f"{bl_author} (Former member)"
                                bl_created = pd.to_datetime(
                                    bl_comment.get("created_at"), errors="coerce"
                                )
                                bl_created_str = (
                                    bl_created.strftime("%Y-%m-%d %H:%M")
                                    if pd.notna(bl_created)
                                    else "Unknown"
                                )
                                st.markdown(f"**{bl_author}** · {bl_created_str}")
                                st.write(bl_comment.get("body", ""))
                                st.divider()

                        new_bl_comment = st.text_area(
                            "Add comment",
                            key=f"new_blocker_comment_{blocker_id}",
                            height=80,
                        )
                        if st.button("Post", key=f"post_blocker_comment_{blocker_id}"):
                            if not (new_bl_comment or "").strip():
                                st.warning("Comment cannot be empty.")
                            elif current_user_id_bl is None:
                                st.error("You must be signed in to post comments.")
                            else:
                                try:
                                    run_query(
                                        """
                                        INSERT INTO comments (entity_type, entity_id, body, author_id)
                                        VALUES ('blocker', %s, %s, %s)
                                        """,
                                        (blocker_id, new_bl_comment.strip(), current_user_id_bl),
                                    )
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))

                    # Pinned note
                    bl_note_df = query_df(
                        """
                        SELECT body FROM notes
                        WHERE entity_type = 'blocker' AND entity_id = %s
                        LIMIT 1
                        """,
                        (blocker_id,),
                    )

                    bl_note_editing_key = f"editing_blocker_note_{blocker_id}"
                    if not bl_note_df.empty:
                        existing_bl_note = str(bl_note_df.iloc[0]["body"])
                        st.markdown(
                            f"""
                            <div style="background:#FFF7CC; border:1px solid #E6D27A; color:#3D3D3D; padding:0.6rem 0.75rem; border-radius:0.5rem; margin:0.5rem 0;">
                                <strong>Note:</strong> {existing_bl_note}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("Edit Note", key=f"edit_bl_note_{blocker_id}"):
                            st.session_state[bl_note_editing_key] = True

                        if st.session_state.get(bl_note_editing_key, False):
                            edited_bl_note = st.text_area(
                                "Edit note",
                                value=existing_bl_note,
                                key=f"edit_bl_note_body_{blocker_id}",
                            )
                            if st.button("Save Note", key=f"save_bl_note_{blocker_id}"):
                                if not (edited_bl_note or "").strip():
                                    st.warning("Note cannot be empty.")
                                elif current_user_id_bl is None:
                                    st.error("You must be signed in to save notes.")
                                else:
                                    try:
                                        run_query(
                                            """
                                            INSERT INTO notes (entity_type, entity_id, body, author_id)
                                            VALUES ('blocker', %s, %s, %s)
                                            ON CONFLICT (entity_id)
                                            DO UPDATE
                                            SET body = EXCLUDED.body,
                                                author_id = EXCLUDED.author_id,
                                                updated_at = NOW()
                                            """,
                                            (blocker_id, edited_bl_note.strip(), current_user_id_bl),
                                        )
                                        st.session_state[bl_note_editing_key] = False
                                        query_df.clear()
                                        st.rerun()
                                    except Exception as error:
                                        st.error(str(error))
                    else:
                        new_bl_note = st.text_input(
                            "Add note",
                            key=f"new_blocker_note_{blocker_id}",
                        )
                        if st.button("Save", key=f"save_new_bl_note_{blocker_id}"):
                            if not (new_bl_note or "").strip():
                                st.warning("Note cannot be empty.")
                            elif current_user_id_bl is None:
                                st.error("You must be signed in to save notes.")
                            else:
                                try:
                                    run_query(
                                        """
                                        INSERT INTO notes (entity_type, entity_id, body, author_id)
                                        VALUES ('blocker', %s, %s, %s)
                                        ON CONFLICT (entity_id)
                                        DO UPDATE
                                        SET body = EXCLUDED.body,
                                            author_id = EXCLUDED.author_id,
                                            updated_at = NOW()
                                        """,
                                        (blocker_id, new_bl_note.strip(), current_user_id_bl),
                                    )
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))

    # ── Resolved blockers ─────────────────────────────────────────────────────
    with st.expander(f"Resolved ({len(resolved_bl)})", expanded=False):
        if resolved_bl.empty:
            st.caption("No resolved blockers.")
        else:
            resolved_rows = []
            for _, rb in resolved_bl.iterrows():
                resolved_at_ts = pd.to_datetime(rb.get("resolved_at"), errors="coerce")
                resolved_rows.append({
                    "Description": str(rb.get("description") or ""),
                    "Resolved on": (
                        resolved_at_ts.strftime("%Y-%m-%d") if pd.notna(resolved_at_ts) else "—"
                    ),
                    "Resolution note": str(rb.get("resolution_note") or "—"),
                })
            st.dataframe(
                pd.DataFrame(resolved_rows),
                use_container_width=True,
                hide_index=True,
            )

    # ── Add blocker ───────────────────────────────────────────────────────────
    if can_edit_blockers:
        st.markdown("### Log Blocker")
        new_bl_description = st.text_area(
            "Description",
            key="new_blocker_description",
            height=100,
        )
        new_bl_date = st.date_input(
            "Date raised",
            value=today_date_bl,
            max_value=today_date_bl,
            key="new_blocker_date",
        )

        if st.button("Log Blocker", key="log_blocker_button"):
            if not (new_bl_description or "").strip():
                st.warning("Description is required.")
            elif current_user_id_bl is None:
                st.error("You must be signed in to log a blocker.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO blockers
                            (workstream_id, description, date_raised, status, created_by)
                        VALUES (%s, %s, %s, 'open', %s)
                        """,
                        (
                            workstream_id,
                            new_bl_description.strip(),
                            new_bl_date,
                            current_user_id_bl,
                        ),
                    )
                    calculate_rag(workstream_id)
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))

with tab_updates:
    POST_TYPE_CONFIG = {
        "status_update": {"label": "Status Update", "colour": "#2E86C1", "owner_only": True},
        "decision_made": {"label": "Decision Made", "colour": "#8E44AD", "owner_only": False},
        "risk_raised": {"label": "Risk Raised", "colour": "#E74C3C", "owner_only": False},
        "milestone_reached": {
            "label": "Milestone Reached",
            "colour": "#27AE60",
            "owner_only": False,
        },
        "general_announcement": {
            "label": "General Announcement",
            "colour": "#F39C12",
            "owner_only": False,
        },
    }

    def relative_time(dt):
        dt = pd.to_datetime(dt, errors="coerce")
        if pd.isna(dt):
            return "unknown"

        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        else:
            dt = dt.tz_convert("UTC")

        delta = datetime.now(timezone.utc) - dt.to_pydatetime()
        if delta.days >= 1:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours}h ago"
        return f"{delta.seconds // 60}m ago"

    try:
        run_query(
            """
            UPDATE updates
            SET is_locked = TRUE
            WHERE workstream_id = %s AND is_locked = FALSE
              AND created_at < NOW() - INTERVAL '15 minutes'
            """,
            (workstream_id,),
        )
        query_df.clear()
    except Exception as error:
        st.error(str(error))

    current_user_id = get_current_user_id()
    can_post = user_role in ("owner", "contributor")

    if can_post:
        st.markdown("### New Update")

        if user_role == "owner":
            available_post_types = list(POST_TYPE_CONFIG.keys())
        else:
            available_post_types = [
                post_type for post_type in POST_TYPE_CONFIG.keys() if post_type != "status_update"
            ]

        selected_post_type = st.selectbox(
            "Post type",
            options=available_post_types,
            format_func=lambda key: POST_TYPE_CONFIG[key]["label"],
            key="updates_post_type",
        )
        update_title = st.text_input("Title", key="updates_title")
        update_body = st.text_area("Body", height=150, key="updates_body")

        if st.button("Post Update", key="post_update_button"):
            if not (update_title or "").strip():
                st.warning("Title is required.")
            elif not (update_body or "").strip():
                st.warning("Body is required.")
            elif current_user_id is None:
                st.error("You must be signed in to post updates.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO updates (workstream_id, post_type, title, body, author_id, is_locked)
                        VALUES (%s, %s, %s, %s, %s, FALSE)
                        """,
                        (
                            workstream_id,
                            selected_post_type,
                            update_title.strip(),
                            update_body.strip(),
                            current_user_id,
                        ),
                    )
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))

        st.divider()

    posts_df = query_df(
        """
        SELECT p.id, p.post_type, p.title, p.body, p.created_at,
               p.edited_at, p.is_locked, p.author_id, u.display_name as author_name
        FROM updates p
        JOIN users u ON u.id = p.author_id
        WHERE p.workstream_id = %s
        ORDER BY p.created_at DESC
        """,
        (workstream_id,),
    )

    if posts_df.empty:
        st.info("No updates yet.")
    else:
        for _, post in posts_df.iterrows():
            post_id = str(post["id"])
            post_type = str(post.get("post_type") or "")
            cfg = POST_TYPE_CONFIG.get(
                post_type,
                {"label": post_type.replace("_", " ").title() or "Update", "colour": "#888888"},
            )
            post_title = post.get("title") or "(Untitled)"
            post_body = post.get("body") or ""
            author_name = post.get("author_name") or "Unknown"
            created_at = post.get("created_at")
            edited_at = post.get("edited_at")
            is_locked = bool(post.get("is_locked"))
            author_id = str(post.get("author_id") or "")

            timestamp_text = relative_time(created_at)
            if pd.notna(pd.to_datetime(edited_at, errors="coerce")):
                timestamp_text = f"{timestamp_text} <span style='color:#9AA0A6;'>(edited)</span>"

            st.markdown(
                f"""
                <div style="margin-bottom:0.35rem;">
                    <span style="background:{cfg['colour']}; color:#FFFFFF; padding:0.2rem 0.6rem; border-radius:999px; font-weight:600; font-size:0.78rem;">
                        {cfg['label']}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"**{post_title}**")
            st.markdown(
                f"{author_name} · {timestamp_text}",
                unsafe_allow_html=True,
            )
            st.write(post_body)

            can_edit_post = (not is_locked) and (author_id == str(current_user_id))
            edit_state_key = f"editing_update_{post_id}"
            if can_edit_post:
                if st.button("Edit", key=f"edit_update_btn_{post_id}"):
                    st.session_state[edit_state_key] = True

                if st.session_state.get(edit_state_key, False):
                    edited_body = st.text_area(
                        "Edit update body",
                        value=post_body,
                        key=f"edit_update_body_{post_id}",
                        height=140,
                    )
                    if st.button("Save", key=f"save_update_btn_{post_id}"):
                        if not (edited_body or "").strip():
                            st.warning("Body is required.")
                        else:
                            try:
                                run_query(
                                    """
                                    UPDATE updates
                                    SET body = %s, edited_at = NOW()
                                    WHERE id = %s
                                    """,
                                    (edited_body.strip(), post_id),
                                )
                                st.session_state[edit_state_key] = False
                                query_df.clear()
                                st.rerun()
                            except Exception as error:
                                st.error(str(error))

            st.divider()

with tab_team:
    members_df = query_df(
        """
        SELECT wm.id, wm.user_id, wm.role, wm.joined_at, wm.is_former_member,
               u.display_name, u.email
        FROM workstream_members wm
        JOIN users u ON u.id = wm.user_id
        WHERE wm.workstream_id = %s
        ORDER BY
          CASE wm.role WHEN 'owner' THEN 0 WHEN 'contributor' THEN 1 ELSE 2 END,
          wm.joined_at ASC
        """,
        (workstream_id,),
    )

    if members_df.empty:
        st.info("No members found for this workstream.")
    else:
        active_mask = ~members_df["is_former_member"].fillna(False).astype(bool)
        active_members = members_df[active_mask]
        former_members = members_df[~active_mask]

        owner_count = int((active_members["role"] == "owner").sum()) if not active_members.empty else 0
        contributor_count = (
            int((active_members["role"] == "contributor").sum()) if not active_members.empty else 0
        )
        viewer_count = int((active_members["role"] == "viewer").sum()) if not active_members.empty else 0
        st.markdown(
            f"**{owner_count} Owner · {contributor_count} Contributors · {viewer_count} Viewers**"
        )

        st.markdown("### Active Members")
        current_user_id = str(get_current_user_id() or "")
        role_avatar_colours = {"owner": "#4DB6AC", "contributor": "#7B68EE", "viewer": "#888"}
        role_labels = {"owner": "Owner", "contributor": "Contributor", "viewer": "Viewer"}

        if active_members.empty:
            st.caption("No active members.")
        else:
            for _, member in active_members.iterrows():
                member_row_id = str(member["id"])
                member_user_id = str(member.get("user_id") or "")
                member_role = str(member.get("role") or "viewer")
                member_name = str(member.get("display_name") or "Unknown")
                member_email = str(member.get("email") or "")
                joined_ts = pd.to_datetime(member.get("joined_at"), errors="coerce")
                joined_display = joined_ts.strftime("%Y-%m-%d") if pd.notna(joined_ts) else "Unknown"

                initial = member_name.strip()[0].upper() if member_name.strip() else "?"
                avatar_colour = role_avatar_colours.get(member_role, "#888")
                role_label = role_labels.get(member_role, member_role.title())

                col_avatar, col_identity, col_role, col_joined, col_actions = st.columns(
                    [0.8, 3.0, 1.6, 1.4, 2.2]
                )
                with col_avatar:
                    st.markdown(
                        f"""
                        <div style="width:34px; height:34px; border-radius:50%; background:{avatar_colour}; color:#FFFFFF; display:flex; align-items:center; justify-content:center; font-weight:700;">
                            {initial}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_identity:
                    st.markdown(f"**{member_name}**")
                    st.caption(member_email)
                with col_role:
                    st.markdown(
                        f"""
                        <span style="background:#1F2937; color:#E5E7EB; padding:0.2rem 0.6rem; border-radius:999px; font-size:0.78rem; font-weight:600;">
                            {role_label}
                        </span>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_joined:
                    st.caption("Joined")
                    st.write(joined_display)

                with col_actions:
                    if user_role == "owner" and member_user_id != current_user_id:
                        if member_role != "owner":
                            new_role = st.selectbox(
                                "Role",
                                options=["contributor", "viewer"],
                                index=0 if member_role == "contributor" else 1,
                                key=f"team_role_change_{member_row_id}",
                                label_visibility="collapsed",
                            )
                            if new_role != member_role:
                                try:
                                    run_query(
                                        "UPDATE workstream_members SET role = %s WHERE id = %s",
                                        (new_role, member_row_id),
                                    )
                                    query_df.clear()
                                    st.rerun()
                                except Exception as error:
                                    st.error(str(error))
                        else:
                            st.caption("Owner role locked")

                        remove_flag_key = f"team_remove_confirm_{member_row_id}"
                        if st.button("Remove", key=f"team_remove_btn_{member_row_id}"):
                            st.session_state[remove_flag_key] = True

                        if st.session_state.get(remove_flag_key, False):
                            st.warning(f"Remove {member_name} from this workstream?")
                            col_confirm, col_cancel = st.columns(2)
                            with col_confirm:
                                if st.button("Confirm", key=f"team_remove_confirm_btn_{member_row_id}"):
                                    try:
                                        run_query(
                                            """
                                            UPDATE workstream_members
                                            SET is_former_member = TRUE
                                            WHERE id = %s
                                            """,
                                            (member_row_id,),
                                        )
                                        run_query(
                                            """
                                            UPDATE comments
                                            SET is_former_member = TRUE
                                            WHERE author_id = %s
                                            """,
                                            (member_user_id,),
                                        )
                                        st.session_state.pop(remove_flag_key, None)
                                        query_df.clear()
                                        st.rerun()
                                    except Exception as error:
                                        st.error(str(error))
                            with col_cancel:
                                if st.button("Cancel", key=f"team_remove_cancel_btn_{member_row_id}"):
                                    st.session_state.pop(remove_flag_key, None)
                                    st.rerun()

                st.divider()

        with st.expander(f"Former Members ({len(former_members)})", expanded=False):
            if former_members.empty:
                st.caption("No former members.")
            else:
                for _, member in former_members.iterrows():
                    former_role = str(member.get("role") or "viewer")
                    former_role_label = role_labels.get(former_role, former_role.title())
                    former_name = str(member.get("display_name") or "Unknown")
                    former_email = str(member.get("email") or "")
                    joined_ts = pd.to_datetime(member.get("joined_at"), errors="coerce")
                    joined_display = joined_ts.strftime("%Y-%m-%d") if pd.notna(joined_ts) else "Unknown"

                    left_display = "N/A"
                    if "updated_at" in former_members.columns:
                        left_ts = pd.to_datetime(member.get("updated_at"), errors="coerce")
                        if pd.notna(left_ts):
                            left_display = left_ts.strftime("%Y-%m-%d")

                    st.markdown(f"**{former_name}**")
                    st.caption(
                        f"{former_email} · {former_role_label} · Joined: {joined_display} · Left: {left_display}"
                    )
                    st.divider()

    if user_role == "owner":
        st.markdown("### Invite Link")
        current_url = get_active_invite_url(workstream_id)
        current_user_id = get_current_user_id()

        if current_url:
            st.code(current_url)
            st.caption(
                "Anyone with this link can join as Viewer. Promote them to Contributor from this tab."
            )
            if st.button("Generate New Link", key="team_generate_new_invite"):
                try:
                    generate_invite_link(workstream_id, current_user_id)
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))
        else:
            st.info("No active invite link.")
            if st.button("Generate Invite Link", key="team_generate_invite"):
                try:
                    generate_invite_link(workstream_id, current_user_id)
                    query_df.clear()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))
    else:
        st.info("Only the workstream Owner can manage invite links.")
