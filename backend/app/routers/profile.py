"""Authenticated user profile endpoints."""
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app import schemas
from app.dependencies import get_current_user
from services import auth_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=Dict[str, Any])
def get_profile(user: dict = Depends(get_current_user)):
    return auth_service.get_user_profile(user["id"]) or {}


@router.put("", response_model=Dict[str, Any])
def save_profile(payload: schemas.ProfileIn, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    auth_service.save_user_profile(user["id"], data)
    return data
