"""
Study Hours Planner & Detailed Topic/Subtopic Tracker View.
Allows candidates to plan weekday/weekend hours, track languages, and check off syllabus topics with real-time projections.
"""

import streamlit as st
from ui.components import render_navbar
from services import career_service, tracker_service


def render():
    render_navbar()

    user = st.session_state.get("user")
    user_id = user["id"] if user else 0

    all_roles = career_service.get_all_roles()
    if not all_roles:
        st.warning("No roles available in the database.")
        return

    # Determine current role
    selected_role = st.session_state.get("selected_role")
    role_titles = [r["title"] for r in all_roles]

    default_idx = 0
    if selected_role:
        for idx, r in enumerate(all_roles):
            if r["id"] == selected_role["id"]:
                default_idx = idx
                break

    st.markdown("## 📅 Study Hours Planner & Topic Tracker")
    st.caption("Customize your daily study throughput across weekdays and weekends, and check off syllabus topics as you master them.")
    st.markdown("---")

    # ── Role & Schedule Configuration ─────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### ⚙️ **1. Study Commitment & Target Stack**")

        c_role, c_weekdays, c_weekends = st.columns([2.0, 1.2, 1.2])

        with c_role:
            chosen_title = st.selectbox("Target Role for Study Tracker", role_titles, index=default_idx)
            current_role = next(r for r in all_roles if r["title"] == chosen_title)
            st.session_state.selected_role = current_role

        # Fetch current schedule from DB
        current_schedule = tracker_service.get_study_schedule(user_id, current_role["id"])

        with c_weekdays:
            weekday_hrs = st.number_input(
                "Weekday Study (hrs/day)",
                min_value=0.5,
                max_value=12.0,
                value=float(current_schedule.get("weekday_hours", 1.5)),
                step=0.5,
                help="Hours you can realistically dedicate each Monday through Friday"
            )

        with c_weekends:
            weekend_hrs = st.number_input(
                "Weekend Study (hrs/day)",
                min_value=0.5,
                max_value=16.0,
                value=float(current_schedule.get("weekend_hours", 4.0)),
                step=0.5,
                help="Hours dedicated on Saturday and Sunday"
            )

        # ── Role-Specific Dynamic Stack Selectors (3 Tailored Dropdowns) ──
        schema = tracker_service.get_role_stack_schema(current_role["id"])
        saved_choices = current_schedule.get("target_languages") or []

        st.markdown(f"##### 🎯 **Configure Your {current_role['title']} Specialization Stack:**")
        col_d1, col_d2, col_d3 = st.columns(3)

        # Dimension 1
        d1_opts = schema["dim1"]["options"]
        d1_default_idx = 0
        for idx, opt in enumerate(d1_opts):
            if opt in saved_choices:
                d1_default_idx = idx
                break
        with col_d1:
            choice_d1 = st.selectbox(schema["dim1"]["label"], d1_opts, index=d1_default_idx)

        # Dimension 2
        d2_opts = schema["dim2"]["options"]
        d2_default_idx = 0
        for idx, opt in enumerate(d2_opts):
            if opt in saved_choices:
                d2_default_idx = idx
                break
        with col_d2:
            choice_d2 = st.selectbox(schema["dim2"]["label"], d2_opts, index=d2_default_idx)

        # Dimension 3
        d3_opts = schema["dim3"]["options"]
        d3_default_idx = 0
        for idx, opt in enumerate(d3_opts):
            if opt in saved_choices:
                d3_default_idx = idx
                break
        with col_d3:
            choice_d3 = st.selectbox(schema["dim3"]["label"], d3_opts, index=d3_default_idx)

        current_selected_choices = [choice_d1, choice_d2, choice_d3]

        weekly_total = (weekday_hrs * 5.0) + (weekend_hrs * 2.0)
        st.markdown(
            f"⚡ **Weekly Study Pace:** `{weekly_total:.1f} hours/week` "
            f"*(5 weekdays × {weekday_hrs}h + 2 weekend days × {weekend_hrs}h)*"
        )

        # Auto-detect changes to choices or hours and sync syllabus immediately
        if set(current_selected_choices) != set(saved_choices):
            tracker_service.save_study_schedule(
                user_id,
                current_role["id"],
                weekday_hrs,
                weekend_hrs,
                current_selected_choices
            )
            tracker_service.sync_topics_for_role_stack(
                user_id, current_role["id"], current_selected_choices, force_refresh=True
            )
            st.rerun()

        if st.button("Save Schedule & Update Syllabus", type="primary"):
            tracker_service.save_study_schedule(
                user_id,
                current_role["id"],
                weekday_hrs,
                weekend_hrs,
                current_selected_choices
            )
            tracker_service.sync_topics_for_role_stack(
                user_id, current_role["id"], current_selected_choices, force_refresh=True
            )
            st.toast("Syllabus tailored for selected stack!")
            st.rerun()

    # Fetch topics tailored for current role and chosen stack
    topics = tracker_service.sync_topics_for_role_stack(
        user_id, current_role["id"], current_selected_choices, force_refresh=False
    )
    metrics = tracker_service.calculate_tracker_metrics(topics, weekly_total)

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # ── Progress Dashboard Header ──────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"#### 📊 **2. Progress Dashboard: {current_role['icon']} {current_role['title']}**")

        pct = metrics["percentage"]
        st.progress(pct / 100.0)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Completion", f"{pct}%", f"{metrics['completed_topics']}/{metrics['total_topics']} Topics")
        with m2:
            st.metric("Total Syllabus Time", f"{metrics['total_hours']:.0f} hrs")
        with m3:
            st.metric("Remaining Study", f"{metrics['remaining_hours']:.0f} hrs")
        with m4:
            st.metric("Projected Timeline", f"{metrics['weeks_remaining']} wks", "At current weekly pace")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # ── Detailed Topics & Subtopics Checklist ─────────────────────────────────
    st.markdown("#### 📝 **3. Detailed Topic & Subtopic Syllabus**")
    st.caption("Check off topics as you finish your study sessions. All progress is automatically stored.")

    # Group topics by Category
    categories = {}
    for t in topics:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t)

    for cat_name, cat_topics in categories.items():
        with st.container(border=True):
            cat_completed = sum(1 for t in cat_topics if t["is_completed"])
            st.markdown(f"### 📚 {cat_name} &nbsp;*(Completed: {cat_completed}/{len(cat_topics)})*")

            for t in cat_topics:
                t_col1, t_col2 = st.columns([3.5, 1.2])

                with t_col1:
                    is_checked = st.checkbox(
                        f"**{t['topic_name']}** ({t['estimated_hours']:.0f} hrs)",
                        value=t["is_completed"],
                        key=f"topic_chk_{t['id']}"
                    )
                    if is_checked != t["is_completed"]:
                        tracker_service.toggle_topic_status(t["id"], is_checked)
                        st.rerun()

                    # Render granular subtopics
                    for sub in t.get("subtopics", []):
                        st.markdown(f"<div class='subtopic-item'>{sub}</div>", unsafe_allow_html=True)

                with t_col2:
                    if t["is_completed"]:
                        st.markdown("<span class='badge' style='background:#DCFCE7; color:#166534;'>✓ Completed</span>", unsafe_allow_html=True)
                        if t.get("completed_at"):
                            st.caption(f"Done: {t['completed_at'][:10]}")
                    else:
                        st.markdown("<span class='badge' style='background:#F1F5F9; color:#475569;'>In Progress</span>", unsafe_allow_html=True)

                st.markdown("<hr style='margin: 0.6rem 0; border-color: #F1F5F9;'/>", unsafe_allow_html=True)

    st.markdown("---")
    cb1, cb2 = st.columns([1.5, 4.0])
    with cb1:
        if st.button("← Back to Roadmap", use_container_width=True):
            st.session_state.page = "roadmap"
            st.rerun()
    with cb2:
        if st.button("💬 Chat with Roadmap Copilot", use_container_width=True):
            st.session_state.page = "chat"
            st.rerun()
