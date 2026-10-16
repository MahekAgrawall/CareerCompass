"""Smart matched roles view (Step 2)."""
import streamlit as st
from ui.components import render_navbar, render_role_card
from services import career_service, ai_service


def render():
    render_navbar()

    profile = st.session_state.get("profile", {})
    scored = st.session_state.get("scored_roles", [])

    if not scored and profile:
        scored = career_service.match_roles_smart(profile)
        st.session_state.scored_roles = scored
        st.session_state.matched_roles = [r for _, r in scored]

    st.markdown(f"## 🎯 Step 2 — Roles Matched for **{profile.get('name', 'You')}**")
    st.caption("Filtered strictly according to your selected career interests and current technical baseline.")

    if not scored:
        st.info("No roles strictly matched your selected interest combination. Try broadening your interests or explore our complete catalog.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Edit Interests in Profile", use_container_width=True):
                st.session_state.page = "profile"
                st.rerun()
        with c2:
            if st.button("Browse All Roles Directory", use_container_width=True, type="primary"):
                st.session_state.page = "directory"
                st.rerun()
        return

    # AI Match Assessment
    if "match_explanation" not in st.session_state:
        with st.spinner("Analyzing candidate interest synergy..."):
            st.session_state.match_explanation = ai_service.generate_role_match_explanation(
                profile, [r for _, r in scored]
            )

    st.info(f"💡 **Strategic Fit Assessment:** {st.session_state.match_explanation}")

    st.markdown(f"**Identified {len(scored)} high-alignment roles:**")
    st.markdown("")

    # Grid Display (3 columns)
    for i in range(0, len(scored), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(scored):
                match_pct, role = scored[i + j]
                with col:
                    render_role_card(role, match_pct=match_pct, key_prefix="matched")

    st.markdown("---")
    col_back, col_cmp, col_dir = st.columns([1.5, 2.0, 1.5])
    with col_back:
        if st.button("← Modify Profile", use_container_width=True):
            st.session_state.page = "profile"
            st.rerun()
    with col_cmp:
        cmp_len = len(st.session_state.get("compare_roles", []))
        if cmp_len > 0:
            if st.button(f"Compare Selected Roles ({cmp_len})", use_container_width=True, type="primary"):
                st.session_state.page = "compare"
                st.rerun()
    with col_dir:
        if st.button("Explore All Roles Catalog →", use_container_width=True):
            st.session_state.page = "directory"
            st.rerun()
