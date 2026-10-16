"""My Roadmaps — a history of AI-generated roadmaps for the signed-in user."""
import streamlit as st
from ui.components import render_navbar
from services import auth_service, career_service


def render():
    render_navbar()

    user = st.session_state.get("user")

    st.markdown("## 🗺️ My Saved Roadmaps")
    st.caption("Every roadmap you generate is saved here so you can revisit a plan or pick up where you left off.")
    st.markdown("---")

    if not user:
        st.info("Sign in to build a personal library of your generated roadmaps across roles.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔑 Sign In", type="primary", use_container_width=True):
                st.session_state.page = "auth"
                st.rerun()
        with c2:
            if st.button("Explore Roles", use_container_width=True):
                st.session_state.page = "directory"
                st.rerun()
        return

    saved = auth_service.get_saved_roadmaps(user["id"])

    if not saved:
        st.info("You haven't generated any roadmaps yet. Pick a role and generate your first personalized plan.")
        if st.button("Browse Roles Directory", type="primary", use_container_width=True):
            st.session_state.page = "directory"
            st.rerun()
        return

    st.markdown(f"**{len(saved)} saved roadmap(s)** — most recent first.")
    st.markdown("")

    for item in saved:
        role = career_service.get_role_by_id(item["role_id"])
        roadmap = item.get("roadmap", {})

        with st.container(border=True):
            col_a, col_b = st.columns([3.0, 1.7])
            with col_a:
                heading = f"{role['icon']} {item['role_title']}" if role else f"💼 {item['role_title']}"
                st.markdown(f"#### {heading}")
                created = (item.get("created_at") or "")[:10]
                priority = len(roadmap.get("immediate_focus", []))
                projects = len(roadmap.get("projects", []))
                st.caption(f"Generated {created} &nbsp;•&nbsp; {priority} priority skills &nbsp;•&nbsp; {projects} projects")
                if roadmap.get("summary"):
                    st.markdown(
                        f"<p style='color:#475569; font-size:0.88rem; margin:0.3rem 0 0 0;'>{roadmap['summary']}</p>",
                        unsafe_allow_html=True
                    )
            with col_b:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Open Plan", key=f"rm_open_{item['id']}", type="primary", use_container_width=True):
                        if role:
                            st.session_state.selected_role = role
                            st.session_state.roadmap = roadmap
                            st.session_state.page = "roadmap"
                            st.rerun()
                        else:
                            st.warning("This role is no longer available in the catalog.")
                with b2:
                    if st.button("Delete", key=f"rm_del_{item['id']}", use_container_width=True):
                        auth_service.delete_saved_roadmap(item["id"], user["id"])
                        st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back to Home", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    with c2:
        if st.button("Explore More Roles →", use_container_width=True):
            st.session_state.page = "directory"
            st.rerun()
