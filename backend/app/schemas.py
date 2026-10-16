"""Pydantic request/response models for the API."""
from typing import Any, Dict, List

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


class MatchResult(BaseModel):
    role: Dict[str, Any]
    score: int
    matched_interests: List[str]
    matched_skills: List[str]


class MatchResponse(BaseModel):
    results: List[MatchResult]
    explanation: str = ""


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
