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
        st.session_state.matched_roles = [item["role"] for item in scored]

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
                profile, [item["role"] for item in scored]
            )

    st.info(f"💡 **Strategic Fit Assessment:** {st.session_state.match_explanation}")

    # ── Refine controls ────────────────────────────────────────────────────────
    fc1, fc2 = st.columns([2.4, 1.4])
    with fc1:
        query = st.text_input(
            "Filter matches",
            placeholder="🔎 Search your matches by role, skill, or company...",
            label_visibility="collapsed",
        )
    with fc2:
        sort_by = st.selectbox(
            "Sort matches",
            ["Best match", "Fresher salary (high → low)", "Market demand"],
            label_visibility="collapsed",
        )

    def _matches_query(item):
        if not query.strip():
            return True
        q = query.strip().lower()
        r = item["role"]
        haystack = [r["title"], r["description"], r["category"],
                    *r["skills"]["must_have"], *r["top_companies"]]
        return any(q in str(x).lower() for x in haystack)

    def _demand_rank(value):
        v = value or ""
        if v.startswith("Hyper"):
            return 4
        if v.startswith("Very High"):
            return 3
        if v.startswith("High"):
            return 2
        if v.startswith("Moderate"):
            return 1
        return 2

    display = [item for item in scored if _matches_query(item)]

    if sort_by == "Fresher salary (high → low)":
        display.sort(key=lambda it: it["role"]["salary"]["fresher_0_1"]["max"], reverse=True)
    elif sort_by == "Market demand":
        display.sort(key=lambda it: _demand_rank(it["role"].get("market_demand")), reverse=True)

    if not display:
        st.warning("None of your matches match that search. Clear the filter to see all matches again.")
    else:
        st.markdown(f"**Showing {len(display)} of {len(scored)} matched roles:**")
        st.markdown("")

    # Grid Display (3 columns)
    for i in range(0, len(display), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(display):
                item = display[i + j]
                with col:
                    render_role_card(
                        item["role"],
                        match_pct=item["score"],
                        key_prefix="matched",
                        match_details=item,
                    )

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
