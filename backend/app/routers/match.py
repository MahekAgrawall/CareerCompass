"""Role-matching endpoint."""
from fastapi import APIRouter, Depends, Request

from app import schemas
from app.dependencies import consume_ai_quota, get_optional_user
from services import ai_service, career_service

router = APIRouter(tags=["matching"])


@router.post("/match", response_model=schemas.MatchResponse)
def match(
    payload: schemas.MatchRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    profile = {
        "interests": payload.interests,
        "current_skills": payload.current_skills,
        # Context for the semantic recall stage only; the score ignores it.
        "career_goal": payload.career_goal,
        "experience": payload.experience,
        "work_mode": payload.work_mode,
        "location": payload.location,
    }
    results = career_service.match_roles_smart(profile)

    explanation = ""
    # The ranked matches never call Gemini; only the written assessment does. When
    # the caller's AI budget is spent we drop the assessment rather than the answer.
    if payload.explain and results and consume_ai_quota(request, user):
        explanation = ai_service.generate_role_match_explanation(
            profile, [item["role"] for item in results]
        )

    return schemas.MatchResponse(
        results=[schemas.MatchResult(**item) for item in results],
        explanation=explanation,
        interest_weight=career_service.INTEREST_WEIGHT,
        skill_weight=career_service.SKILL_WEIGHT,
    )
