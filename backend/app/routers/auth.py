from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.db.base import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

_login_rate_limit = rate_limit("login", settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
_register_rate_limit = rate_limit("register", settings.REGISTER_RATE_LIMIT_MAX, settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS)


@router.post("/register", response_model=UserRead, status_code=201, dependencies=[Depends(_register_rate_limit)])
def register(payload: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register_user(db, payload)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(_login_rate_limit)])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    access_token, refresh_token = auth_service.login(
        db, payload.email, payload.password, ip_address=request.client.host if request.client else None
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    access_token, refresh_token = auth_service.refresh_access_token(db, payload.refresh_token)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
def logout(payload: LogoutRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    auth_service.logout(db, payload.refresh_token, current_user.id)
    return None


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)):
    return current_user
