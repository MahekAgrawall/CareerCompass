"""Live job-posting endpoints.

Public and read-only, like `/roles`: the postings come from public job boards and
carry no user data. The `job_role` collection behind them is filled explicitly by
`python -m scripts.ingest_jobs`, so these endpoints are also honest about having
no data yet — see `schemas.JobSearchResponse.available`.

`/search` takes a query *and* the structured filters the Jobs page offers. The
filters are applied by the vector store, so they narrow the whole collection and
`matched` is a real count of it — see `services.job_service`. It also reports how
old the data is (`schemas.HarvestFreshness`), because live postings age silently.
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app import schemas
from services import career_service, job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/search", response_model=schemas.JobSearchResponse)
def search_jobs(
    q: str = Query("", max_length=200, description="What to look for — ranks the results"),
    location: str = Query("", max_length=80, description="A place, or 'remote'"),
    remote: Optional[bool] = Query(
        None, description="True/False to filter on the board's own remote flag"
    ),
    experience: Optional[Literal["internship", "entry", "senior"]] = Query(
        None, description="Experience bucket: internship, entry or senior"
    ),
    limit: int = Query(job_service.DEFAULT_LIMIT, ge=1, le=job_service.MAX_LIMIT),
):
    """Semantic search over the live postings collected into `job_role`.

    `q` is the ranking signal and may be left empty when at least one filter is
    given — the filter terms then stand in for it, so browsing by filter still
    comes back in a sensible order. Asking for nothing at all is a 400 rather
    than an empty guess.
    """
    if not (q.strip() or location.strip() or remote is not None or experience):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a search query or at least one filter.",
        )
    return job_service.search_postings(
        q, limit=limit, location=location, remote=remote, experience=experience or ""
    )


@router.get("/locations", response_model=schemas.JobLocationsResponse)
def job_locations():
    """The places the indexed postings name, plus the Indian market's preferences.

    Public like `/search`, and equally honest without an index: no postings means
    no options, not an error. The Jobs page fills its location suggestions from
    here — the collection's own vocabulary — rather than from the fifty postings
    a previous search happened to return, and offers the Indian hubs beside them
    (`preferred`) even where the boards carry nothing, so a candidate can see what
    the feed actually holds at home instead of assuming the field forgot them.
    """
    return job_service.locations()


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
