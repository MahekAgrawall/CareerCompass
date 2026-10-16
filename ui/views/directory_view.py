"""Comprehensive All Roles Directory view."""
import streamlit as st
from ui.components import render_navbar, render_role_card
from services import career_service


def render():
    render_navbar()

    st.markdown("## 📚 Comprehensive Technology Roles Catalog")
    st.caption("Browse all corporate, AI, and specialized technology roles with Indian compensation benchmarks.")
    st.markdown("---")

    # Filter Controls
    c_search, c_cat, c_niche = st.columns([2.0, 1.4, 1.4])
    with c_search:
        search_query = st.text_input("Search by role title, skill, or keyword", placeholder="e.g. Agent, Java, Cloud, Palantir, SQL...")
    with c_cat:
        all_cats = ["All Categories"] + career_service.get_all_categories()
        cat_filter = st.selectbox("Category", all_cats)
    with c_niche:
        niche_filter = st.selectbox("Role Classification", ["All Roles", "Niche Specialists Only 🎯", "Mainstream Core Only 🏢"])

    filtered_roles = career_service.search_and_filter_roles(
        search_query=search_query,
        category=cat_filter,
        niche_filter=niche_filter
    )

    st.markdown(f"**Showing {len(filtered_roles)} roles:**")
    st.markdown("")

    for i in range(0, len(filtered_roles), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(filtered_roles):
                role = filtered_roles[i + j]
                with col:
                    render_role_card(role, match_pct=None, key_prefix="dir")
