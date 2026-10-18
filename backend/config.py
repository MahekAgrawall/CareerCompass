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

# ── The role catalog's category vocabulary ────────────────────────────────────
# A *closed* taxonomy. These eight are what `data/roles.json` organises the
# catalog into, and they are what the directory's Category dropdown offers. A
# role whose category is anything else — a label a future catalog introduces
# before the taxonomy is widened, a typo, a blank — is reported as
# OTHER_CATEGORY rather than becoming a ninth category of its own: the filter
# stays total (every role is reachable through it) and the catalog's vocabulary
# stays honest (a category nobody declared is not one). Unlike the other
# vocabularies here, the client does not mirror this one — it reads the list from
# `GET /roles/categories`, so the taxonomy has exactly one definition.
ROLE_CATEGORIES = [
    "AI / ML",
    "Data & Analytics",
    "Development",
    "Engineering & Consulting",
    "Hardware & Embedded",
    "Infrastructure & Cloud",
    "Product & Strategy",
    "Security",
]

# The escape hatch, offered last in the dropdown: where a role is filed when its
# classification is *uncertain* rather than merely niche. Not a peer of the
# eight — nothing is declared into it, roles only fall into it.
OTHER_CATEGORY = "Other / Unclassified"

# The filter's "no category filter" value. Like OTHER_CATEGORY it is not a
# category: no role is ever labelled with it.
ALL_CATEGORIES = "All Categories"

# ── What a live listing is classified as ──────────────────────────────────────
# A *declared* vocabulary rather than whatever the model writes. Two reasons: the
# same advert must not come back as "SRE" today and "Site Reliability Engineer"
# tomorrow, and a vocabulary nobody wrote down cannot be tested. Each entry is a
# role *family* — deliberately narrower than its category, because the whole point
# is that a Site Reliability Engineer, a DevOps Engineer and a Platform Engineer
# are three different jobs inside one category, and that Generative AI Engineering
# is not AI Agent Engineering. That is what lets a listing be grouped without being
# declared a duplicate of a neighbour that merely shares its skills. The families
# are the groupings of the catalog's own `data/roles.json` titles, so a listing
# classified here sits beside the catalogued roles a candidate can actually open.
CANONICAL_ROLES = {
    "AI / ML": (
        "Generative AI Engineering",
        "AI Agent Engineering",
        "Machine Learning Engineering",
        "ML Platform & MLOps Engineering",
        "Computer Vision Engineering",
        "Speech & Voice AI Engineering",
        "NLP & Conversational AI Engineering",
        "AI Research",
        "Responsible AI & AI Governance",
        "AI Solutions Architecture",
    ),
    "Data & Analytics": (
        "Data Engineering",
        "Analytics Engineering",
        "Data Science",
        "Business Intelligence & Analytics",
        "Data Architecture",
        "Database Administration",
        "Quantitative & Risk Analysis",
    ),
    "Development": (
        "Backend Development",
        "Frontend Development",
        "Full Stack Development",
        "Mobile Development",
        "Game & XR Development",
        "Quality & Test Automation",
        "Desktop Application Development",
        "Blockchain & Web3 Development",
        "Web CMS & Low-Code Development",
    ),
    "Engineering & Consulting": (
        "Technology Consulting",
        "Forward Deployed Engineering",
        "Management Consulting",
        "Technical Account Management",
        "Technical Writing & Documentation",
    ),
    "Hardware & Embedded": (
        "Embedded Firmware Engineering",
        "Embedded Systems & IoT Engineering",
        "DSP & Signal Processing Engineering",
        "FPGA Engineering",
        "VLSI Design Engineering",
        "Semiconductor Verification",
        "Robotics Engineering",
    ),
    "Infrastructure & Cloud": (
        "Cloud Architecture",
        "Cloud Engineering",
        "DevOps Engineering",
        "Site Reliability Engineering",
        "Platform Engineering",
        "Linux Systems Engineering",
        "Network Engineering",
        "Observability Engineering",
        "Virtualization & VMware Engineering",
        "IT & Technical Support",
    ),
    "Product & Strategy": (
        "Product Management",
        "Product Marketing",
        "Technical Program Management",
        "Program Management",
        "Product Design",
        "User Experience Research",
        "Content & UX Writing",
    ),
    "Security": (
        "Application Security",
        "Cloud Security Engineering",
        "Security Operations",
        "DevSecOps Engineering",
        "Identity & Access Management",
        "Penetration Testing",
        "Threat & Malware Analysis",
        "Governance, Risk & Compliance",
    ),
}

#: What a family is called when the advert does not say enough to place it. The
#: listing is *still* a listing — it is only the classification that is missing —
#: so this is reported as a value rather than as an absent field. Paired with
#: `OTHER_CATEGORY`, and the pair is what the API returns for such a listing.
UNCLASSIFIED_ROLE = "Unclassified"

#: The family -> category direction, derived so the two can never disagree: the
#: role is the finer claim, and this is what turns one into a category.
ROLE_CATEGORY_OF = {
    role: category for category, roles in CANONICAL_ROLES.items() for role in roles
}

#: How senior a listing is, as the *advert* states it — not as the boards label it.
#: `job_service.EXPERIENCE_LEVELS` stays what it is (a translation of whatever the
#: board published); this is a reading of the ad's own text, and the two are shown
#: side by side rather than folded into one, because they can honestly disagree: a
#: board files a "Senior Engineering Manager (Backend)" advert under no seniority at
#: all, and a title-only advert reads as `unknown`.
SENIORITY_LEVELS = ("internship", "entry", "mid", "senior", "lead", "unknown")

#: Where the work happens according to the advert's own words: "remote", "hybrid",
#: "onsite", or `unspecified` when it says nothing either way. Deliberately not the
#: boards' remote flag — that is a field some boards publish and others do not, and
#: merging the two readings would hide the case where they disagree.
WORK_ARRANGEMENTS = ("remote", "hybrid", "onsite", "unspecified")
