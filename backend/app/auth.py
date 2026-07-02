"""Authentication & Authorization module"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie
from jwt import PyJWTError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)
refresh_cookie_scheme = APIKeyCookie(name="refresh_token", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Timing-Angleich beim Login: auch bei unbekannter E-Mail läuft ein bcrypt-Vergleich,
# damit die Antwortzeit nicht verrät, welche Adressen registriert sind.
DUMMY_PASSWORD_HASH = get_password_hash("timing-equalization-dummy")


def create_access_token(user_id: int, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "access", "ver": token_version}
    return pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "refresh", "ver": token_version}
    return pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def set_auth_cookies(response: Response, user: User):
    """Set HttpOnly cookies for access and refresh tokens"""
    version = user.token_version or 0
    access_token = create_access_token(user.id, version)
    refresh_token = create_refresh_token(user.id, version)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )


def clear_auth_cookies(response: Response):
    """Clear auth cookies on logout"""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")


def _decode_token(token: str, expected_type: str) -> Optional[dict]:
    """Decode and validate a JWT token, returning the payload (sub as int) or None.
    Tokens ohne "ver"-Claim (vor Migration 18 ausgestellt) zählen als Version 0."""
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
        payload["sub"] = int(user_id)
        return payload
    except (PyJWTError, ValueError):
        return None


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extract current user from access_token cookie"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht eingeloggt",
        )

    payload = _decode_token(token, "access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ungültig oder abgelaufen",
        )

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden oder deaktiviert",
        )

    # Nach einem Passwortwechsel (token_version erhöht) sind alte Tokens ungültig
    if payload.get("ver", 0) != (user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sitzung abgelaufen, bitte neu einloggen",
        )

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency: require admin privileges"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin-Rechte erforderlich",
        )
    return user


def validate_refresh_token(token: str) -> Optional[dict]:
    """Validate a refresh token and return the payload (sub = user_id, ver = token_version)"""
    return _decode_token(token, "refresh")
