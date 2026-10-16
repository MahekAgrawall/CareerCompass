"""
Reusable UI Components for CareerCompass.
Includes navigation bar, role cards, badges, and progress indicators.
"""

import streamlit as st
from typing import Dict, Any, List, Optional
from services import auth_service


def render_navbar():
    """Renders the top navigation header with unique SVG branding, direct routing, and scroll-to-top."""
    # Auto-reset scroll position to top on page load
    st.markdown("""
        <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
             onload="try{var m=window.parent.document.querySelector('section.main');if(m){m.scrollTo({top:0,left:0,behavior:'instant'});}}catch(e){}"
             style="display:none;" />
    """, unsafe_allow_html=True)

    col_brand, col_links, col_user = st.columns([2.1, 4.3, 1.6])

    with col_brand:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 3px;">
            <svg width="34" height="34" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" style="border-radius: 8px; box-shadow: 0 4px 10px -2px rgba(67, 56, 202, 0.35);">
                <rect width="36" height="36" rx="8" fill="url(#ccBrandGrad)" />
                <circle cx="18" cy="18" r="11" stroke="#FFFFFF" stroke-width="1.6" stroke-opacity="0.35" stroke-dasharray="2 2.5"/>
                <circle cx="18" cy="18" r="13.8" stroke="#FFFFFF" stroke-width="1.0" stroke-opacity="0.2"/>
                <!-- Compass North Needle (White) -->
                <path d="M18 6.5L21.2 16.5L18 15.2L14.8 16.5L18 6.5Z" fill="#FFFFFF"/>
                <!-- Compass South Needle (Cyan) -->
                <path d="M18 29.5L21.2 19.5L18 20.8L14.8 19.5L18 29.5Z" fill="#38BDF8"/>
                <!-- Compass East/West Needles -->
                <path d="M29.5 18L19.5 21.2L20.8 18L19.5 14.8L29.5 18Z" fill="#E0E7FF"/>
                <path d="M6.5 18L16.5 21.2L15.2 18L16.5 14.8L6.5 18Z" fill="#818CF8"/>
                <circle cx="18" cy="18" r="2.2" fill="#FFFFFF"/>
                <defs>
                    <linearGradient id="ccBrandGrad" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
                        <stop stop-color="#1E1B4B"/>
                        <stop offset="0.5" stop-color="#4338CA"/>
                        <stop offset="1" stop-color="#6366F1"/>
                    </linearGradient>
                </defs>
            </svg>
            <div style="display: flex; align-items: baseline; line-height: 1;">
                <span style="font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 1.35rem; letter-spacing: -0.035em; color: #0F172A;">
                    Career<span style="color: #4338CA;">Compass</span>
                </span>
                <span style="background: #EEF2FF; color: #4338CA; border: 1px solid #C7D2FE; font-size: 0.62rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; margin-left: 6px; letter-spacing: 0.04em;">
                    AI
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_links:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            if st.button("Home", use_container_width=True, key="btn_nav_home"):
                st.session_state.page = "home"
                st.rerun()
        with c2:
            if st.button("My Matches", use_container_width=True, key="btn_nav_matches"):
                st.session_state.page = "roles" if st.session_state.get("matched_roles") else "profile"
                st.rerun()
        with c3:
            if st.button("All Roles", use_container_width=True, key="btn_nav_dir"):
                st.session_state.page = "directory"
                st.rerun()
        with c4:
            if st.button("🗺️ Roadmaps", use_container_width=True, key="btn_nav_roadmaps"):
                st.session_state.page = "roadmaps"
                st.rerun()
        with c5:
            if st.button("📅 Tracker", use_container_width=True, key="btn_nav_tracker"):
                st.session_state.page = "tracker"
                st.rerun()
        with c6:
            count = len(st.session_state.get("compare_roles", []))
            lbl = f"Compare ({count})" if count > 0 else "Compare"
            if st.button(lbl, use_container_width=True, key="btn_nav_cmp"):
                st.session_state.page = "compare" if count > 0 else "directory"
                st.rerun()

    with col_user:
        user = st.session_state.get("user")
        if user:
            u_col1, u_col2 = st.columns([1.8, 1.2])
            with u_col1:
                st.markdown(f"**👤 {user['name'].split()[0]}**")
            with u_col2:
                if st.button("Logout", key="btn_nav_logout", use_container_width=True):
                    auth_service.clear_saved_session()
                    st.session_state.user = None
                    st.session_state.page = "home"
                    st.rerun()
        else:
            if st.button("🔑 Sign In", key="btn_nav_auth", use_container_width=True, type="primary"):
                st.session_state.page = "auth"
                st.rerun()

    st.markdown("<hr style='margin-top: 0.2rem; margin-bottom: 1.5rem; border-color: #E2E8F0;'/>", unsafe_allow_html=True)


def render_role_card(
    role: Dict[str, Any],
    match_pct: Optional[int] = None,
    key_prefix: str = "card"
):
    """Renders a clean, structured role card with market intelligence and action buttons."""
    with st.container(border=True):
        col_title, col_badge = st.columns([2.5, 1.5])
        with col_title:
            st.markdown(f"#### {role['icon']} {role['title']}")
            st.caption(f"{role['category']} • {role.get('niche_category', 'Engineering')}")
        with col_badge:
            if match_pct is not None:
                st.markdown(f"<span class='badge badge-match'>⭐ {match_pct}% Match</span>", unsafe_allow_html=True)
            elif role.get("is_niche"):
                st.markdown("<span class='badge badge-niche'>🎯 Niche Specialist</span>", unsafe_allow_html=True)

        # Market Badges
        st.markdown(
            f"""
            <div>
                <span class='badge badge-demand'>{role.get('market_demand', 'High')}</span>
                <span class='badge badge-comp'>{role.get('competition_level', 'Moderate')}</span>
                <span class='badge badge-future'>AI Future: {role.get('future_relevance', 'High').split('(')[0].strip()}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(f"<p style='color: #475569; font-size: 0.88rem; margin: 0.5rem 0;'>{role['description'][:125]}...</p>", unsafe_allow_html=True)

        sal = role["salary"]
        st.markdown(f"💰 **Fresher:** ₹{sal['fresher_0_1']['min']}–{sal['fresher_0_1']['max']} LPA &nbsp;|&nbsp; **1–3y:** ₹{sal['mid_1_3']['min']}–{sal['mid_1_3']['max']} LPA")

        b1, b2 = st.columns([1.5, 1.0])
        with b1:
            if st.button("View Specs & Roadmap", key=f"{key_prefix}_view_{role['id']}", use_container_width=True, type="primary"):
                st.session_state.selected_role = role
                st.session_state.page = "role_detail"
                st.rerun()
        with b2:
            compare_list = st.session_state.get("compare_roles", [])
            already = role["id"] in [r["id"] for r in compare_list]
            if already:
                st.button("✓ Added", key=f"{key_prefix}_added_{role['id']}", disabled=True, use_container_width=True)
            else:
                if st.button("⚖️ Compare", key=f"{key_prefix}_cmp_{role['id']}", use_container_width=True):
                    if len(compare_list) < 3:
                        compare_list.append(role)
                        st.session_state.compare_roles = compare_list
                        st.rerun()
                    else:
                        st.toast("Comparison max is 3 roles.")
