# 🧭 CareerCompass

> An AI-powered career guidance and learning-progression platform for B.Tech CSE students and early-career professionals in India.

CareerCompass is more than a role quiz. It matches you to high-fit tech roles, benchmarks Indian
compensation, generates a personalized AI skill roadmap, and turns that roadmap into a trackable,
week-by-week study plan — with a context-aware AI mentor you can chat with throughout.

---

## ✨ Features

| Feature | What it does |
|---|---|
| 🎯 **Interest-first role matching** | Ranks roles by how well they align with your *stated* interests (65% weight) and your existing skills (35% weight), and filters out roles with zero interest synergy. |
| 📚 **Role catalog** | 15 curated corporate and modern engineering roles with responsibilities, qualifications, growth paths, and hiring companies. |
| 💰 **India salary benchmarks** | Fresher (0–1 yr), mid (1–3 yrs), and senior (3+ yrs) CTC ranges aggregated from AmbitionBox, Glassdoor, and LinkedIn India tech data. |
| 🤖 **AI skill roadmap** | Google Gemini generates a structured 3-phase plan (Immediate → Level Up → Explore) with one curated free resource per skill. |
| 🛠️ **Portfolio projects** | Each roadmap includes 3 hands-on project ideas with difficulty ratings and validated skills. |
| 📅 **Study tracker** | Configure weekday vs weekend study hours and a role-specific tech stack; check off granular topics and subtopics. Progress, remaining hours, and projected weeks are computed live. |
| ⚖️ **Side-by-side comparison** | Compare up to 3 roles on demand, competition, AI-future relevance, salary, and must-have skills. |
| 💬 **Roadmap Copilot** | A multi-turn Gemini chat pre-loaded with your profile, target role, and roadmap — replies stream in live, and answers are always specific to you. |
| ⬇️ **Export & share** | Download any roadmap as a portable Markdown file. |
| 🔗 **Deep links** | The current view lives in the URL (`?page=role_detail&id=backend_dev`), so refreshing or sharing a link returns you to the same page. |
| 🔑 **Accounts & persistence** | Sign up / sign in (SQLite-backed), saved profiles, and a **My Roadmaps** library of every plan you generate. |

---

## 🏗️ Architecture

A clean, layered Streamlit application:

```
┌─────────────────────────────────────────────────────────┐
│  UI layer          ui/views/*  (10 routed views)        │
│                    ui/components.py  ui/theme.py        │
├─────────────────────────────────────────────────────────┤
│  Service layer     services/ai_service.py  (Gemini)     │
│                    services/career_service.py (matching)│
│                    services/tracker_service.py (syllabus)│
│                    services/auth_service.py (accounts)  │
├─────────────────────────────────────────────────────────┤
│  Data layer        database/db.py  →  SQLite            │
│                    data/roles.json (seed catalog)       │
└─────────────────────────────────────────────────────────┘
```

`app.py` is a thin controller: it configures the page, applies the theme, initializes the database,
restores the session, and dispatches to a view through a simple `ROUTER` dict.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ (developed on 3.14) |
| UI framework | Streamlit 1.66 |
| AI model | Google Gemini (`gemini-flash-lite-latest`) |
| AI SDK | `google-generativeai` |
| Persistence | SQLite (embedded, zero-config) |
| Config | `python-dotenv` |
| Deployment | Streamlit Community Cloud (or any host) |

---

## 📂 Project Structure

```
career-compass/
│
├── app.py                     ← App controller, session state & view router
├── requirements.txt
├── .env.example               ← Template for GEMINI_API_KEY
│
├── database/
│   └── db.py                  ← Connection, schema, and role seeding
│
├── services/
│   ├── ai_service.py          ← Gemini roadmap, match explanation & copilot
│   ├── career_service.py      ← Role queries, search/filter, smart matching
│   ├── tracker_service.py     ← Study stacks, syllabus synthesis, progress math
│   └── auth_service.py        ← Accounts, sessions, profiles, saved roadmaps
│
├── ui/
│   ├── theme.py               ← Global CSS design system
│   ├── components.py          ← Navbar, role cards, badges
│   └── views/                 ← home · auth · profile · roles · directory
│                                 role_detail · compare · roadmap · roadmaps
│                                 tracker · chat
│
└── data/
    ├── roles.json             ← 15-role seed catalog
    └── career_compass.db      ← SQLite database (created on first run)
```

---

## 🚀 Setup & Run Locally

### 1. Clone
```bash
git clone https://github.com/YOUR_USERNAME/career-compass.git
cd career-compass
```

### 2. Create a virtual environment & install dependencies
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Get a free Gemini API key
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with Google → **Get API Key** → **Create API key**
3. Copy the key

### 4. Configure the key
```bash
cp .env.example .env
# then edit .env and replace the placeholder:
# GEMINI_API_KEY=your_real_key_here
```

### 5. Run
```bash
streamlit run app.py
```
Open <http://localhost:8501>.

The SQLite database and role catalog are created automatically on first launch — no manual migration step.

---

## 🗂️ Data Model (SQLite)

| Table | Purpose |
|---|---|
| `users` | Account credentials (hashed passwords) |
| `profiles` | Candidate questionnaire answers (skills, interests, location, experience) |
| `roles` | Role catalog seeded from `data/roles.json` |
| `roadmaps` | Every AI roadmap a user generates (powers **My Roadmaps**) |
| `study_schedules` | Per-user, per-role study hours and chosen tech stack |
| `tracker_topics` | Granular syllabus topics with completion markers |
| `user_sessions` | Remembered sign-in sessions |

---

## 🎯 Roles Covered (15)

| Category | Roles |
|---|---|
| Development | Backend Dev, Frontend Dev, Full Stack Dev, Forward-Deployed Engineer |
| AI / ML | AI/GenAI (Agentic) Engineer, ML Engineer, Data Scientist |
| Data & Analytics | Data Engineer, Data Analyst |
| Infrastructure | Cloud Engineer, SRE / Platform Engineer |
| Business | Business Analyst, Associate Product Manager |
| Quality | QA / Automation Engineer |
| Security | Cybersecurity Analyst |

---

## 🤖 AI Integration Details

- **Role match explanation** — Gemini explains, in natural language, why your matched roles fit your profile.
- **Personalized roadmap** — a 3-phase plan (Immediate Focus → Level Up → High-Growth) tailored to skills you *don't* already have.
- **Structured output** — uses `response_mime_type="application/json"` for reliable, parseable responses.
- **Portfolio projects** — 3 role-specific project ideas with difficulty and validated skills.
- **Roadmap Copilot** — a context-aware multi-turn chat pre-seeded with your profile, role, and roadmap.
- **Graceful config handling** — if `GEMINI_API_KEY` is missing, the app shows a friendly setup prompt instead of crashing.

---

## ⚠️ Known Limitations & Roadmap

Tracked honestly, because these are the next things to fix:

- **Sessions** — sign-in is scoped to the current browser session (no persistent "remember me"); a cookie-based option is planned. Passwords are stored with salted **PBKDF2-HMAC-SHA256**.
- **AI SDK** — `google-generativeai` is deprecated by Google; migrating to `google-genai` is planned.
- **Theming** — a single polished light theme; a dark mode would require a Streamlit theme-config approach.
- **No automated tests yet.**

---

## 📄 License

MIT License — free to use, modify, and share.
