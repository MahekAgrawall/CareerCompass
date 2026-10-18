"""Shared FastAPI dependencies (authentication and the AI quota)."""
import math
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import AI_RATE_LIMIT, AI_RATE_WINDOW_SECONDS
from app.security import decode_access_token
from services import auth_service
from services.rate_limit import RateLimiter

# One budget for the whole process: see services/rate_limit.py for why that is
# enough here (and what would change it).
ai_limiter = RateLimiter(AI_RATE_LIMIT, AI_RATE_WINDOW_SECONDS)


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


def _quota_key(request: Request, user: Optional[dict]) -> str:
    """Meters a signed-in candidate by identity and everyone else by address."""
    if user:
        return f"user:{user['id']}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def _consume_quota(request: Request, user: Optional[dict]) -> tuple[bool, float]:
    """Records one AI call for this caller: (allowed, seconds if not)."""
    return ai_limiter.check(_quota_key(request, user))


def consume_ai_quota(request: Request, user: Optional[dict]) -> bool:
    """Soft form, for endpoints where the AI is only part of the answer.

    `/match` ranks roles deterministically; the written assessment is a bonus on
    top. Returning False lets the caller skip that bonus instead of failing a
    request whose real answer is already computed.
    """
    allowed, _ = _consume_quota(request, user)
    return allowed


def _too_many_requests(retry_after: float) -> HTTPException:
    """The 429 every AI endpoint refuses with, worded once."""
    wait = max(1, math.ceil(retry_after))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            "You have made a lot of AI requests in a short time. "
            f"Please wait about {wait} seconds and try again."
        ),
        headers={"Retry-After": str(wait)},
    )


def spend_ai_quota(request: Request, user: Optional[dict]) -> Optional[HTTPException]:
    """The decision `ai_quota` would make, in a form a route can take later.

    For an endpoint where the model is only sometimes reached: `/jobs/classify`
    answers from the classification store without asking anything, and charges a
    token only when it actually goes to the model. Returns the refusal to raise, or
    None when the call is allowed — so the wording and headers stay in one place.
    """
    allowed, retry_after = _consume_quota(request, user)
    return None if allowed else _too_many_requests(retry_after)


def ai_quota(request: Request, user: Optional[dict] = Depends(get_optional_user)) -> None:
    """Rejects with 429 once the caller's AI budget for the window is spent."""
    refusal = spend_ai_quota(request, user)
    if refusal:
        raise refusal
