/**
 * Shared option vocabularies.
 * Kept in step with `backend/config.py` so the questionnaire, matching engine
 * and UI agree; originally ported verbatim from the legacy Streamlit app.
 */

export const GRAD_YEAR_OPTIONS = [
  "2026 (Upcoming)",
  "2025",
  "2024",
  "2023",
  "2022 or earlier",
] as const;

export const EXPERIENCE_OPTIONS = [
  "Student / Fresher",
  "0–6 months (internship)",
  "6 months – 1 year",
  "1–2 years",
  "2+ years",
] as const;

/**
 * Preferred work hub. The Indian hubs come first because the salary bands and
 * hiring-company lists are built around them, then the international hubs the
 * live job boards actually publish into — those boards skew European and
 * North-American, so a candidate aiming at them has to be able to name one.
 */
export const LOCATION_OPTIONS = [
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
] as const;

export const WORK_MODE_OPTIONS = [
  "No preference",
  "On-site",
  "Hybrid",
  "Remote",
] as const;

export const RELOCATE_OPTIONS = [
  "Not sure yet",
  "Yes, anywhere in India",
  "Yes, anywhere in the world",
  "Only my current city",
] as const;

export const CAREER_GOAL_OPTIONS = [
  "Still exploring",
  "First internship",
  "First full-time role",
  "Switch domains",
  "Upskilling while working",
] as const;

export const INTEREST_OPTIONS = [
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
] as const;

export const SKILL_OPTIONS = [
  "Java",
  "Python",
  "JavaScript",
  "TypeScript",
  "C++",
  "C",
  "Go",
  "SQL / MySQL / PostgreSQL",
  "MongoDB",
  "Redis",
  "React.js",
  "Next.js",
  "HTML & CSS",
  "Spring Boot",
  "Django",
  "FastAPI",
  "Node.js",
  "Express.js",
  "Data Structures & Algorithms (DSA)",
  "Git & GitHub",
  "Docker",
  "Kubernetes",
  "Linux",
  "AWS",
  "GCP",
  "Azure",
  "Machine Learning (Scikit-Learn)",
  "Deep Learning (PyTorch)",
  "LLMs & Prompt Engineering",
  "LangChain / LangGraph",
  "Power BI",
  "Tableau",
  "Excel Modeling",
  "Client Communication",
  "Problem Solving",
  "System Architecture",
] as const;

export const DEFAULT_INTERESTS = ["Coding & Problem Solving", "Backend Systems & Databases"];

export const DEFAULT_SKILLS = ["Java", "SQL / MySQL / PostgreSQL", "Data Structures & Algorithms (DSA)"];
