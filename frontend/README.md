# CareerCompass — Frontend

React + TypeScript single-page app for the CareerCompass API, built with Vite, Tailwind CSS,
React Router and TanStack Query.

## Quick start

```bash
npm install
cp .env.example .env        # VITE_API_BASE_URL (defaults to http://localhost:8000)
npm run dev                 # http://localhost:5173
```

The FastAPI backend must be running (see `../backend`) with `http://localhost:5173` in `CORS_ORIGINS`.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server with HMR on port 5173 |
| `npm run typecheck` | TypeScript project check (`tsc --noEmit`) |
| `npm run build` | Type-check + production build to `dist/` |
| `npm run preview` | Preview the production build |

## Structure

```
src/
├── api/           fetch client (JWT, errors, streaming, timeouts), typed endpoints, API types
├── components/    Navbar, Layout, RoleCard, Badge, Alert, ChipSelect, ProgressBar, …
├── pages/         home · auth · profile · matches · directory · role detail
│                  compare · roadmap · roadmaps · tracker · chat
├── state/         AuthContext (sessionStorage JWT) · Profile · Compare · Roadmap caches
├── lib/           option vocabularies, formatting, Markdown export, hooks
└── index.css      Tailwind entry + design-system component classes
```

## Notes

- **Session-scoped auth** — the JWT lives in `sessionStorage`, so closing the tab signs you out.
- **Deep links** — views are real routes (e.g. `/tracker/backend_dev`) and are shareable.
- **Progressive AI** — the match grid renders from the deterministic engine immediately; the
  AI-written assessment loads separately so a slow model never blocks results.
- **Resilient AI calls** — roadmap generation and chat streaming use client-side timeouts so they
  fail with a clear message instead of spinning forever.
