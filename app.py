"""
CareerCompass — AI Career Advisor & Learning Progression Platform.
Main Application Controller & Router.
"""

import streamlit as st
from database.db import init_db
from ui.theme import apply_theme
from ui.views import (
    home_view,
    auth_view,
    profile_view,
    roles_view,
    directory_view,
    role_detail_view,
    compare_view,
    roadmap_view,
    roadmaps_view,
    tracker_view,
    chat_view,
)

# ── 1. Page Configuration & Theme ─────────────────────────────────────────────
st.set_page_config(
    page_title="CareerCompass 🧭 — AI Career Engine",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_theme()

# ── 2. Database Initialization ────────────────────────────────────────────────
init_db()

# ── 3. Session State Management ───────────────────────────────────────────────
# Sign-in is intentionally scoped to the current browser session only:
# closing the tab / restarting the server requires signing in again.
if "user" not in st.session_state:
    st.session_state.user = None

if "page" not in st.session_state:
    st.session_state.page = "home"

if "profile" not in st.session_state:
    user = st.session_state.get("user")
    st.session_state.profile = user.get("profile", {}) if user else {}

if "matched_roles" not in st.session_state:
    st.session_state.matched_roles = []

if "selected_role" not in st.session_state:
    st.session_state.selected_role = None

if "roadmap" not in st.session_state:
    st.session_state.roadmap = None

if "compare_roles" not in st.session_state:
    st.session_state.compare_roles = []

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


# ── 4. View Router ────────────────────────────────────────────────────────────
ROUTER = {
    "home": home_view.render,
    "auth": auth_view.render,
    "profile": profile_view.render,
    "roles": roles_view.render,
    "directory": directory_view.render,
    "role_detail": role_detail_view.render,
    "compare": compare_view.render,
    "roadmap": roadmap_view.render,
    "roadmaps": roadmaps_view.render,
    "tracker": tracker_view.render,
    "chat": chat_view.render,
}

current_page = st.session_state.get("page", "home")
render_func = ROUTER.get(current_page, home_view.render)
render_func()
