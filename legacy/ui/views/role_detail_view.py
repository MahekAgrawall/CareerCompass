"""Role specifications and deep-dive view."""
import streamlit as st
from ui.components import render_navbar


def render():
    render_navbar()

    role = st.session_state.get("selected_role")
    if not role:
        st.session_state.page = "directory"
        st.rerun()

    st.markdown(f"## {role['icon']} {role['title']}")
    st.caption(f"{role['category']} • {role.get('niche_category', 'Specialization')}")

    # Market Intelligence Panel
    st.markdown(
        f"""
        <div style='background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1.2rem; margin: 1rem 0;'>
            <div style='display: flex; justify-content: space-around; flex-wrap: wrap; text-align: center; gap: 1rem;'>
                <div>
                    <span style='color: #64748B; font-size: 0.82rem; font-weight: 600;'>MARKET DEMAND</span><br/>
                    <strong style='color: #DC2626; font-size: 1.05rem;'>{role.get('market_demand', 'High')}</strong>
                </div>
                <div>
                    <span style='color: #64748B; font-size: 0.82rem; font-weight: 600;'>COMPETITION LEVEL</span><br/>
                    <strong style='color: #D97706; font-size: 1.05rem;'>{role.get('competition_level', 'Moderate')}</strong>
                </div>
                <div>
                    <span style='color: #64748B; font-size: 0.82rem; font-weight: 600;'>10-YR AI RELEVANCE</span><br/>
                    <strong style='color: #16A34A; font-size: 1.05rem;'>{role.get('future_relevance', 'High')}</strong>
                </div>
                <div>
                    <span style='color: #64748B; font-size: 0.82rem; font-weight: 600;'>ROLE TYPE</span><br/>
                    <strong style='color: #7C3AED; font-size: 1.05rem;'>{'Niche Specialist 🎯' if role.get('is_niche') else 'Mainstream Core 🏢'}</strong>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(f"<p style='font-size: 1.02rem; color: #334155; line-height: 1.6;'>{role['description']}</p>", unsafe_allow_html=True)
    st.markdown("---")

    # Salary Trajectory
    st.markdown("### 💰 Compensation Benchmark (India)")
    sal = role["salary"]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(f"🌱 {sal['fresher_0_1']['label']}", f"₹{sal['fresher_0_1']['min']}–{sal['fresher_0_1']['max']} LPA")
    with c2:
        st.metric(f"📈 {sal['mid_1_3']['label']}", f"₹{sal['mid_1_3']['min']}–{sal['mid_1_3']['max']} LPA")
    with c3:
        st.metric(f"🚀 {sal['senior_3_plus']['label']}", f"₹{sal['senior_3_plus']['min']}–{sal['senior_3_plus']['max']} LPA")
    st.caption("*Source: Aggregated enterprise data from AmbitionBox, Glassdoor, and LinkedIn Indian Tech Index.*")

    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### 📋 Primary Responsibilities")
        for r in role["responsibilities"]:
            st.markdown(f"• {r}")

        st.markdown("### 🎓 Recommended Qualifications")
        for q in role["qualifications"]:
            st.markdown(f"• {q}")

    with col_right:
        st.markdown("### 📈 Career Progression")
        for idx, step in enumerate(role["growth_path"]):
            prefix = "🟢 **Entry:**" if idx == 0 else ("⭐ **Apex:**" if idx == len(role["growth_path"]) - 1 else "↗️")
            st.markdown(f"{prefix} {step}")

        st.markdown("### 🏢 Hiring Companies in India")
        st.markdown(", ".join(role["top_companies"]))

    st.markdown("---")
    st.markdown("### 🛠️ Required Technical Competencies")
    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        st.markdown("**✅ Must-Have Foundations**")
        for s in role["skills"]["must_have"]:
            st.markdown(f"• {s}")
    with cs2:
        st.markdown("**⭐ Competitive Accelerators**")
        for s in role["skills"]["good_to_have"]:
            st.markdown(f"• {s}")
    with cs3:
        st.markdown("**💡 Advanced Niche Strengths**")
        for s in role["skills"]["can_have"]:
            st.markdown(f"• {s}")

    st.markdown("---")
    # Action buttons
    cb1, cb2, cb3, cb4 = st.columns([2.0, 1.8, 1.2, 1.0])
    with cb1:
        if st.button("Generate AI Skill Roadmap", type="primary", use_container_width=True):
            st.session_state.roadmap = None
            st.session_state.page = "roadmap"
            st.rerun()
    with cb2:
        if st.button("📅 Open Study Hours Tracker", use_container_width=True):
            st.session_state.page = "tracker"
            st.rerun()
    with cb3:
        compare_list = st.session_state.get("compare_roles", [])
        already = role["id"] in [r["id"] for r in compare_list]
        if not already:
            if st.button("⚖️ Compare", use_container_width=True):
                if len(compare_list) < 3:
                    compare_list.append(role)
                    st.session_state.compare_roles = compare_list
                    st.rerun()
        else:
            st.button("✓ Added", disabled=True, use_container_width=True)
    with cb4:
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "roles" if st.session_state.get("matched_roles") else "directory"
            st.rerun()
