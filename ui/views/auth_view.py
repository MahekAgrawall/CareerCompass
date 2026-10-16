"""Authentication view (Login / Signup)."""
import streamlit as st
from ui.components import render_navbar
from services import auth_service, career_service


def render():
    render_navbar()

    col1, col2, col3 = st.columns([1, 1.6, 1])
    with col2:
        tab_login, tab_signup = st.tabs(["🔑 Sign In", "✨ Create Account"])

        with tab_login:
            with st.container(border=True):
                st.markdown("### Welcome Back")
                st.caption("Access your saved profile, custom roadmaps, and study schedules.")

                with st.form("form_login"):
                    email = st.text_input("Email", placeholder="name@domain.com")
                    password = st.text_input("Password", type="password", placeholder="••••••••")
                    submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)

                if submit:
                    success, res = auth_service.authenticate_user(email, password)
                    if success:
                        st.session_state.user = res
                        if res.get("profile"):
                            st.session_state.profile = res["profile"]
                            st.session_state.scored_roles = career_service.match_roles_smart(res["profile"])
                            st.session_state.matched_roles = [item["role"] for item in st.session_state.scored_roles]
                        st.success("Successfully authenticated!")
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error(res)

        with tab_signup:
            with st.container(border=True):
                st.markdown("### Create Your Account")
                st.caption("Keep your career trajectories, roadmaps, and tracker checklists saved.")

                with st.form("form_signup"):
                    name = st.text_input("Full Name", placeholder="e.g. Mahek Agrawal")
                    email = st.text_input("Email", placeholder="name@domain.com")
                    password = st.text_input("Password", type="password", placeholder="At least 8 characters")
                    submit = st.form_submit_button("Register", type="primary", use_container_width=True)

                if submit:
                    success, msg = auth_service.signup_user(name, email, password)
                    if success:
                        _, user = auth_service.authenticate_user(email, password)
                        st.session_state.user = user
                        st.success("Account created! Let's build your profile.")
                        st.session_state.page = "profile"
                        st.rerun()
                    else:
                        st.error(msg)
