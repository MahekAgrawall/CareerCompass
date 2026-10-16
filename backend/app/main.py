"""CareerCompass FastAPI application entrypoint.

Run from the backend/ directory:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_TITLE, API_VERSION, CORS_ORIGINS
from app.routers import auth, chat, match, profile, roadmap, roles, tracker
from database.db import init_db


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
app.include_router(profile.router)
app.include_router(match.router)
app.include_router(roadmap.router)
app.include_router(tracker.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": API_TITLE, "version": API_VERSION}
