# 🧭 CareerCompass

> An AI-powered career guidance and learning-progression platform for B.Tech CSE students and early-career professionals in India.

CareerCompass is more than a role quiz. It matches you to high-fit tech roles, benchmarks Indian
compensation, generates a personalized AI skill roadmap, and turns that roadmap into a trackable,
week-by-week study plan — with a context-aware AI mentor you can chat with throughout.

The project is a **monorepo**: a **FastAPI** backend, a **React + TypeScript** single-page frontend,
and the original **Streamlit** app preserved in `legacy/` for reference.

---

## ✨ Features

| Feature | What it does |
|---|---|
| 🎯 **Interest-first, transparent role matching** | Ranks roles by how well they align with your *stated* interests (65% weight) and your existing skills (35% weight), and filters out roles with zero interest synergy. Every card shows the arithmetic: the two component scores, the interests and skills that counted, and the profile chips that would raise the match. |
| 📚 **Role catalog** | 30 curated corporate and modern engineering roles across 8 categories — including AI/ML, data, cloud, security, hardware and product tracks — each with responsibilities, qualifications, growth paths, and hiring companies. |
| 💰 **India salary benchmarks** | Fresher (0–1 yr), mid (1–3 yrs) and senior (3+ yrs) CTC bands for every role, each stated as an *envelope* — low end a typical mid-market/services offer, high end a strong product-company or GCC offer — with the market and product-company medians and every source (and its sample size) linked on the role page. |
| 🤖 **AI skill roadmap** | Google Gemini generates a structured 3-phase plan (Immediate → Level Up → Explore) with one curated free resource per skill. |
| 🛠️ **Portfolio projects** | Each roadmap includes 3 hands-on project ideas with difficulty ratings and validated skills. |
| 📅 **Study tracker** | Configure weekday vs weekend study hours and a role-specific tech stack. Every one of the 30 roles ships a tailored three-dimension stack (mobile, games, embedded, design, offensive security and more), and each choice maps onto syllabus topics with subtopics. Progress, remaining hours, and projected weeks are computed live. |
| ⚖️ **Side-by-side comparison** | Compare up to 3 roles on demand, competition, AI-future relevance, salary, and must-have skills. |
| 💬 **Roadmap Copilot** | A multi-turn Gemini chat pre-loaded with your profile, target role, and roadmap — replies stream in live. |
| ⬇️ **Export & share** | Download any roadmap as a portable Markdown file. |
| 🔗 **Deep links** | Every view is its own URL (`/roles/backend_dev`, `/tracker/backend_dev`), so refreshing or sharing a link returns you to the same page. |
| 🔑 **Accounts & persistence** | Sign up / sign in (JWT bearer, SQLite-backed), saved profiles, and a **My Roadmaps** library of every plan you generate. |

### 💰 How the salary bands work

The bands are an **envelope**, not a survey of one employer tier: the low end is a typical
mid-market or services offer, the high end a strong product-company or GCC offer. They were
last reviewed in **October 2026** against independently collected sources, and each role page
links every one of them:

| Reference point | Source | What it measures |
|---|---|---|
| Market median | [Indeed India salary pages](https://in.indeed.com/career/salaries) | What Indian employers actually post, mass market included (samples of 5–10,900 postings per title) |
| Product-company median | [Levels.fyi India](https://www.levels.fyi) | What product companies and GCCs pay for the same title, from verified offer letters |
| Fresher direction | [TeamLease Digital Skills & Salary Primer FY2025-26](https://business.teamleasedigital.com/digital-skills-and-salary-primer-fy2025-26/) | Where the 2026 fresher market sits (AI/Cloud start at ₹7–8.5 LPA) |

Two honesty rules are enforced by tests: every role cites at least one market-wide source,
and any role whose reference points are borrowed from an adjacent role family says so on the
page instead of hiding it. Where the sources disagree — and they disagree by design, because
they sample different employers — the band spans them rather than picking a winner.
AmbitionBox and Glassdoor, which this project cited before, block automated access; they were
replaced with sources a reader can actually open.

---

## 🏗️ Architecture

A monorepo with a clean client/server split and a layered backend:

```
┌────────────────────────────────────────────────────────────┐
│  frontend/   React + TypeScript SPA (Vite + Tailwind)      │
│              React Router · TanStack Query · JWT context   │
└───────────────────────────┬────────────────────────────────┘
                            │  REST / JSON  (Bearer JWT)
┌───────────────────────────▼────────────────────────────────┐
│  backend/    FastAPI                                       │
│              app/routers/*  →  app/schemas.py              │
│              app/dependencies.py (JWT) · app/security.py   │
├────────────────────────────────────────────────────────────┤
│  service layer   services/ai_service.py       (Gemini)     │
│                  services/career_service.py   (matching)   │
│                  services/tracker_service.py  (syllabus)   │
│                  services/auth_service.py     (accounts)   │
├────────────────────────────────────────────────────────────┤
│  data layer      database/db.py  →  SQLite                 │
│                  data/roles.json · data/stacks.json        │
└────────────────────────────────────────────────────────────┘
```

`legacy/` holds the original Streamlit application (UI + the same services), kept as a working
reference and design source.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ (developed on 3.14) |
| API framework | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| Auth | PyJWT (HS256 bearer tokens) + PBKDF2-HMAC-SHA256 password hashing |
| AI | Google Gemini (`gemini-flash-lite-latest`) via `google-generativeai` |
| Frontend language | TypeScript |
| Frontend framework | React 18 |
| Build tool | Vite 5 |
| Styling | Tailwind CSS 3 |
| Routing / data | React Router 6 · TanStack Query 5 |
| Persistence | SQLite (embedded, zero-config) |
| Config | `python-dotenv` (backend) · Vite env vars (frontend) |
| CI | GitHub Actions |

---

## 📂 Project Structure

```
career-compass/
│
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI app, CORS, routers, /health
│   │   ├── config.py          ← env-driven settings
│   │   ├── schemas.py         ← Pydantic request/response models
│   │   ├── security.py        ← JWT create/decode
│   │   ├── dependencies.py    ← get_current_user / get_optional_user
│   │   └── routers/           ← auth · roles · profile · match · roadmap · tracker · chat
│   ├── services/              ← ai · career · tracker · auth (shared domain logic)
│   ├── database/db.py         ← connection, schema, role-catalog sync
│   ├── data/                  ← roles.json · stacks.json
│   ├── tests/                 ← unittest: API integration + end-to-end journey
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── api/               ← fetch client, typed endpoints, mirrored types
│   │   ├── components/        ← navbar, role cards, badges, alerts, layout…
│   │   ├── pages/             ← home · auth · profile · matches · directory
│   │   │                        role detail · compare · roadmap · roadmaps
│   │   │                        tracker · chat
│   │   ├── state/             ← Auth · Profile · Compare · Roadmap contexts
│   │   └── lib/               ← option vocabularies, formatting, markdown export
│   ├── package.json
│   └── .env.example
│
├── legacy/                    ← original Streamlit app (UI/UX reference)
│
└── .github/workflows/ci.yml   ← backend tests + frontend type-check & build
```

---

## 🚀 Setup & Run Locally

Requires **Python 3.11+** and **Node 18+**. Run the backend and frontend in two terminals.

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/career-compass.git
cd career-compass
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # set JWT_SECRET (required) and GEMINI_API_KEY (optional)
python -m uvicorn app.main:app --reload
```

The API serves at <http://localhost:8000> (interactive docs at `/docs`). The SQLite database is
created automatically on first launch, and `backend/data/roles.json` — the catalog's source of
truth — is synced into it on every startup, so adding or editing a role there is picked up by the
next restart. Existing roles are updated in place and never deleted.

`backend/data/stacks.json` is the study-plan source of truth: it gives every role its
three-dimension stack selector (for example DevOps gets delivery pipelines and observability,
not "primary backend language"). `build_topics_from_choices()` turns the picked options into
syllabus topics — a fixed keyword map for the original roles, plus a block per newer
specialisation (mobile, games, embedded, design, offensive security, analytics engineering and
product/technical-programme tracks). Both live in `services/tracker_service.py`.

`JWT_SECRET` is required — generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. The API refuses to start without it.

Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com) → **Get API Key**.
AI features (roadmap, copilot) return `503` until `GEMINI_API_KEY` is set; everything else works without it.

### 3. Frontend (React)

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:5173>. The backend's `CORS_ORIGINS` already allows the Vite dev origin.

### 4. Legacy Streamlit app (optional, reference)

```bash
cd legacy
pip install -r requirements.txt
streamlit run app.py        # http://localhost:8501
```

---

## 🔌 API Reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | — | Service health |
| `POST` | `/auth/signup` | — | Create an account, returns a JWT |
| `POST` | `/auth/login` | — | Authenticate, returns a JWT |
| `GET` | `/auth/me` | ✅ | Current user + profile |
| `GET` | `/roles` | — | Full role catalog, each role carrying its salary bands, review date and sources |
| `GET` | `/roles/categories` | — | Distinct categories |
| `GET` | `/roles/{role_id}` | — | Single role, including its salary provenance |
| `GET` | `/profile` | ✅ | Saved profile |
| `PUT` | `/profile` | ✅ | Save profile |
| `POST` | `/match` | — | Ranked role matches with a score breakdown (+ optional AI explanation) |
| `POST` | `/roadmap` | optional | Generate an AI roadmap (saved when authenticated) |
| `GET` | `/roadmaps` | ✅ | Saved roadmap library |
| `DELETE` | `/roadmaps/{id}` | ✅ | Delete a saved roadmap |
| `GET` | `/tracker/stack/{role_id}` | — | Specialization stack schema |
| `GET` | `/tracker/schedule/{role_id}` | optional | Study schedule |
| `PUT` | `/tracker/schedule` | optional | Save schedule (+ rebuild syllabus) |
| `GET` | `/tracker/topics/{role_id}` | optional | Syllabus topics + metrics |
| `PATCH` | `/tracker/topics/{topic_id}` | optional | Toggle a topic |
| `POST` | `/chat` | — | Copilot reply (non-streaming) |
| `POST` | `/chat/stream` | — | Copilot reply (streamed text) |

Full OpenAPI schema is available at `/docs` and `/openapi.json`.

---

## 🔐 Auth & Security

- **JWT bearer tokens** (HS256). The frontend stores the token in `sessionStorage`, so sign-in is
  scoped to the browser tab and cleared when it closes — no cross-restart "remember me".
- Passwords are stored with salted **PBKDF2-HMAC-SHA256** (200k iterations); legacy unsalted hashes
  are upgraded automatically on next successful login.

---

## 🤖 AI Integration

- **Role match explanation** — the score breakdown (interest vs skill fit, matched chips, what to add) is
  computed deterministically and needs no API key; Gemini adds a natural-language assessment on top.
- **Personalized roadmap** — a 3-phase plan tailored to skills you *don't* already have.
- **Structured output** — `response_mime_type="application/json"` with JSON extract + validate + retry.
- **Roadmap Copilot** — a context-aware multi-turn chat, streamed chunk-by-chunk.
- **Graceful degradation** — a missing key surfaces a friendly `503`; the frontend shows setup
  guidance, and the match grid still renders because the AI assessment loads independently.

---

## 🧪 Testing & CI

Backend integration tests use the standard library's `unittest` (no extra dependencies):

```bash
cd backend
python -m unittest discover -s tests -t . -v
```

The suite is fully isolated: `tests/harness.py` points the app at a throwaway SQLite
database in a temporary directory, so no test can read or touch
`backend/data/career_compass.db`. `tests/test_api.py` pins the endpoint contracts —
auth, role catalog, matching, tracker, profiles and saved roadmaps, including that a
user can only ever reach their own records. `tests/test_roles_catalog.py` guards the
catalog itself: every role carries the full content contract, the salary bands rise
with seniority, every band cites dated, attributable sources (and explains itself when its
reference points are proxied from an adjacent role family), every role is reachable from a
real questionnaire answer, and an older database gains new roles — and the salary
provenance columns — on startup without losing saved work.
`tests/test_e2e_journey.py` walks the whole
candidate journey end to end: browse → register → sign in → profile → ranked matches →
role detail → study plan → tick off a topic → saved library, plus a check that progress
survives a new session. `tests/test_tracker_syllabus.py` guards the study plans: every
catalogued role has a tailored stack, every option maps onto real content, every
combination produces a usable plan, and the original roles' shipped plans are pinned so
adding content for newer roles cannot rewrite them. `tests/test_matching.py` guards the
transparency contract: the two component scores reproduce the published score, half-point
scores round the way a reader rounds them, and every suggested skill is a real chip that
cannot lower the match it was offered for.

The frontend is checked with the TypeScript compiler and a production build:

```bash
cd frontend
npm run typecheck
npm run build
```

GitHub Actions runs both on every push and pull request (see `.github/workflows/ci.yml`).

---

## ⚠️ Known Limitations & Roadmap

- **AI SDK** — `google-generativeai` is deprecated by Google; migrating to `google-genai` is planned.
- **Refresh tokens** — access tokens are long-lived for a demo; refresh-token rotation is future work.
- **Theming** — a single polished light theme.

---

## 📄 License

MIT License — free to use, modify, and share.
