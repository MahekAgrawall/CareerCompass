"""Study-tracker endpoints (schedule, stacks, syllabus topics, progress).

Tracker state is *per-user* data, so every schedule/topic endpoint requires
authentication. All reads and writes are scoped to the authenticated user's id,
which means one user can never read or modify another user's progress.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.dependencies import get_current_user
from services import tracker_service

router = APIRouter(prefix="/tracker", tags=["tracker"])


@router.get("/stack/{role_id}", response_model=Dict[str, Any])
def get_stack(role_id: str):
    """Static per-role stack catalogue — contains no user data, so it stays public."""
    return tracker_service.get_role_stack_schema(role_id)


@router.get("/schedule/{role_id}", response_model=Dict[str, Any])
def get_schedule(role_id: str, user: dict = Depends(get_current_user)):
    return tracker_service.get_study_schedule(user["id"], role_id)


@router.put("/schedule", response_model=Dict[str, Any])
def save_schedule(payload: schemas.ScheduleIn, user: dict = Depends(get_current_user)):
    uid = user["id"]
    schedule = tracker_service.save_study_schedule(
        uid, payload.role_id, payload.weekday_hours,
        payload.weekend_hours, payload.target_languages,
    )
    topics = tracker_service.sync_topics_for_role_stack(
        uid, payload.role_id, payload.target_languages, force_refresh=True
    )
    metrics = tracker_service.calculate_tracker_metrics(topics, schedule["weekly_total_hours"])
    return {"schedule": schedule, "topics": topics, "metrics": metrics}


@router.get("/topics/{role_id}", response_model=Dict[str, Any])
def get_topics(role_id: str, user: dict = Depends(get_current_user)):
    uid = user["id"]
    schedule = tracker_service.get_study_schedule(uid, role_id)
    topics = tracker_service.sync_topics_for_role_stack(
        uid, role_id, schedule["target_languages"], force_refresh=False
    )
    metrics = tracker_service.calculate_tracker_metrics(topics, schedule["weekly_total_hours"])
    return {"schedule": schedule, "topics": topics, "metrics": metrics}


@router.patch("/topics/{topic_id}", response_model=Dict[str, Any])
def toggle_topic(
    topic_id: int,
    payload: schemas.TopicToggle,
    user: dict = Depends(get_current_user),
):
    """Toggles a completion marker, but only for a topic owned by the caller."""
    updated = tracker_service.toggle_topic_status(topic_id, user["id"], payload.is_completed)
    if not updated:
        # 404 (not 403) so we never reveal whether another user's topic exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return {"id": topic_id, "is_completed": payload.is_completed}
