"""Live job-posting endpoints.

Public and read-only, like `/roles`: the postings come from public job boards and
carry no user data. The `job_role` collection behind them is filled explicitly by
`python -m scripts.ingest_jobs`, so these endpoints are also honest about having
no data yet — see `schemas.JobSearchResponse.available`.

`/search` takes a query *and* the structured filters the Jobs page offers. The
filters are applied by the vector store, so they narrow the whole collection and
`matched` is a real count of it — see `services.job_service`. It also reports how
old the data is (`schemas.HarvestFreshness`), because live postings age silently.

`/classify` is the one endpoint here that spends anything: it reads one advert with
the AI and stores what the job actually is (`services.classification`). It is a POST
because it writes, and it is per listing because one listing is one model call — see
`schemas.JobClassifyRequest`. Every read of a posting carries the stored verdict when
there is one, so this is only ever called for a listing nobody has read.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app import schemas
from app.dependencies import get_optional_user, spend_ai_quota
from services import ai_service, career_service, classification, job_service

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
    employment_type: Optional[
        Literal["full_time", "part_time", "internship", "contract", "permanent"]
    ] = Query(None, description="How the job hires — matched against the board's wording"),
    posted_within_days: Optional[int] = Query(
        None, ge=1, le=365, description="Only postings the board dated within this many days"
    ),
    category: str = Query(
        "",
        max_length=80,
        description="Only listings the classifier filed under this category",
    ),
    limit: int = Query(job_service.DEFAULT_LIMIT, ge=1, le=job_service.MAX_LIMIT),
):
    """Semantic search over the live postings collected into `job_role`.

    `q` is the ranking signal and may be left empty when at least one filter is
    given — the filter terms then stand in for it, so browsing by filter still
    comes back in a sensible order. Asking for nothing at all is a 400 rather
    than an empty guess.

    Not every board publishes every filter: `employment_type` and
    `posted_within_days` read fields only some boards send, and a posting that
    does not carry one simply does not match that filter. The response's `sources`
    block names the providers that contributed and any that could not be read, so
    a thin result set can be explained rather than just observed.

    `category` is the taxonomy of the *classification* (`/roles/categories`), not a
    field a board publishes — so it narrows to listings whose advert has been read
    and filed, and an unknown label is a 400 rather than a page that quietly matches
    nothing. Listings nobody has classified match no category of any kind; see
    `services.job_service.search_postings`.
    """
    if category and category not in career_service.get_all_categories():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown category '{category}'. One of: "
                + ", ".join(career_service.get_all_categories())
            ),
        )
    if not (
        q.strip()
        or location.strip()
        or remote is not None
        or experience
        or employment_type
        or posted_within_days
        or category
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a search query or at least one filter.",
        )
    return job_service.search_postings(
        q,
        limit=limit,
        location=location,
        remote=remote,
        experience=experience or "",
        employment_type=employment_type or "",
        posted_within_days=posted_within_days,
        category=category,
    )


@router.post("/classify", response_model=schemas.ListingClassification)
def classify_job(
    payload: schemas.JobClassifyRequest,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Reads one listing's advert and says what the job actually is.

    The answer is the stored verdict, whether or not it cost anything: a listing
    already classified is returned from the store with `cached: true`, and a listing
    the classifier could not place comes back as Unclassified with the reason
    (`unclassified_reason`) rather than as an error. Only a *momentary* failure —
    no key, no index — is an error status, because those are the deployment's
    problem and a candidate can do nothing with them.

    The AI token is spent after the store has answered (see `spend_ai_quota`), so
    reading verdicts that already exist is free and only reaching for the model is
    metered.
    """
    if not job_service.jobs_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The job index has not been built yet, so there is no listing to "
                "classify. Build it with: python -m scripts.ingest_jobs"
            ),
        )
    posting = job_service.posting_by_id(payload.id)
    if posting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such listing in the job index.",
        )

    stored = classification.without_model(posting, force=payload.force)
    if stored is not None:
        return stored

    refusal = spend_ai_quota(request, user)
    if refusal:
        raise refusal

    try:
        return classification.classify_posting(posting, force=payload.force)
    except ai_service.AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


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
