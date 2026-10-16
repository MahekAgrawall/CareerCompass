"""
CareerCompass — AI Career Advisor & Learning Progression Platform.
Main Application Controller & Router.
"""

import streamlit as st
from database.db import init_db
from services import career_service
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

VALID_PAGES = set(ROUTER.keys())
ROLE_SCOPED_PAGES = {"role_detail", "roadmap", "tracker", "chat"}


# ── 5. URL ↔ session-state route synchronization ──────────────────────────────
# Keeps the current page in the URL so a browser refresh (or a shared link)
# returns the user to the same view, and supports deep links like:
#   ?page=role_detail&id=backend_dev
def _sync_route():
    qp_page = st.query_params.get("page")
    if qp_page in VALID_PAGES and st.session_state.get("_route_seen") != qp_page:
        # The URL changed (link, back/forward button) — treat it as intent.
        st.session_state.page = qp_page
    st.session_state["_route_seen"] = st.session_state.page

    qp_role_id = st.query_params.get("id")
    if qp_role_id and st.session_state.page in ROLE_SCOPED_PAGES:
        current = st.session_state.get("selected_role")
        if not current or current.get("id") != qp_role_id:
            role = career_service.get_role_by_id(qp_role_id)
            if role:
                st.session_state.selected_role = role

    # Reflect app state back into the URL (guard prevents rerun loops).
    if st.query_params.get("page") != st.session_state.page:
        st.query_params["page"] = st.session_state.page
    current_role = st.session_state.get("selected_role")
    if current_role and st.session_state.page in ROLE_SCOPED_PAGES:
        if st.query_params.get("id") != current_role["id"]:
            st.query_params["id"] = current_role["id"]


_sync_route()

current_page = st.session_state.get("page", "home")
render_func = ROUTER.get(current_page, home_view.render)
render_func()
