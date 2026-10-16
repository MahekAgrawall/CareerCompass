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
GEMINI_API_KEY=your_free_gemini_key
JWT_SECRET=some_long_random_string
ACCESS_TOKEN_EXPIRE_MINUTES=10080
CORS_ORIGINS=http://localhost:5173
```

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

Leave this terminal running.

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
Then try **All Roles** — if 15 roles load, the frontend is talking to the backend.

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
| Want a clean database | Stop the backend, delete `backend/data/career_compass.db`, restart — it is recreated and reseeded. |
| `FutureWarning` about `google.generativeai` | Harmless; the SDK is deprecated and migration is planned. |

---

## 9. Running the tests

**Backend** (standard-library `unittest`, no extra deps):
```powershell
cd backend
python -m unittest discover -s tests -t . -v
```

**Frontend** (TypeScript check + production build):
```powershell
cd frontend
npm run typecheck
npm run build
```

CI runs both on every push — see `.github/workflows/ci.yml`.
