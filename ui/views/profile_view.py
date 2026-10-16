"""Profile questionnaire view (Step 1)."""
import streamlit as st
from ui.components import render_navbar
from services import career_service, auth_service


GRAD_YEAR_OPTIONS = ["2026 (Upcoming)", "2025", "2024", "2023", "2022 or earlier"]

EXPERIENCE_OPTIONS = [
    "Student / Fresher",
    "0–6 months (internship)",
    "6 months – 1 year",
    "1–2 years",
    "2+ years",
]

LOCATION_OPTIONS = [
    "Bangalore",
    "Mumbai / Pune",
    "Delhi / NCR / Gurgaon",
    "Hyderabad",
    "Chennai",
    "Remote / Flexible anywhere",
]

INTEREST_OPTIONS = [
    "AI, LLMs & Autonomous Agents",
    "Coding & Problem Solving",
    "Backend Systems & Databases",
    "Client Facing & Consulting",
    "Building Web Apps (Full Stack)",
    "UI/UX & Frontend Experiences",
    "Cloud, DevOps & Linux",
    "Data Analytics & Business Intelligence",
    "Machine Learning & Research",
    "Cybersecurity & Ethical Hacking",
    "Product Management & Strategy",
    "Automation & Testing Quality",
    "High-Impact Startup Fast-Paced",
]

SKILL_OPTIONS = [
    "Java", "Python", "JavaScript", "TypeScript", "C++", "C", "Go",
    "SQL / MySQL / PostgreSQL", "MongoDB", "Redis",
    "React.js", "Next.js", "HTML & CSS",
    "Spring Boot", "Django", "FastAPI", "Node.js", "Express.js",
    "Data Structures & Algorithms (DSA)",
    "Git & GitHub", "Docker", "Kubernetes", "Linux",
    "AWS", "GCP", "Azure",
    "Machine Learning (Scikit-Learn)", "Deep Learning (PyTorch)",
    "LLMs & Prompt Engineering", "LangChain / LangGraph",
    "Power BI", "Tableau", "Excel Modeling",
    "Client Communication", "Problem Solving", "System Architecture"
]

DEFAULT_INTERESTS = ["Coding & Problem Solving", "Backend Systems & Databases"]
DEFAULT_SKILLS = ["Java", "SQL / MySQL / PostgreSQL", "Data Structures & Algorithms (DSA)"]


def _index_of(options: list, value, default: int = 0) -> int:
    """Safely resolves a stored value to a selectbox index."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def _restore_interests(saved: dict) -> list:
    """Maps a saved profile back to interest labels (handles both stored formats)."""
    raw = [i for i in (saved.get("raw_interests") or []) if i in INTEREST_OPTIONS]
    if raw:
        return raw
    lower_map = {opt.lower(): opt for opt in INTEREST_OPTIONS}
    return [lower_map[i] for i in saved.get("interests", []) if i in lower_map]


def _restore_skills(saved: dict) -> list:
    """Keeps only stored skills that still exist as selectable options."""
    return [s for s in saved.get("current_skills", []) if s in SKILL_OPTIONS]


def render():
    render_navbar()

    st.markdown("## 👤 Step 1 — Build Your Candidate Profile")
    st.caption("Tell us about your background and interests so we can identify high-fit career trajectories.")
    st.markdown("---")

    saved = st.session_state.get("profile") or {}
    user = st.session_state.get("user")

    with st.form("form_candidate_profile"):
        c1, c2 = st.columns(2)

        with c1:
            default_name = saved.get("name") or (user["name"] if user else "")
            name = st.text_input("Full Name", value=default_name, placeholder="e.g. Mahek Agrawal")

            grad_year = st.selectbox(
                "Graduation Year",
                GRAD_YEAR_OPTIONS,
                index=_index_of(GRAD_YEAR_OPTIONS, saved.get("grad_year"))
            )

            experience = st.selectbox(
                "Experience Level",
                EXPERIENCE_OPTIONS,
                index=_index_of(EXPERIENCE_OPTIONS, saved.get("experience"))
            )

            location = st.selectbox(
                "Preferred Work Hub",
                LOCATION_OPTIONS,
                index=_index_of(LOCATION_OPTIONS, saved.get("location"))
            )

        with c2:
            st.markdown("**What genuinely interests you?** *(Roles will match these strictly)*")
            interests = st.multiselect(
                "Core Career Interests",
                options=INTEREST_OPTIONS,
                default=_restore_interests(saved) or DEFAULT_INTERESTS,
                help="Your suggested roles will be strictly aligned with these chosen interest areas."
            )

            current_skills = st.multiselect(
                "Existing Technical Skills",
                options=SKILL_OPTIONS,
                default=_restore_skills(saved) or DEFAULT_SKILLS,
                help="Include tools you've explored in classes, projects, or self-study."
            )

        submit = st.form_submit_button("Find Matching Roles →", type="primary", use_container_width=True)

    if submit:
        if not name.strip():
            st.warning("Please provide your name.")
        elif not interests:
            st.warning("Please select at least one interest area.")
        elif not current_skills:
            st.warning("Please choose at least one skill you are familiar with.")
        else:
            profile = {
                "name": name.strip(),
                "grad_year": grad_year,
                "experience": experience,
                "location": location,
                "current_skills": current_skills,
                "interests": [i.lower() for i in interests],
                "raw_interests": interests
            }
            st.session_state.profile = profile

            if user:
                auth_service.save_user_profile(user["id"], profile)

            scored = career_service.match_roles_smart(profile)
            st.session_state.scored_roles = scored
            st.session_state.matched_roles = [r for _, r in scored]
            st.session_state.pop("match_explanation", None)
            st.session_state.page = "roles"
            st.rerun()
