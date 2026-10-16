"""Side-by-side Role Comparison View."""
import streamlit as st
from ui.components import render_navbar


def render():
    render_navbar()

    roles = st.session_state.get("compare_roles", [])
    if not roles:
        st.info("No roles selected for comparison yet. Select up to 3 roles from the directory or your matches.")
        if st.button("Browse Roles Directory", type="primary"):
            st.session_state.page = "directory"
            st.rerun()
        return

    st.markdown("## ⚖️ Compare Selected Roles Side-by-Side")
    st.caption(f"Benchmarking {len(roles)} technology career paths")
    st.markdown("---")

    cols = st.columns(len(roles))
    for col, role in zip(cols, roles):
        with col:
            with st.container(border=True):
                st.markdown(f"### {role['icon']} {role['title']}")
                st.caption(role["category"])

                st.markdown("---")
                st.markdown(f"**🔥 Demand:** {role.get('market_demand', 'High')}")
                st.markdown(f"**⚔️ Competition:** {role.get('competition_level', 'Moderate')}")
                st.markdown(f"**🚀 10-Yr AI Future:** {role.get('future_relevance', 'High').split('(')[0]}")

                st.markdown("---")
                st.markdown("**💰 CTC (India):**")
                sal = role["salary"]
                st.markdown(f"• Fresher: ₹{sal['fresher_0_1']['min']}–{sal['fresher_0_1']['max']} LPA")
                st.markdown(f"• 1–3 Yrs: ₹{sal['mid_1_3']['min']}–{sal['mid_1_3']['max']} LPA")
                st.markdown(f"• 3+ Yrs: ₹{sal['senior_3_plus']['min']}–{sal['senior_3_plus']['max']} LPA")

                st.markdown("---")
                st.markdown("**🛠️ Must-Have Foundations:**")
                for s in role["skills"]["must_have"][:4]:
                    st.markdown(f"• {s}")

                st.markdown("---")
                st.markdown("**🏢 Top Hiring Firms:**")
                st.markdown(", ".join(role["top_companies"][:4]))

                st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
                if st.button("Generate Roadmap", key=f"cmp_rdm_{role['id']}", use_container_width=True, type="primary"):
                    st.session_state.selected_role = role
                    st.session_state.roadmap = None
                    st.session_state.page = "roadmap"
                    st.rerun()

    st.markdown("---")
    c1, c2 = st.columns([1.5, 4.0])
    with c1:
        if st.button("← Back"):
            st.session_state.page = "roles" if st.session_state.get("matched_roles") else "directory"
            st.rerun()
    with c2:
        if st.button("🗑️ Clear Comparison"):
            st.session_state.compare_roles = []
            st.session_state.page = "directory"
            st.rerun()
