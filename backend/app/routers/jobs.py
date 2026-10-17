"""Live job-posting endpoints.

Public and read-only, like `/roles`: the postings come from public job boards and
carry no user data. The `job_role` collection behind them is filled explicitly by
`python -m scripts.ingest_jobs`, so these endpoints are also honest about having
no data yet — see `schemas.JobSearchResponse.available`.
"""
from fastapi import APIRouter, HTTPException, Query, status

from app import schemas
from services import career_service, job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/search", response_model=schemas.JobSearchResponse)
def search_jobs(
    q: str = Query(min_length=1, max_length=200, description="What to look for"),
    limit: int = Query(job_service.DEFAULT_LIMIT, ge=1, le=job_service.MAX_LIMIT),
):
    """Semantic search over the live postings collected into `job_role`."""
    return job_service.search_postings(q, limit=limit)


@router.post("/for-role", response_model=schemas.RoleJobsResponse)
def jobs_for_role(payload: schemas.RoleJobsRequest):
    """The live postings closest to one catalogued role, best first.

    POST because the questionnaire travels with the request: the same role ranks
    differently for two candidates, which is the point — this is the read used by
    the "live openings" list on a role card and on the role detail page.
    """
    role = career_service.get_role_by_id(payload.role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return job_service.search_for_role(role, payload.profile, limit=payload.limit)
