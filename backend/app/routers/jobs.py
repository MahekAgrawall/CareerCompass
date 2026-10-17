"""Live job-posting endpoints.

Public and read-only, like `/roles`: the postings come from public job boards and
carry no user data. The `job_role` collection behind them is filled explicitly by
`python -m scripts.ingest_jobs`, so these endpoints are also honest about having
no data yet — see `schemas.JobSearchResponse.available`.
"""
from fastapi import APIRouter, Query

from app import schemas
from services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/search", response_model=schemas.JobSearchResponse)
def search_jobs(
    q: str = Query(min_length=1, max_length=200, description="What to look for"),
    limit: int = Query(job_service.DEFAULT_LIMIT, ge=1, le=job_service.MAX_LIMIT),
):
    """Semantic search over the live postings collected into `job_role`."""
    return job_service.search_postings(q, limit=limit)
