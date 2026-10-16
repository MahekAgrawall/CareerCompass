"""Roadmap Copilot endpoints (standard + streaming)."""
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app import schemas
from services import ai_service, career_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _require_role(role_id: str) -> dict:
    role = career_service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


@router.post("", response_model=Dict[str, str])
def chat(payload: schemas.ChatRequest):
    role = _require_role(payload.role_id)
    try:
        reply = ai_service.send_chat_message(
            payload.profile, role, payload.roadmap, payload.new_message, payload.history
        )
    except ai_service.AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Chat failed: {e}")
    return {"reply": reply}


@router.post("/stream")
def chat_stream(payload: schemas.ChatRequest):
    role = _require_role(payload.role_id)
    # Fail fast (before the stream starts) if the AI key is missing.
    try:
        ai_service._ensure_configured()
    except ai_service.AIConfigurationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    def generate():
        yield from ai_service.stream_chat_message(
            payload.profile, role, payload.roadmap, payload.new_message, payload.history
        )

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
