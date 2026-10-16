"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.dependencies import get_current_user
from app.security import create_access_token
from services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: dict) -> schemas.TokenResponse:
    token = create_access_token(user["id"], user["email"])
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserOut(id=user["id"], name=user["name"], email=user["email"]),
    )


@router.post("/signup", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.SignupRequest):
    ok, message = auth_service.signup_user(payload.name, payload.email, payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    authed, user = auth_service.authenticate_user(payload.email, payload.password)
    if not authed:
        raise HTTPException(status_code=500, detail="Account created but sign-in failed.")
    return _token_response(user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest):
    ok, result = auth_service.authenticate_user(payload.email, payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result)
    return _token_response(result)


@router.get("/me", response_model=schemas.MeResponse)
def me(user: dict = Depends(get_current_user)):
    return schemas.MeResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        profile=user.get("profile") or {},
    )
