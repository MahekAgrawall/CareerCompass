"""Roadmap generation and saved-roadmap library endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.dependencies import get_current_user, get_optional_user
from services import ai_service, auth_service, career_service

router = APIRouter(tags=["roadmap"])


@router.post("/roadmap", response_model=Dict[str, Any])
def generate(payload: schemas.RoadmapRequest, user: dict | None = Depends(get_optional_user)):
    role = career_service.get_role_by_id(payload.role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    try:
        roadmap = ai_service.generate_roadmap(payload.profile, role)
    except ai_service.AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Roadmap generation failed: {e}")

    if user:
        auth_service.save_roadmap(user["id"], role["id"], role["title"], roadmap)

    return roadmap


@router.get("/roadmaps", response_model=List[Dict[str, Any]])
def list_saved(user: dict = Depends(get_current_user)):
    return auth_service.get_saved_roadmaps(user["id"])


@router.delete("/roadmaps/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(roadmap_id: int, user: dict = Depends(get_current_user)):
    auth_service.delete_saved_roadmap(roadmap_id, user["id"])
