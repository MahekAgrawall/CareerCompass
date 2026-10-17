"""
Central configuration for CareerCompass.

Keeping the option vocabularies in one place stops the profile questionnaire,
the matching engine, and the UI from drifting apart over time.
"""

APP_NAME = "CareerCompass"

GRAD_YEAR_OPTIONS = ["2026 (Upcoming)", "2025", "2024", "2023", "2022 or earlier"]

EXPERIENCE_OPTIONS = [
    "Student / Fresher",
    "0–6 months (internship)",
    "6 months – 1 year",
    "1–2 years",
    "2+ years",
]

# Preferred work hubs: the Indian hubs the salary bands are built around first,
# then the international hubs the live job boards actually publish into. Kept in
# step with `frontend/src/lib/options.ts`.
LOCATION_OPTIONS = [
    "Bangalore",
    "Mumbai / Pune",
    "Delhi / NCR / Gurgaon",
    "Hyderabad",
    "Chennai",
    "Remote / Flexible anywhere",
    "London (UK)",
    "Dublin (Ireland)",
    "Berlin (Germany)",
    "Amsterdam (Netherlands)",
    "Zurich (Switzerland)",
    "Barcelona / Madrid (Spain)",
    "Stockholm (Sweden)",
    "Dubai (UAE)",
    "Singapore",
    "Toronto / Vancouver (Canada)",
    "New York (USA)",
    "San Francisco / Bay Area (USA)",
    "Sydney (Australia)",
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
    "Client Communication", "Problem Solving", "System Architecture",
]

DEFAULT_INTERESTS = ["Coding & Problem Solving", "Backend Systems & Databases"]
DEFAULT_SKILLS = ["Java", "SQL / MySQL / PostgreSQL", "Data Structures & Algorithms (DSA)"]
