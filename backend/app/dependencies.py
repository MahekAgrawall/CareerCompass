"""Shared FastAPI dependencies (authentication)."""
from typing import Optional

from fastapi import Header, HTTPException, status

from app.security import decode_access_token
from services import auth_service


def _resolve_user(authorization: Optional[str]) -> Optional[dict]:
    """Resolves a bearer token into a user dict, or None if absent/invalid."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        payload = decode_access_token(parts[1])
        user_id = int(payload.get("sub"))
    except Exception:
        return None
    return auth_service.get_user_by_id(user_id)


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Requires a valid bearer token; raises 401 otherwise."""
    user = _resolve_user(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    """Returns the authenticated user if present, otherwise None."""
    return _resolve_user(authorization)
