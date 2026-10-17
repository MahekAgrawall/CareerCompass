"""Saved jobs and application tracking — a candidate's own records.

Everything here is *per-user* data, unlike `/jobs` (public, read-only listings),
so every endpoint requires authentication and every query is scoped to the
authenticated user's id. A row belonging to somebody else is answered with 404
rather than 403, the way the study tracker does it: whether a given application
exists at all is itself private.

The stage vocabulary and the snapshot rule live in
`services.application_service`; this module only shapes HTTP around them.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app import schemas
from app.dependencies import get_current_user
from services import application_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=schemas.ApplicationListResponse)
def list_applications(user: dict = Depends(get_current_user)):
    """Every posting the candidate saved, most recently touched first."""
    results = application_service.list_applications(user["id"])
    return {"count": len(results), "results": results}


@router.post("", response_model=schemas.SavedJob, status_code=status.HTTP_201_CREATED)
def save_application(
    payload: schemas.ApplicationCreate,
    response: Response,
    user: dict = Depends(get_current_user),
):
    """Files a posting, or returns the row already filed for it.

    Saving is idempotent by `posting_id`: a second save answers `200` with the
    stored row rather than `201`, and never resets a stage the candidate has
    already advanced past.
    """
    row, created = application_service.save_application(user["id"], payload.model_dump())
    if not created:
        response.status_code = status.HTTP_200_OK
    return row


@router.patch("/{application_id}", response_model=schemas.SavedJob)
def update_application(
    application_id: int,
    payload: schemas.ApplicationUpdate,
    user: dict = Depends(get_current_user),
):
    """Moves a saved posting to another stage, edits its note, or both."""
    if payload.status is None and payload.note is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Give a status, a note, or both.",
        )
    row = application_service.update_application(
        user["id"], application_id, status=payload.status, note=payload.note
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved job not found")
    return row


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: int, user: dict = Depends(get_current_user)):
    """Forgets a saved posting — the exit for one the candidate no longer wants."""
    if not application_service.delete_application(user["id"], application_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved job not found")
