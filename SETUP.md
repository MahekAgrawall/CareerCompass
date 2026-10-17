# 🚀 CareerCompass — Local Setup & Run Guide

Step-by-step instructions to get the **backend (FastAPI)** and **frontend (React)** running locally.

> Windows commands are PowerShell. macOS/Linux alternatives are given where they differ.

---

## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11+ (3.14 tested) | `python --version` |
| Node.js | 18+ (24 tested) | `node --version` |
| npm | comes with Node | `npm --version` |

You do **not** need a database server — SQLite is embedded and created automatically.

---

## 1. Project layout (what runs where)

```
career-compass/
├── backend/     ← FastAPI API            → http://localhost:8000
├── frontend/    ← React dev server (Vite) → http://localhost:5173
└── legacy/      ← original Streamlit app  → http://localhost:8501 (optional)
```

You will run the backend and frontend in **two separate terminals** (both must be running).

---

## 2. Backend — FastAPI

Open a terminal:

```powershell
cd C:\Users\HP\Documents\career-compass\backend
```

### 2.1 Create the virtual environment

```powershell
python -m venv .venv
```

### 2.2 Activate it

**PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**cmd.exe**
```bat
.venv\Scripts\activate.bat
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

> If PowerShell blocks the script ("running scripts is disabled"), allow it for this terminal only:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\.venv\Scripts\Activate.ps1
> ```
> Or skip activation entirely and prefix commands with `.\.venv\Scripts\python.exe` (see §2.6).

### 2.3 Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2.4 Create the environment file

```powershell
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env
```

Open `backend/.env` and set:

```env
# Optional — leave blank to run without AI
GEMINI_API_KEY=your_free_gemini_key

# REQUIRED — the API refuses to start without it (min 32 chars)
JWT_SECRET=
ACCESS_TOKEN_EXPIRE_MINUTES=10080
CORS_ORIGINS=http://localhost:5173
```

- `JWT_SECRET` is **required** — there is deliberately no fallback. Generate one:
  ```powershell
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
  The API exits at startup with a clear message if this is missing, shorter than 32
  characters, or a known placeholder.
- Get a free key at **<https://aistudio.google.com>** → *Get API Key*.
- `GEMINI_API_KEY` is **optional** — without it everything works except AI roadmap
  generation and the copilot, which return a friendly "AI not configured" message.

### 2.5 Run the API

> Must be run from inside `backend/` (the app imports top-level packages `app/`, `services/`, `database/`).

```powershell
python -m uvicorn app.main:app --reload
```

Useful options: `--port 8001` (if 8000 is taken), `--host 0.0.0.0` (expose on your network).
Drop `--reload` for a stable run.

### 2.6 Run without activating (works in any shell)

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### 2.7 Verify

- Health check → <http://127.0.0.1:8000/health>  (expect `{"status":"ok",...}`)
- Interactive API docs → <http://127.0.0.1:8000/docs>
- Live job search (after §2.9) → <http://127.0.0.1:8000/jobs/search?q=kubernetes+platform+engineer>

Leave this terminal running.

### 2.8 Build the semantic role index (one-off, optional)

Matching has two stages: candidate roles are **recalled** from a Qdrant vector
index, then **scored and explained** by the same transparent 65/35 formula as
before. Recall adds roles that match the *meaning* of your profile (interests,
skills and free-text goal) even when no interest chip overlaps.

The index is a derived artifact, so it is built by an explicit migration — never
at startup, and it is not in git:

```powershell
# With the API stopped (embedded Qdrant locks its directory)
.\.venv\Scripts\python.exe -m scripts.ingest_roles --query "cloud infrastructure pipelines"
```

Re-run it whenever `data/roles.json` changes; add `--rebuild` to drop the old
collection first. Until then, matching is keyword-only, exactly as before —
nothing breaks.

Embeddings come from Gemini when `GEMINI_API_KEY` is set, otherwise from a
deterministic offline embedder (no key, no network, no model download). If Gemini
is configured but unusable — quota exhausted, model retired, offline — the script
says so and builds the offline index instead. Either way the provider that built
the index is recorded beside it, so the API always queries the right collection.
See §8 for what to do if you change keys or models later.

### 2.9 Collect live job postings into `job_role` (optional)

A second collection holds real, currently-open postings rather than curated roles.
It is collected from free public job-board APIs (Himalayas and Arbeitnow) — no key
and no sign-up — normalised, de-duplicated by title and company, and embedded with
the same embedder as the catalog:

```powershell
# With the API stopped, exactly like 2.8
.\.venv\Scripts\python.exe -m scripts.ingest_jobs --limit 1000 --query "kubernetes platform engineer"
```

It fetches politely (descriptive `User-Agent`, a pause between pages, a page
ceiling per board) and writes what it collected to `data/job_postings.json`
(git-ignored). Re-ingest from that file with no network at all:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_jobs --from-file data\job_postings.json
```

`job_role` is a plain, human-chosen name, so the embedding space it holds is
recorded in `<index>/job_role.space`. Ingesting from a *different* space (say you
add a Gemini key after building offline) is refused instead of mixing
incomparable vectors — re-run with `--rebuild` to replace it. Rebuilding this
collection never touches the catalog index, and vice versa.

`GET /jobs/search?q=…` serves these postings (public, like `/roles`): semantic search over the
collection, returning each listing with its salary text, publication date and the board's own URL.
Until §2.9 has been run the endpoint still answers `200` with `available: false` and no rows, so a
client can hide the section instead of surfacing an error — nothing else in the app depends on it.

The React **Jobs** page (§3.4) is the front end for this endpoint, and every match card deep-links
into it with its role prefilled.

---

## 3. Frontend — React (Vite)

Open a **second** terminal:

```powershell
cd C:\Users\HP\Documents\career-compass\frontend
```

### 3.1 Install dependencies

```powershell
npm install
```

### 3.2 Create the environment file

```powershell
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env
```

`frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

> This must match where the backend is running. If you moved the backend to port `8001`,
> update this too.

### 3.3 Run the dev server

```powershell
npm run dev
```

### 3.4 Verify

Open <http://localhost:5173>. You should see the CareerCompass home page.
Then try **All Roles** — if the full 100-role catalog loads, the frontend is talking to the backend.

Then open **💼 Jobs** in the navigation. Type a role (e.g. `kubernetes engineer`) and press
**Search jobs**: you should get live postings. Add a location or pick an experience level and the
list narrows while the page still reports how many postings the index ranked. If §2.9 has not been
run, the page shows a note telling you to run the migration instead of an error — that is expected.

The same page is reachable from any match card: open **My Matches** and press **💼 Explore Jobs** on
a card. The role is filled into the search box and the results load immediately.

Leave this terminal running.

---

## 4. You're up 🎉

| Service | URL |
|---|---|
| Frontend (UI) | <http://localhost:5173> |
| Backend (API) | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

**First run checklist:** build a profile → see matches → open a role → generate a roadmap →
open the study tracker → chat with the copilot.

Run the one-off migration in §2.8 too if you want matches recalled by meaning
(it needs the API stopped, so it is easiest before you start the servers).

---

## 5. Optional — Legacy Streamlit app

```powershell
cd ..\legacy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py            # http://localhost:8501
```

---

## 6. Every day after the first setup (quick reference)

**Terminal 1 — backend**
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

**Terminal 2 — frontend**
```powershell
cd frontend
npm run dev
```

---

## 7. Production build (frontend)

```powershell
cd frontend
npm run build        # type-checks, then outputs static files to frontend/dist/
npm run preview      # serve the built app locally to sanity-check it
```

Serve `frontend/dist/` from any static host (Netlify, Vercel, Nginx…). Point
`VITE_API_BASE_URL` at your deployed API **before** building, and add that site's origin to the
backend's `CORS_ORIGINS`.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `python: command not found` | Install Python 3.11+ and ensure "Add python.exe to PATH" was checked. Try the `py` launcher: `py -m venv .venv`. |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, or use `.\.venv\Scripts\python.exe` directly. |
| `[Errno 10048] address already in use` (port 8000) | Another server is running. Stop it, or run with `--port 8001` **and** update `VITE_API_BASE_URL`. |
| `npm run dev` says port 5173 in use | Stop the other Vite instance. The dev server is configured with `strictPort`, so it won't silently pick another port. |
| Browser console: **CORS policy** error | Ensure `backend/.env` has `CORS_ORIGINS=http://localhost:5173` (exact origin, no trailing slash) and restart the backend. |
| Frontend loads but no roles appear | Backend isn't running, or `VITE_API_BASE_URL` is wrong. Check <http://127.0.0.1:8000/health>. |
| Roadmap/Copilot: "AI is not configured" | Set `GEMINI_API_KEY` in `backend/.env` and restart the backend. |
| Roadmap/Copilot: "took too long to respond" | The request to Gemini timed out (slow/offline connection). Check your network and try again. |
| Want a clean database | Stop the backend, delete `backend/data/career_compass.db`, restart — it is recreated and the role catalog is loaded from `roles.json` again. |
| Existing database after an upgrade | Nothing to do. On startup `init_db()` appends any columns added since your database was created, refreshes the role catalog from `roles.json` in place, and keeps every existing row — user profiles, roadmaps and tracker progress included. |
| Roles are missing after editing `roles.json` | Restart the backend. The catalog is read at startup, and roles are never deleted from the database (so saved roadmaps can't be orphaned), which also means removing a role from the JSON leaves its old row in place. |
| A role shows the **generic** stack (Python / Java / TypeScript / Go / C++) | `data/stacks.json` is read once at import, so the running process still has the old copy. Restart the backend. If you edited the file while `--reload` was running, make sure the old server actually exited — a lingering reload worker keeps port 8000 and keeps serving the old content. |
| Migration says the index is **locked** / "another process … is holding it open" | Embedded Qdrant allows one process at a time. Stop the API server (and any stray `python -m uvicorn` process) and re-run. Or set `QDRANT_URL` to a Qdrant server, which needs no lock. |
| `/health` shows `semantic_index.points: 0`, or `other_collections` is listed | You are querying a different embedding space than the one that was ingested — usually because a `GEMINI_API_KEY` was added/removed, or `GEMINI_EMBEDDING_MODEL` changed, after the migration. Re-run §2.8 (with `--rebuild`), or pin `EMBEDDING_PROVIDER` to the space you want. |
| Migration prints "Gemini embeddings unavailable … falling back" | Gemini is configured but unreachable (quota, retired model, offline). The offline index is built instead and recorded, so matching still works. Fix the key/quota and re-run §2.8 with `--rebuild` to switch to Gemini vectors. |
| Matches look keyword-only after an upgrade | Expected until §2.8 runs. Without an index the matcher behaves exactly as before; `recalled_by` on every result says how it was found. |
| `scripts.ingest_jobs` refuses: "was built in embedding space … but the active embeddings are …" | `job_role` already holds vectors from another space (usually you added a `GEMINI_API_KEY` after building offline). Re-run with `--rebuild` to replace the collection, or pin `EMBEDDING_PROVIDER` to the space it holds. |
| `scripts.ingest_jobs` reports no postings / a board was skipped | A job board was unreachable or returned nothing; the other board was still used. Re-run later, or ingest the saved `data/job_postings.json` with `--from-file`. |
| `GET /jobs/search` returns `available: false` and no rows | The `job_role` collection has not been built yet. Run §2.9 (or `--from-file data\job_postings.json` if you already collected once). The endpoint answers honestly rather than erroring — nothing else depends on it. |
| `FutureWarning` about `google.generativeai` | Harmless; the SDK is deprecated and migration is planned. |

---

## 9. Running the tests

**Backend** (standard-library `unittest`, no extra deps):
```powershell
cd backend
python -m unittest discover -s tests -t . -v
```

`tests/harness.py` redirects the app to a throwaway SQLite database in a temp directory,
so the suite never reads or writes `backend/data/career_compass.db`. `test_api.py` covers
the endpoint contracts (and per-user ownership); `test_e2e_journey.py` walks the full
candidate journey end to end. An individual file also runs directly, e.g.
`python tests/test_e2e_journey.py`.

The semantic-index tests are hermetic too: the harness forces the offline embedder
(`EMBEDDING_PROVIDER=local`) and points `QDRANT_PATH` at a temporary directory, so no test ever
calls Gemini or touches your real `backend/data/qdrant/` index. The live job-feed tests
(`test_job_feed.py`) replace the single function that touches the network, so no test reaches a job
board either; `test_job_api.py` covers the `/jobs/search` read path against a throwaway index.

**Frontend** (TypeScript check + production build):
```powershell
cd frontend
npm run typecheck
npm run build
```

CI runs both on every push — see `.github/workflows/ci.yml`.
