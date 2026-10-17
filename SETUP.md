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
# Optional — pin the model (default is the floating "latest" alias)
# GEMINI_MODEL=gemini-flash-lite-latest
# Optional — AI calls allowed per caller per rolling window
# AI_RATE_LIMIT=15
# AI_RATE_WINDOW_SECONDS=60

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
- The AI endpoints (roadmap, copilot, match explanation) are metered **per caller** —
  by user id when signed in, otherwise by client address — because this app lets
  guests use the AI without an account. Over budget is a **429** with a `Retry-After`;
  `/match` never fails on it, it just drops its written assessment, because the ranked
  matches need no AI. Raise `AI_RATE_LIMIT` if you are demoing heavily from one machine.

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
- Live job search with the filters, and no search text at all (after §2.9) →
  <http://127.0.0.1:8000/jobs/search?location=berlin&remote=true&experience=senior>
  (expect `count <= limit`, and `matched` / `indexed` describing the whole collection)
- Per-role openings (after §2.9) — POST, because the profile travels in the body:

  ```powershell
  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/jobs/for-role `
    -ContentType application/json `
    -Body '{"role_id":"platform_engineer","limit":3,"profile":{}}'
  ```

Leave this terminal running.

### 2.8 Build the semantic role index (one-off, optional)

Matching has two stages: candidate roles are **recalled** from a Qdrant vector
index, then **scored and explained** by the same transparent 65/35 formula as
before. Recall adds roles that match the *meaning* of your profile (interests,
skills, free-text goal, experience, preferred work setup and work hub) even when
no interest chip overlaps.

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
It also takes `location`, `remote` (`true`/`false`) and `experience` (`internship`/`entry`/`senior`),
which the backend applies to the whole collection in the vector store — so the response reports
`count` (this page), `matched` (what the filters leave collection-wide) and `indexed` (the collection
size). `q` ranks the results and is optional when a filter is given; asking for nothing at all is a
`400`. Until §2.9 has been run the endpoint still answers `200` with `available: false` and no rows, so
a client can hide the section instead of surfacing an error — nothing else in the app depends on it.

The same migration creates the payload indexes those filters read. The embedded store ignores payload
indexes and works regardless, but a deployment pointing `QDRANT_URL` at a Qdrant server needs the text
indexes before Qdrant will accept a full-text filter — so re-run §2.9 once after upgrading.

The React **Jobs** page (§3.4) is the front end for this endpoint, and every match card deep-links
into it with its role prefilled.

`POST /jobs/for-role` is the same collection read for one catalogued role: it ranks the postings
against that role's index document plus the candidate's questionnaire answers, so the ranking is
personalised. It fills the **live openings** list on each role card and on the role page. An empty
`profile` is fine — the search then degrades to the role itself.

**Freshness.** The feed records when it was harvested. The artifact carries a `harvested_at` stamp
(`{"harvested_at", "postings"}` — an older bare-list file still loads, with no date), and the ingest
writes that date plus its own into `<index>/job_role.meta.json`. `GET /jobs/search` reports both in a
`freshness` block (`harvested_at`, `ingested_at`, `age_days`, `stale`, `stale_after_days` = 14), and
`/health` reports the same under `job_postings`, so a monitor can alert on a stale feed without
running a search. The Jobs page shows "Harvested on … (N days ago)" under every set of results, and
an amber warning once the feed is past two weeks. A `--from-file` re-ingest reports the *artifact's*
date rather than the day it ran, so re-loading old data cannot age it up to today. On a `QDRANT_URL`
deployment the sidecar is written next to the ingest; a server that shares no volume with it reports
the date as "not recorded" instead of guessing.

**Re-ingest on a schedule.** `--if-stale DAYS` does nothing at all when the current harvest is
younger than `DAYS`, which is what makes a frequent schedule cheap: point a scheduler at it and the
run is a no-op until the feed is really getting old.

```powershell
# Hourly, but only actually harvests once the feed is 3 days old or more
.\.venv\Scripts\python.exe -m scripts.ingest_jobs --limit 1000 --if-stale 3
```

Which schedule is possible depends on the store:

* **Embedded Qdrant (the default)** — the index directory is locked by whichever process has it
  open, so a harvest cannot run while the API is serving. Schedule it for a window with the server
  stopped (a nightly maintenance slot is the usual answer); the API reports the new date as soon as
  it is back up.
* **`QDRANT_URL` set** — the store is a separate server, the lock is not a factor, and the harvest
  can run on its own schedule. Both examples below assume this.

```bash
# cron: hourly, and the command itself decides whether there is work to do
0 * * * * cd /srv/career-compass/backend && .venv/bin/python -m scripts.ingest_jobs --limit 1000 --if-stale 3 >> /var/log/careercompass-harvest.log 2>&1
```

```powershell
# Windows Task Scheduler: one hourly trigger
schtasks /create /tn "CareerCompass harvest" /sc HOURLY /mo 1 /f /tr "cmd /c cd /d C:\path\to\career-compass\backend && .venv\Scripts\python.exe -m scripts.ingest_jobs --limit 1000 --if-stale 3"
```

`--rebuild` overrides `--if-stale`, and a run with no recorded date yet (the first one) always does
the work. To see what a schedule actually did, read the freshness rather than the log:
<http://127.0.0.1:8000/health> → `job_postings`.

---

### 2.10 Measure how good the role recall actually is (optional)

`backend/evals/` carries a labelled set of questionnaire profiles with the role(s) each one means,
plus the harness that runs them through the real recall path and prints what the current index and
similarity floor do with them:

```powershell
cd backend
.\.venv\Scripts\python.exe -m evals.retrieval_eval --provider both
```

It builds its **own** throwaway index and database in a temporary directory, so it neither touches
`data/career_compass.db` nor contends for the lock the running API holds on `data/qdrant` — it is
safe to run with the server up. `--provider both` measures the offline embedder and Gemini side by
side (same labels, same documents, same scorer); a full run costs ~135 embed items, more than a
free-tier key serves in a minute, so the harness waits out a rate limit and retries rather than
failing two thirds of the way through (`--pace 0` to turn that waiting off). The free tier's *daily*
budget is 1,000 embed items for this model — about seven full comparison runs — and once it is gone
the harness says so and reports whichever provider did run instead of inventing a number.
`--json` prints the whole report for scripting, and `--index-dir <dir>` measures an existing index
instead of building a temporary one (stop the API first — embedded Qdrant locks its directory). The
numbers it produces for this repository are in the README's *"Does the index find the right role?"*
section.

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

Then open **Jobs** in the navigation. Type a role (e.g. `kubernetes engineer`) and press
**Search jobs**: you should get live postings. Add a location or pick an experience level and the
list narrows while the page still reports how many postings the collection holds. If §2.9 has not been
run, the page shows a note telling you to run the migration instead of an error — that is expected.

With an account, each posting also offers **🔖 Save job**. Save one, open **Applications** in the
navigation, and you should see it under **Saved**; move it to **Interview** with the stage selector and
it moves section, with the counts at the top following it. Signed out, the same button reads
**🔑 Sign in to save** — saved jobs are per-account, so that page requires a session.

The same page is reachable from any match card: open **My Matches** and press **💼 Explore Jobs** on
a card. The role is filled into the search box and the results load immediately.

With a profile saved, press **✨ Use my profile** on the Jobs page (or the button on the empty state):
the search runs off your questionnaire answers — interests, current skills and the stated goal — instead
of a typed role.

Now check the per-role job links and the roadmap copilot:

- On **All Roles** (or **My Matches**), open a card's **💼 Live openings from the job boards** section.
  It fetches on open (the section is collapsed by default, so the directory does not fire one request
  per card) and lists a handful of real postings, each linking out to the board that published it.
- Open the same role's page — the **💼 Live Openings from the Job Boards** section is there in full.
- On any role card press **🗺️ Generate AI Roadmap**. It lands on the role's roadmap page, which
  generates the plan and now hosts the **Roadmap Copilot** on the *same page*, below the plan: ask it a
  question and the answer streams in without leaving the roadmap.
- The copilot thread is **remembered for the tab**: ask something, navigate to **All Roles** and back
  (or open `/chat/<role>`), and the conversation is still there. *Clear Conversation* and closing the
  tab both drop it.
- Sign in and generate a plan, then **close the tab and open the role again** in a new session: the plan
  is fetched from **🗺️ Roadmaps** (your saved library) instead of being generated — and your saved
  library shows the model and prompt fingerprint that produced each one, e.g.
  `gemini-flash-lite-latest · prompt edc3becb7cc3`.

**Preferred Work Hub** also lists international hubs now (London, Berlin, Amsterdam, Zurich, Dubai,
Singapore, Toronto, New York, the Bay Area, Sydney…), not just the Indian ones — the live boards skew
European and North-American, so a candidate aiming there can say so. The hub feeds the semantic recall
stage of matching and the query behind each role's live openings; it is never used to filter the
curated catalog.

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
| Roadmap/Copilot: "a lot of AI requests in a short time" (429) | The per-caller AI budget is spent (`AI_RATE_LIMIT` per `AI_RATE_WINDOW_SECONDS`). Wait for the `Retry-After`, or raise the limit in `backend/.env` and restart. Matches still load — only the AI half is gated. |
| Want a clean database | Stop the backend, delete `backend/data/career_compass.db`, restart — it is recreated and the role catalog is loaded from `roles.json` again. |
| Existing database after an upgrade | Nothing to do. On startup `init_db()` creates any table added since your database was created (the saved-jobs table for application tracking, for instance) and appends any columns added since, refreshes the role catalog from `roles.json` in place, and keeps every existing row — user profiles, roadmaps and tracker progress included. |
| Roles are missing after editing `roles.json` | Restart the backend. The catalog is read at startup, and roles are never deleted from the database (so saved roadmaps can't be orphaned), which also means removing a role from the JSON leaves its old row in place. |
| A role shows the **generic** stack (Python / Java / TypeScript / Go / C++) | `data/stacks.json` is read once at import, so the running process still has the old copy. Restart the backend. If you edited the file while `--reload` was running, make sure the old server actually exited — a lingering reload worker keeps port 8000 and keeps serving the old content. |
| Migration says the index is **locked** / "another process … is holding it open" | Embedded Qdrant allows one process at a time. Stop the API server (and any stray `python -m uvicorn` process) and re-run. Or set `QDRANT_URL` to a Qdrant server, which needs no lock. |
| `/health` shows `semantic_index.points: 0`, or `other_collections` is listed | You are querying a different embedding space than the one that was ingested — usually because a `GEMINI_API_KEY` was added/removed, or `GEMINI_EMBEDDING_MODEL` changed, after the migration. Re-run §2.8 (with `--rebuild`), or pin `EMBEDDING_PROVIDER` to the space you want. |
| Migration prints "Gemini embeddings unavailable … falling back" | Gemini is configured but unreachable (quota, retired model, offline). The offline index is built instead and recorded, so matching still works. Fix the key/quota and re-run §2.8 with `--rebuild` to switch to Gemini vectors. |
| Matches look keyword-only after an upgrade | Expected until §2.8 runs. Without an index the matcher behaves exactly as before; `recalled_by` on every result says how it was found. |
| `scripts.ingest_jobs` refuses: "was built in embedding space … but the active embeddings are …" | `job_role` already holds vectors from another space (usually you added a `GEMINI_API_KEY` after building offline). Re-run with `--rebuild` to replace the collection, or pin `EMBEDDING_PROVIDER` to the space it holds. |
| `scripts.ingest_jobs` reports no postings / a board was skipped | A job board was unreachable or returned nothing; the other board was still used. Re-run later, or ingest the saved `data/job_postings.json` with `--from-file`. |
| `GET /jobs/search` returns `available: false` and no rows | The `job_role` collection has not been built yet. Run §2.9 (or `--from-file data\job_postings.json` if you already collected once). The endpoint answers honestly rather than erroring — nothing else depends on it. |
| `/jobs/search` with a filter returns nothing, and the log says "Text index required" | Only affects `QDRANT_URL` deployments: a Qdrant server refuses a full-text filter unless the field has a text index, and this collection was ingested before the filters existed. Re-run §2.9 — it creates the payload indexes. The embedded store ignores payload indexes, so a default setup is never affected. |
| The Jobs page says the postings are **getting old** | The feed has not been re-harvested since the date shown. Re-run §2.9 (which records a new harvest date), or wire up the schedule there. Nothing is broken: the page is saying the data is old rather than implying it is current. |
| `/jobs/search` reports `harvested_at: ""` | Nothing recorded a harvest date for this index — it was built before freshness existed, or the sidecar is missing (with `QDRANT_URL` set it is written next to the *ingest*, not next to the API). Re-run §2.9 on the ingest host to record one; the feed otherwise works normally. |
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
board either; `test_job_api.py` covers the `/jobs/search` and `/jobs/for-role` read paths against a
throwaway index, including the payload filters and the honest counts (`count` vs `matched` vs
`indexed`), and `test_job_freshness.py` covers the harvest provenance — the stamp on the artifact,
the sidecar the ingest writes, the age the API reports (including "not recorded" when there is
none), and that `--if-stale` skips without touching the collection. `test_applications.py` covers
saved jobs end to end — auth, idempotent saving,
ownership, the stage vocabulary and the snapshot round-trip. `test_prompts.py` checks the prompt
library: every template the AI calls need exists
on disk, renders without a leftover placeholder, reaches the model as the same text the inline prompt
used to, and survives a crafted answer that tries to open its own `Guidelines:` block
(`google-generativeai` itself is mocked — no network). `test_rate_limit.py` covers the AI budget:
the sliding window in isolation, then the endpoint behaviour — a `429` with `Retry-After` from the
copilot and roadmap, and a `/match` that still returns its ranked answer without the AI explanation.
`test_retrieval_eval.py` guards the retrieval *evaluation* rather than a score: the labelled set must
be well formed and realistic (every expected role exists in the catalogue, every interest and skill
is a real questionnaire option, and at least eight labels stay reachable only by meaning, so the
harness cannot quietly stop exercising the semantic path), the metric arithmetic is checked against
ranked lists whose answer is known by hand, and an index that answers nothing at all is reported as a
broken measurement instead of a fake recall figure. The harness's own numbers are not asserted
anywhere, because they depend on the provider and the network — those come from §2.10, by hand.

**Frontend** (TypeScript check + production build):
```powershell
cd frontend
npm run typecheck
npm run build
```

CI runs both on every push — see `.github/workflows/ci.yml`.
