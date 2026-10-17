"""Pydantic request/response models for the API."""
from typing import Any, Dict, List, Literal, Optional

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
    # score. A free-text goal is the strongest signal the index gets; the work hub
    # matters because the live boards are location-bound even though the curated
    # roles are not.
    career_goal: str = ""
    experience: str = ""
    work_mode: str = ""
    location: str = ""


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
    # Bounded on the way in: the message and the replayed history both end up in a
    # paid model call, so a client cannot push an unbounded payload at it.
    new_message: str = Field(min_length=1, max_length=4000)
    history: List[Dict[str, str]] = Field(default_factory=list, max_length=40)
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


class HarvestFreshness(BaseModel):
    """When the live postings were pulled, and whether that is getting old.

    Recorded by `scripts.ingest_jobs` beside the collection, never derived from
    the postings themselves: a board keeps serving a listing after the job is
    filled, so the boards' publication dates say when a job was posted — never
    when CareerCompass last looked at it.

    Empty strings mean "not recorded", which is the honest answer on a
    `QDRANT_URL` deployment, whose sidecar is written next to the ingest rather
    than next to the API. `age_days` and `stale` are the backend's own reading of
    that date so no client has to re-implement the threshold.
    """

    #: UTC ISO 8601, e.g. "2026-10-18T09:14:02+00:00", or "" when unrecorded.
    harvested_at: str = ""
    #: When that harvest was loaded into the index. Informational: a re-ingest of
    #: an old artifact moves this and leaves `harvested_at` alone.
    ingested_at: str = ""
    #: Whole days since the harvest, or None when there is no usable date.
    age_days: Optional[int] = None
    #: True once the harvest is at least `stale_after_days` old.
    stale: bool = False
    #: The threshold `stale` was decided with, so a client can word the warning
    #: ("older than two weeks") without hard-coding the number.
    stale_after_days: int = 14


class JobSearchResponse(BaseModel):
    #: The text the ranking actually ran on: the caller's query, or their filter
    #: terms when they typed none.
    query: str
    # False when the `job_role` index has not been built (scripts.ingest_jobs).
    # The endpoint still answers 200 — it simply has nothing to search — so a
    # client can hide the section instead of showing an error.
    available: bool
    # How many postings this page returned (never more than `limit`).
    count: int
    # How many postings the filters leave in the whole collection. Counted in the
    # vector store, so it is a real total rather than a property of this page.
    matched: int
    # How many postings the collection holds, filters or no filters.
    indexed: int
    # When this data was harvested, and whether that is old enough to warn about.
    freshness: HarvestFreshness
    results: List[JobPosting]


class RoleJobsRequest(BaseModel):
    """Postings for one catalogued role, personalised by the questionnaire."""

    role_id: str = Field(min_length=1)
    # A handful per role card is plenty; the endpoint is called once per role the
    # candidate opens, not once for the whole page.
    limit: int = Field(5, ge=1, le=50)
    # The candidate's answers (interests, skills, goal, location, …). Optional:
    # without them this degrades to a plain search for the role itself.
    profile: Dict[str, Any] = {}


class RoleJobsResponse(BaseModel):
    role_id: str
    role_title: str
    available: bool
    count: int
    results: List[JobPosting]


# ── Saved jobs & application tracking ─────────────────────────────────────────
#: Mirrors `services.application_service.STATUSES`; a test keeps the two in step.
ApplicationStatus = Literal["saved", "applied", "interview", "offer", "rejected"]


class ApplicationCreate(BaseModel):
    """A live posting, snapshotted at the moment the candidate saves it.

    The client sends the whole posting rather than just its id, deliberately: the
    boards rotate and the `job_role` index is rebuilt, so the saved row has to
    stand on its own. Each value is capped at what a board can actually publish,
    so the endpoint cannot be used as arbitrary storage.
    """

    posting_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    company: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    remote: bool = False
    employment_type: str = Field("", max_length=100)
    salary_text: str = Field("", max_length=200)
    published: str = Field("", max_length=40)
    url: str = Field("", max_length=1000)
    source: str = Field("", max_length=60)
    # Recording a posting the candidate has *already* applied to is a real flow —
    # they met the listing on the board, then filed it here — so the stage can be
    # set on the way in. It only applies to a new row: re-saving never moves one.
    status: ApplicationStatus = "saved"
    note: str = Field("", max_length=1000)


class ApplicationUpdate(BaseModel):
    """A stage change, a note edit, or both. At least one field is required."""

    status: Optional[ApplicationStatus] = None
    note: Optional[str] = Field(None, max_length=1000)


class SavedJob(BaseModel):
    """One saved posting: the snapshot a candidate filed, plus where it got to."""

    id: int
    posting_id: str
    title: str
    company: str = ""
    location: str = ""
    remote: bool = False
    employment_type: str = ""
    salary_text: str = ""
    published: str = ""
    url: str = ""
    source: str = ""
    status: ApplicationStatus
    note: str = ""
    #: When it was filed, and when it was last moved or edited.
    created_at: str
    updated_at: str


class ApplicationListResponse(BaseModel):
    count: int
    results: List[SavedJob]
