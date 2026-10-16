"""Home landing view."""
import streamlit as st
from ui.components import render_navbar


def render():
    render_navbar()

    # Clean Hero Section
    st.markdown("""
    <div class="hero-card">
        <h1 style='font-size: 2.6rem; font-weight: 800; margin-bottom: 0.6rem; letter-spacing: -0.02em;'>
            Navigate Your Tech Career with Precision
        </h1>
        <p style='font-size: 1.15rem; color: #94A3B8; max-width: 720px; line-height: 1.6; margin-bottom: 0;'>
            CareerCompass maps your skills and interests to high-demand corporate and modern engineering roles in India — complete with compensation benchmarks, AI-generated roadmaps, and custom study trackers.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 3 Strategic Pillars
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("### 🎯 **Smart Interest Matching**")
            st.markdown("<p style='color:#64748B; font-size: 0.9rem;'>Filters roles based strictly on your genuine career interests, eliminating generic or mismatched suggestions.</p>", unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            st.markdown("### 📊 **Market Intelligence**")
            st.markdown("<p style='color:#64748B; font-size: 0.9rem;'>Accurate Indian CTC trajectories (0-1y, 1-3y, 3+y), market competition levels, and 10-year AI relevance ratings.</p>", unsafe_allow_html=True)
    with c3:
        with st.container(border=True):
            st.markdown("### 📅 **Personalized Study Tracker**")
            st.markdown("<p style='color:#64748B; font-size: 0.9rem;'>Configurable study pace (weekdays vs weekends) with subtopic checklists and timeline completion projections.</p>", unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # Clean Call-to-Actions
    col_a, col_b = st.columns([1.6, 1.0])
    with col_a:
        with st.container(border=True):
            st.markdown("#### ✨ **Step 1: Discover Your Role Fit**")
            st.markdown("<p style='color:#64748B; font-size: 0.9rem;'>Take a 2-minute profile questionnaire to get matched with corporate tech specializations.</p>", unsafe_allow_html=True)
            if st.button("Build Candidate Profile", type="primary", use_container_width=True):
                st.session_state.page = "profile"
                st.rerun()

    with col_b:
        with st.container(border=True):
            st.markdown("#### 📚 **Explore All Roles**")
            st.markdown("<p style='color:#64748B; font-size: 0.9rem;'>Browse our database of 15+ technology and corporate roles.</p>", unsafe_allow_html=True)
            if st.button("Open Role Directory", use_container_width=True):
                st.session_state.page = "directory"
                st.rerun()
