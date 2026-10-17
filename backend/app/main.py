"""CareerCompass FastAPI application entrypoint.

Run from the backend/ directory:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_TITLE, API_VERSION, CORS_ORIGINS
from app.routers import applications, auth, chat, jobs, match, profile, roadmap, roles, tracker
from database.db import init_db
from services import job_service, vector_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(roles.router)
app.include_router(jobs.router)
app.include_router(profile.router)
app.include_router(match.router)
app.include_router(roadmap.router)
app.include_router(tracker.router)
app.include_router(applications.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health():
    try:
        semantic = vector_store.index_status()
    except Exception as exc:  # never let diagnostics break liveness
        semantic = {"available": False, "error": str(exc)}
    # Reported here as well as on `/jobs/search` so an uptime monitor can see a
    # feed going stale without running a search — the other half of scheduling a
    # re-ingest is being able to tell that it is due.
    jobs = {}
    try:
        jobs = job_service.freshness()
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        jobs = {"error": str(exc)}
    return {
        "status": "ok",
        "service": API_TITLE,
        "version": API_VERSION,
        "semantic_index": semantic,
        "job_postings": jobs,
    }
