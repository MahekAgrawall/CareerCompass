"""Study-tracker endpoints (schedule, stacks, syllabus topics, progress)."""
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app import schemas
from app.dependencies import get_optional_user
from services import tracker_service

router = APIRouter(prefix="/tracker", tags=["tracker"])


def _uid(user) -> int:
    return user["id"] if user else 0


@router.get("/stack/{role_id}", response_model=Dict[str, Any])
def get_stack(role_id: str):
    return tracker_service.get_role_stack_schema(role_id)


@router.get("/schedule/{role_id}", response_model=Dict[str, Any])
def get_schedule(role_id: str, user=Depends(get_optional_user)):
    return tracker_service.get_study_schedule(_uid(user), role_id)


@router.put("/schedule", response_model=Dict[str, Any])
def save_schedule(payload: schemas.ScheduleIn, user=Depends(get_optional_user)):
    uid = _uid(user)
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
def get_topics(role_id: str, user=Depends(get_optional_user)):
    uid = _uid(user)
    schedule = tracker_service.get_study_schedule(uid, role_id)
    topics = tracker_service.sync_topics_for_role_stack(
        uid, role_id, schedule["target_languages"], force_refresh=False
    )
    metrics = tracker_service.calculate_tracker_metrics(topics, schedule["weekly_total_hours"])
    return {"schedule": schedule, "topics": topics, "metrics": metrics}


@router.patch("/topics/{topic_id}", response_model=Dict[str, Any])
def toggle_topic(topic_id: int, payload: schemas.TopicToggle):
    tracker_service.toggle_topic_status(topic_id, payload.is_completed)
    return {"id": topic_id, "is_completed": payload.is_completed}
