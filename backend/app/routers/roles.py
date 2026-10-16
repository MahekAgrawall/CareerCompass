"""Role catalog endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

from services import career_service

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=List[Dict[str, Any]])
def list_roles():
    return career_service.get_all_roles()


@router.get("/categories", response_model=List[str])
def list_categories():
    return career_service.get_all_categories()


@router.get("/{role_id}", response_model=Dict[str, Any])
def get_role(role_id: str):
    role = career_service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role
