"""AI-Generated Skill Roadmap View (Step 4)."""
import streamlit as st
from ui.components import render_navbar
from services import ai_service, auth_service


def _roadmap_to_markdown(profile: dict, role: dict, roadmap: dict) -> str:
    """Renders a roadmap as a portable Markdown document."""
    lines = [
        f"# {role['title']} — Personalized Roadmap",
        "",
        f"**Candidate:** {profile.get('name', 'Candidate')}  ",
        f"**Target role:** {role['title']} ({role.get('category', '')})  ",
        "**Generated with CareerCompass**",
        "",
        "## Summary",
        "",
        roadmap.get("summary", ""),
        "",
    ]

    def _section(title, items, with_time=True):
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for it in items:
            lines.append(f"### {it.get('skill', '')}")
            if with_time and it.get("time_estimate"):
                lines.append(f"- **Estimated time:** {it['time_estimate']}")
            if it.get("why"):
                lines.append(f"- **Why it matters:** {it['why']}")
            if it.get("resource"):
                lines.append(f"- **Free resource:** {it['resource']}")
            lines.append("")

    _section("Phase 1 — Immediate Focus", roadmap.get("immediate_focus", []))
    _section("Phase 2 — Competitive Edge", roadmap.get("next_level", []))
    _section("Phase 3 — High-Growth Specialization", roadmap.get("good_to_explore", []), with_time=False)

    projects = roadmap.get("projects", [])
    if projects:
        lines.append("## Portfolio Projects")
        lines.append("")
        for idx, p in enumerate(projects, 1):
            lines.append(f"### Project {idx}: {p.get('title', '')}")
            if p.get("difficulty"):
                lines.append(f"- **Difficulty:** {p['difficulty']}")
            if p.get("description"):
                lines.append(f"- **Description:** {p['description']}")
            skills = p.get("skills_demonstrated", [])
            if skills:
                lines.append(f"- **Skills demonstrated:** {', '.join(skills)}")
            lines.append("")

    if roadmap.get("motivational_message"):
        lines += ["---", "", f"> {roadmap['motivational_message']}", ""]

    return "\n".join(lines)


def render():
    render_navbar()

    profile = st.session_state.get("profile", {})
    role = st.session_state.get("selected_role")

    if not role:
        st.session_state.page = "directory"
        st.rerun()

    st.markdown(f"## 🗺️ Step 4 — Personalized Skill Roadmap")
    st.markdown(f"**Target Role:** {role['icon']} **{role['title']}** &nbsp;|&nbsp; **Candidate:** {profile.get('name', 'You')}")
    st.markdown("---")

    if st.session_state.get("roadmap") is None:
        with st.spinner("Synthesizing personalized roadmap & portfolio milestones with Gemini..."):
            try:
                roadmap = ai_service.generate_roadmap(profile, role)
            except ai_service.AIConfigurationError as e:
                st.error(f"⚙️ **AI is not configured.** {e}")
                if st.button("← Back to Role Detail", use_container_width=True):
                    st.session_state.page = "role_detail"
                    st.rerun()
                st.stop()
            except Exception as e:
                st.error(f"Could not generate your roadmap right now: {e}")
                if st.button("🔄 Try Again", type="primary", use_container_width=True):
                    st.session_state.roadmap = None
                    st.rerun()
                st.stop()

            st.session_state.roadmap = roadmap
            user = st.session_state.get("user")
            if user:
                auth_service.save_roadmap(user["id"], role["id"], role["title"], roadmap)

    roadmap = st.session_state["roadmap"]

    # Strategic Summary
    st.info(f"💡 **Advisory Assessment:** {roadmap.get('summary', '')}")

    dl1, dl2 = st.columns([3.0, 1.3])
    with dl2:
        st.download_button(
            "⬇️ Download roadmap (.md)",
            data=_roadmap_to_markdown(profile, role, roadmap),
            file_name=f"careercompass_{role['id']}_roadmap.md",
            mime="text/markdown",
            use_container_width=True,
        )
    st.markdown("---")

    # Phase 1
    st.markdown("### 🔥 Phase 1 — Immediate Focus (Hireability Acceleration)")
    st.caption("Highest-leverage foundational gaps to become interview-ready as quickly as possible.")
    for item in roadmap.get("immediate_focus", []):
        with st.expander(f"✅ **{item['skill']}** &nbsp;•&nbsp; *Estimated: {item.get('time_estimate', '1-2 weeks')}*", expanded=True):
            st.markdown(f"**Why this matters:** {item['why']}")
            st.markdown(f"**📚 Curated Free Resource:** `{item['resource']}`")

    st.markdown("---")

    # Phase 2
    st.markdown("### 📈 Phase 2 — Competitive Edge (Deepening Specialization)")
    st.caption("Capabilities that elevate your profile above average entry-level candidates.")
    for item in roadmap.get("next_level", []):
        with st.expander(f"⭐ **{item['skill']}** &nbsp;•&nbsp; *Estimated: {item.get('time_estimate', '2-3 weeks')}*"):
            st.markdown(f"**Why this matters:** {item['why']}")
            st.markdown(f"**📚 Curated Free Resource:** `{item['resource']}`")

    st.markdown("---")

    # Phase 3
    st.markdown("### 💡 Phase 3 — High-Growth Specialization")
    for item in roadmap.get("good_to_explore", []):
        with st.expander(f"💡 **{item['skill']}**"):
            st.markdown(f"**Why this matters:** {item['why']}")
            st.markdown(f"**📚 Curated Free Resource:** `{item['resource']}`")

    st.markdown("---")

    # Portfolio Projects
    st.markdown("### 🛠️ Portfolio Projects to Build")
    st.caption("Hands-on repositories that validate your competence to hiring managers.")
    for idx, p in enumerate(roadmap.get("projects", []), 1):
        with st.container(border=True):
            diff_icon = {"Beginner": "🟢", "Intermediate": "🟡", "Advanced": "🔴"}.get(p.get("difficulty"), "⚪")
            st.markdown(f"**Project {idx}: {p['title']}** {diff_icon} *({p.get('difficulty', '')})*")
            st.markdown(f"<p style='color: #475569; font-size: 0.9rem;'>{p['description']}</p>", unsafe_allow_html=True)
            skills = p.get("skills_demonstrated", [])
            if skills:
                st.markdown("**Validated Skills:** " + " · ".join([f"`{s}`" for s in skills]))

    st.markdown("---")

    # Next Step CTAs: Study Tracker & Copilot
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        with st.container(border=True):
            st.markdown("#### 📅 **Ready to Study? Plan Your Hours**")
            st.markdown("<p style='color:#64748B; font-size: 0.88rem;'>Configure your weekday and weekend availability to track every topic and subtopic with completion markers.</p>", unsafe_allow_html=True)
            if st.button("Open Custom Study Tracker →", type="primary", use_container_width=True):
                st.session_state.page = "tracker"
                st.rerun()

    with col_cta2:
        with st.container(border=True):
            st.markdown("#### 💬 **Have Questions on the Roadmap?**")
            st.markdown("<p style='color:#64748B; font-size: 0.88rem;'>Chat with your Roadmap Copilot to break down daily tasks, ask interview tips, or get project guidance.</p>", unsafe_allow_html=True)
            if st.button("Launch Roadmap Copilot", use_container_width=True):
                st.session_state.chat_messages = []
                st.session_state.page = "chat"
                st.rerun()

    st.markdown("---")
    cb1, cb2 = st.columns([1.5, 4.0])
    with cb1:
        if st.button("← Back to Role Detail", use_container_width=True):
            st.session_state.page = "role_detail"
            st.rerun()
    with cb2:
        if st.button("🔄 Regenerate Roadmap", use_container_width=True):
            st.session_state.roadmap = None
            st.rerun()
