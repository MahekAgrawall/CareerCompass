"""Pydantic request/response models for the API."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MeResponse(BaseModel):
    id: int
    name: str
    email: str
    profile: Dict[str, Any] = {}


# ── Profile ───────────────────────────────────────────────────────────────────
class ProfileIn(BaseModel):
    name: str = ""
    grad_year: str = ""
    experience: str = ""
    location: str = ""
    work_mode: str = ""
    open_to_relocate: str = ""
    career_goal: str = ""
    current_skills: List[str] = []
    interests: List[str] = []


# ── Matching ──────────────────────────────────────────────────────────────────
class MatchRequest(BaseModel):
    interests: List[str] = []
    current_skills: List[str] = []
    explain: bool = True
    # Extra context for the semantic recall stage only — it never enters the
    # score. A free-text goal is the strongest signal the index gets.
    career_goal: str = ""
    experience: str = ""
    work_mode: str = ""


class MatchResult(BaseModel):
    role: Dict[str, Any]
    score: int
    # Component scores (0-100) — the exact figures `score` is computed from.
    interest_score: int
    skill_score: int
    matched_interests: List[str]
    matched_skills: List[str]
    # Profile chips that would raise the skill half of this match.
    suggested_skills: List[str]
    # How the role was found: "keyword" (interest chips), "semantic" (vector
    # search over the catalog), or both.
    recalled_by: List[str] = []
    # Cosine similarity from the semantic index, when it contributed.
    semantic_similarity: Optional[float] = None


class MatchResponse(BaseModel):
    results: List[MatchResult]
    explanation: str = ""
    # Weights behind `score`, published so clients explain the same maths.
    interest_weight: int
    skill_weight: int


# ── Roadmap ───────────────────────────────────────────────────────────────────
class RoadmapRequest(BaseModel):
    role_id: str
    profile: Dict[str, Any] = {}


# ── Tracker ───────────────────────────────────────────────────────────────────
class ScheduleIn(BaseModel):
    role_id: str
    weekday_hours: float = 1.5
    weekend_hours: float = 4.0
    target_languages: List[str] = []


class TopicToggle(BaseModel):
    is_completed: bool


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    role_id: str
    roadmap: Dict[str, Any] = {}
    new_message: str
    history: List[Dict[str, str]] = []
    profile: Dict[str, Any] = {}


# ── Live job postings ─────────────────────────────────────────────────────────
class JobPosting(BaseModel):
    id: str
    title: str
    company: str = ""
    location: str = ""
    remote: bool = False
    employment_type: str = ""
    seniority: List[str] = []
    categories: List[str] = []
    # Rendered by the ingest from whatever the board published ("EUR 80000-100000
    # / annual"), or "" when the board disclosed nothing.
    salary_text: str = ""
    published: str = ""
    url: str
    source: str = ""
    excerpt: str = ""
    # Cosine similarity from the job index — the only ranking signal here, since
    # these are live listings rather than catalogued roles with a fit score.
    similarity: float


class JobSearchResponse(BaseModel):
    query: str
    # False when the `job_role` index has not been built (scripts.ingest_jobs).
    # The endpoint still answers 200 — it simply has nothing to search — so a
    # client can hide the section instead of showing an error.
    available: bool
    count: int
    results: List[JobPosting]
