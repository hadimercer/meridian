"""
pages/create_workstream.py
New workstream creation — two-step form: basics → 9-question scoring wizard.
"""

import streamlit as st
from datetime import date

from pipeline.auth import require_auth, get_current_user, get_current_user_id, logout
from pipeline.db import get_pg_connection, query_df
from pipeline.scoring import calculate_rag

st.set_page_config(layout="wide")


require_auth()

# ─── Sidebar navigation ───────────────────────────────────────────────────────

with st.sidebar:
    st.page_link("pages/home.py", label="Home")
    st.page_link("pages/dashboard.py", label="Portfolio")
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
    if st.button("Sign Out", key="sidebar_signout_create"):
        logout()

# ─── Wizard question definitions ──────────────────────────────────────────────

_WIZARD_QUESTIONS = [
    (
        "q1_work_type",
        "1. What type of work is this workstream?",
        [
            ("delivery", "Delivery"),
            ("analysis", "Analysis"),
            ("process_improvement", "Process Improvement"),
            ("reporting", "Reporting"),
            ("strategy", "Strategy"),
            ("other", "Other"),
        ],
    ),
    (
        "q2_deadline_nature",
        "2. What is the nature of the deadline?",
        [
            ("hard_contractual", "Hard / Contractual"),
            ("business_driven", "Business-Driven"),
            ("self_imposed", "Self-Imposed"),
            ("ongoing", "Ongoing"),
        ],
    ),
    (
        "q3_deliverable_type",
        "3. What is the primary deliverable?",
        [
            ("document_report", "Document / Report"),
            ("decision_approval", "Decision / Approval"),
            ("built_solution", "Built Solution"),
            ("process_change", "Process Change"),
            ("recommendation", "Recommendation"),
        ],
    ),
    (
        "q4_budget_exposure",
        "4. What is the budget exposure?",
        [
            ("client_billable", "Client-Billable"),
            ("approved_internal", "Approved Internal Budget"),
            ("informal_none", "Informal / No Budget"),
        ],
    ),
    (
        "q5_dependency_level",
        "5. What is the dependency level?",
        [
            ("self_contained", "Self-Contained"),
            ("depends_1_2", "Depends on 1-2 Others"),
            ("depends_multiple", "Depends on Multiple Teams"),
            ("blocked_external", "Blocked by External Party"),
        ],
    ),
    (
        "q6_risk_level",
        "6. What is the stakeholder sensitivity / risk level?",
        [
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
    ),
    (
        "q7_phase",
        "7. What phase is this workstream currently in?",
        [
            ("discovery", "Discovery"),
            ("planning", "Planning"),
            ("in_flight", "In Flight"),
            ("review_closing", "Review & Closing"),
        ],
    ),
    (
        "q8_update_frequency",
        "8. How frequently will you update this workstream?",
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("biweekly", "Bi-Weekly"),
            ("monthly", "Monthly"),
        ],
    ),
    (
        "q9_audience",
        "9. Who is the primary audience for this workstream?",
        [
            ("just_me", "Just Me"),
            ("my_team", "My Team"),
            ("senior_leadership", "Senior Leadership"),
            ("external_client", "External Client"),
        ],
    ),
]

# ─── Step routing ─────────────────────────────────────────────────────────────

if "new_ws_data" not in st.session_state:

    # ── Step 1 — Basics ───────────────────────────────────────────────────────

    st.markdown("# New Workstream")
    st.markdown("### Step 1 of 2 — Basics")

    with st.form("new_ws_basics_form"):
        ws_name = st.text_input(
            "Name *",
            max_chars=120,
            placeholder="e.g. Q2 Client Delivery",
        )
        ws_description = st.text_area("Description (optional)", height=100)

        col_start, col_end = st.columns(2)
        with col_start:
            ws_start = st.date_input("Start date", value=date.today())
        with col_end:
            ws_end = st.date_input("End date", value=date.today())

        ws_budget = st.number_input(
            "Planned Budget (leave blank if informal)",
            min_value=0.0,
            value=0.0,
            step=100.0,
            format="%.2f",
            help="Set to 0 if this workstream has no formal budget.",
        )

        submitted_basics = st.form_submit_button(
            "Continue to Scoring Wizard →", use_container_width=True
        )

    if submitted_basics:
        errors = []
        if not (ws_name or "").strip():
            errors.append("Name is required.")
        if ws_end <= ws_start:
            errors.append("End date must be after start date.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            st.session_state["new_ws_data"] = {
                "name": ws_name.strip(),
                "description": (ws_description or "").strip() or None,
                "start_date": ws_start,
                "end_date": ws_end,
                "planned_budget": float(ws_budget) if ws_budget > 0 else None,
            }
            st.rerun()

else:

    # ── Step 2 — Wizard ───────────────────────────────────────────────────────

    ws_data = st.session_state["new_ws_data"]

    st.markdown("# New Workstream")
    st.markdown("### Step 2 of 2 — Scoring Wizard")
    st.caption(f"Workstream: **{ws_data['name']}**")
    st.markdown(
        "These 9 questions tune the scoring thresholds to the nature of your work. "
        "All are required."
    )

    if st.button("← Back to Basics"):
        del st.session_state["new_ws_data"]
        st.rerun()

    with st.form("new_ws_wizard_form"):
        wizard_answers = {}
        for field_key, question_label, options in _WIZARD_QUESTIONS:
            labels = [label for _, label in options]
            selected_label = st.radio(
                question_label,
                options=labels,
                key=f"wiz_{field_key}",
            )
            code_by_label = {label: code for code, label in options}
            wizard_answers[field_key] = code_by_label[selected_label]
            st.markdown("---")

        create_submitted = st.form_submit_button(
            "Create Workstream", use_container_width=True
        )

    if create_submitted:
        current_user_id = get_current_user_id()
        if current_user_id is None:
            st.error("You must be signed in to create a workstream.")
        else:
            try:
                conn = get_pg_connection()
                try:
                    with conn.cursor() as cur:
                        # 1. Insert workstream, capture generated id
                        cur.execute(
                            """
                            INSERT INTO workstreams
                                (name, description, start_date, end_date,
                                 planned_budget, owner_id, phase)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            (
                                ws_data["name"],
                                ws_data["description"],
                                ws_data["start_date"],
                                ws_data["end_date"],
                                ws_data["planned_budget"],
                                current_user_id,
                                wizard_answers["q7_phase"],
                            ),
                        )
                        new_ws_id = str(cur.fetchone()[0])

                        # 2. Add creator as owner member
                        cur.execute(
                            """
                            INSERT INTO workstream_members (workstream_id, user_id, role)
                            VALUES (%s, %s, 'owner')
                            """,
                            (new_ws_id, current_user_id),
                        )

                        # 3. Insert wizard config
                        cur.execute(
                            """
                            INSERT INTO wizard_config (
                                workstream_id,
                                q1_work_type, q2_deadline_nature, q3_deliverable_type,
                                q4_budget_exposure, q5_dependency_level,
                                q6_risk_level, q7_phase,
                                q8_update_frequency, q9_audience,
                                configured_by
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                new_ws_id,
                                wizard_answers["q1_work_type"],
                                wizard_answers["q2_deadline_nature"],
                                wizard_answers["q3_deliverable_type"],
                                wizard_answers["q4_budget_exposure"],
                                wizard_answers["q5_dependency_level"],
                                wizard_answers["q6_risk_level"],
                                wizard_answers["q7_phase"],
                                wizard_answers["q8_update_frequency"],
                                wizard_answers["q9_audience"],
                                current_user_id,
                            ),
                        )

                        # 4. Seed a rag_scores row (calculate_rag fills values)
                        cur.execute(
                            "INSERT INTO rag_scores (workstream_id) VALUES (%s)",
                            (new_ws_id,),
                        )

                        conn.commit()
                finally:
                    conn.close()

                # 5. Run initial scoring pass
                calculate_rag(new_ws_id)

                # 6–8. Clear cache, confirm, navigate
                query_df.clear()
                del st.session_state["new_ws_data"]
                st.session_state["open_workstream_id"] = new_ws_id
                st.switch_page("pages/workstream.py")

            except Exception as error:
                st.error(f"Failed to create workstream: {error}")
