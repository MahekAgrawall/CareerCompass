"""Role-matching endpoint."""
from fastapi import APIRouter

from app import schemas
from services import ai_service, career_service

router = APIRouter(tags=["matching"])


@router.post("/match", response_model=schemas.MatchResponse)
def match(payload: schemas.MatchRequest):
    profile = {
        "interests": payload.interests,
        "current_skills": payload.current_skills,
        # Context for the semantic recall stage only; the score ignores it.
        "career_goal": payload.career_goal,
        "experience": payload.experience,
        "work_mode": payload.work_mode,
    }
    results = career_service.match_roles_smart(profile)

    explanation = ""
    if payload.explain and results:
        explanation = ai_service.generate_role_match_explanation(
            profile, [item["role"] for item in results]
        )

    return schemas.MatchResponse(
        results=[schemas.MatchResult(**item) for item in results],
        explanation=explanation,
        interest_weight=career_service.INTEREST_WEIGHT,
        skill_weight=career_service.SKILL_WEIGHT,
    )
