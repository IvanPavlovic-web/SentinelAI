from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.user import User
from app.schemas.auth import UserCreate
from app.services.audit_service import log_action


def register_user(db: Session, payload: UserCreate) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return user


def issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id, user.role.value)
    refresh_token, jti, expires_at = create_refresh_token(user.id)

    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    db.commit()

    return access_token, refresh_token


def login(db: Session, email: str, password: str, ip_address: str | None = None) -> tuple[str, str]:
    user = authenticate_user(db, email, password)
    access_token, refresh_token = issue_token_pair(db, user)
    log_action(db, user_id=user.id, action="login", resource_type="user", resource_id=user.id, ip_address=ip_address)
    return access_token, refresh_token


def refresh_access_token(db: Session, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    jti = payload.get("jti")
    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if record is None or record.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or unknown")
    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Rotate: revoke old, issue new pair.
    record.revoked = True
    db.commit()

    return issue_token_pair(db, user)


def logout(db: Session, refresh_token: str, user_id: int) -> None:
    payload = decode_token(refresh_token)
    jti = payload.get("jti")
    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if record:
        record.revoked = True
        db.commit()
    log_action(db, user_id=user_id, action="logout", resource_type="user", resource_id=user_id)
