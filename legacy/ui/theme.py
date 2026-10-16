"""
Theme & Visual Design System for CareerCompass.
Defines professional corporate palettes, typography, and clean micro-interactions.
"""

import streamlit as st

def apply_theme():
    """Injects professional corporate styling into the Streamlit session."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Global Typography & Reset */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #0F172A;
        letter-spacing: -0.01em;
    }

    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Completely Remove Header Anchor Link Icons next to headings */
    [data-testid="stHeaderActionElements"],
    a[data-testid="stHeaderActionElements"],
    .stMarkdown a.anchor-link,
    [data-testid="stMarkdownContainer"] a.anchor-link,
    [data-testid="stMarkdownContainer"] a[href^="#"],
    a.anchorjs-link {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* Hide Deploy Button and top toolbar that overlaps page headers */
    .stDeployButton,
    [data-testid="stToolbarActions"],
    [data-testid="stDecoration"],
    #MainMenu {
        display: none !important;
        visibility: hidden !important;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
        height: 1.2rem !important;
        z-index: 1 !important;
    }

    /* Main Container Padding - properly offset from top bar */
    .block-container {
        padding-top: 2.0rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1200px !important;
    }

    /* Keyframe Animations */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(6px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .animated-section {
        animation: fadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    /* Professional Card Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
        border: 1px solid #E2E8F0 !important;
        background-color: #FFFFFF !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px -4px rgba(15, 23, 42, 0.08) !important;
        border-color: #CBD5E1 !important;
    }

    /* Primary & Secondary Buttons */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.1rem !important;
        transition: all 0.18s ease-in-out !important;
    }

    .stButton > button[kind="primary"] {
        background: #4338CA !important;
        border: 1px solid #3730A3 !important;
        color: #FFFFFF !important;
    }

    .stButton > button[kind="primary"]:hover {
        background: #3730A3 !important;
        box-shadow: 0 4px 12px rgba(67, 56, 202, 0.25) !important;
    }

    /* Badges */
    .badge {
        display: inline-flex;
        align-items: center;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.76rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .badge-demand { background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; }
    .badge-comp { background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; }
    .badge-future { background: #DCFCE7; color: #166534; border: 1px solid #BBF7D0; }
    .badge-match { background: #EEF2FF; color: #3730A3; border: 1px solid #C7D2FE; font-weight: 700; }
    .badge-niche { background: #F3E8FF; color: #6B21A8; border: 1px solid #E9D5FF; }

    /* Hero Banner */
    .hero-card {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 2.2rem 2rem;
        color: #FFFFFF;
        margin-bottom: 1.8rem;
    }

    /* Checklist subtopic items */
    .subtopic-item {
        font-size: 0.88rem;
        color: #475569;
        margin-left: 1.6rem;
        margin-bottom: 4px;
        position: relative;
    }
    .subtopic-item::before {
        content: "•";
        color: #94A3B8;
        font-weight: bold;
        position: absolute;
        left: -12px;
    }
    </style>
    """, unsafe_allow_html=True)
