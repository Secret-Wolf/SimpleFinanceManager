"""Authentication endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..config import settings as app_settings

from ..audit import log_auth_event, log_security_event
from ..auth import (
    clear_auth_cookies,
    get_current_admin,
    get_current_user,
    get_password_hash,
    set_auth_cookies,
    validate_refresh_token,
    verify_password,
)
from ..database import get_db
from ..models import User, Account, Category, CategorizationRule
from .. import schemas
from typing import List

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
@limiter.limit(f"{app_settings.LOGIN_RATE_LIMIT_PER_MINUTE}/minute")
def register(request: Request, data: schemas.UserRegister, response: Response, db: Session = Depends(get_db)):
    """Register a new user. First user becomes admin automatically."""

    # Check if email already exists
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-Mail-Adresse bereits registriert")

    # First user becomes admin
    user_count = db.query(User).count()
    is_first_user = user_count == 0

    # Only admin can register additional users (after first user)
    if not is_first_user:
        # Check for valid auth cookie
        # We don't use Depends here because registration should work for first user
        raise HTTPException(
            status_code=403,
            detail="Registrierung nur durch Admin möglich. Bitte beim Administrator melden."
        )

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        display_name=data.display_name,
        is_admin=is_first_user,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-login after registration
    set_auth_cookies(response, user.id)

    log_auth_event(
        "register",
        ip=request.client.host if request.client else "unknown",
        user_id=user.id,
        user_email=user.email,
        detail="first_user/admin" if is_first_user else "user",
    )

    # Assign existing data to first user (migration of legacy data)
    if is_first_user:
        _assign_legacy_data_to_user(db, user.id)

    return user


@router.post("/register-user", response_model=schemas.UserResponse, status_code=201)
def register_user_by_admin(
    data: schemas.UserRegister,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin creates a new user account."""
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-Mail-Adresse bereits registriert")

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        display_name=data.display_name,
        is_admin=False,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    log_auth_event(
        "register_by_admin",
        ip="internal",
        user_id=user.id,
        user_email=user.email,
        detail=f"created_by_admin_id={admin.id}",
    )

    return user


@router.post("/login")
@limiter.limit(f"{app_settings.LOGIN_RATE_LIMIT_PER_MINUTE}/minute")
def login(request: Request, data: schemas.UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login with email and password"""
    user = db.query(User).filter(User.email == data.email.strip().lower()).first()

    client_ip = request.client.host if request.client else "unknown"

    if not user or not verify_password(data.password, user.hashed_password):
        log_auth_event(
            "login_failed",
            ip=client_ip,
            user_email=data.email,
            status="failure",
            detail="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige E-Mail oder Passwort",
        )

    if not user.is_active:
        log_auth_event(
            "login_failed",
            ip=client_ip,
            user_id=user.id,
            user_email=user.email,
            status="failure",
            detail="account_disabled",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konto deaktiviert",
        )

    set_auth_cookies(response, user.id)

    log_auth_event("login", ip=client_ip, user_id=user.id, user_email=user.email)

    return {
        "message": "Erfolgreich eingeloggt",
        "user": schemas.UserResponse.model_validate(user),
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    """Logout - clear auth cookies"""
    clear_auth_cookies(response)
    log_auth_event("logout", ip=request.client.host if request.client else "unknown")
    return {"message": "Erfolgreich ausgeloggt"}


@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """Refresh access token using refresh token cookie"""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Refresh-Token vorhanden")

    user_id = validate_refresh_token(token)
    if user_id is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh-Token ungültig oder abgelaufen")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Benutzer nicht gefunden")

    set_auth_cookies(response, user.id)

    return {
        "message": "Token erneuert",
        "user": schemas.UserResponse.model_validate(user),
    }


@router.get("/me", response_model=schemas.UserResponse)
def get_me(user: User = Depends(get_current_user)):
    """Get current user info"""
    return user


@router.patch("/me", response_model=schemas.UserResponse)
def update_me(
    data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update current user profile"""
    if data.display_name is not None:
        user.display_name = data.display_name.strip()

    if data.email is not None:
        new_email = data.email.strip().lower()
        if new_email != user.email:
            existing = db.query(User).filter(User.email == new_email).first()
            if existing:
                raise HTTPException(status_code=400, detail="E-Mail bereits vergeben")
            user.email = new_email

    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(
    request: Request,
    data: schemas.PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change password for current user"""
    client_ip = request.client.host if request.client else "unknown"

    if not verify_password(data.current_password, user.hashed_password):
        log_auth_event(
            "password_change_failed",
            ip=client_ip,
            user_id=user.id,
            status="failure",
            detail="wrong_current_password",
        )
        raise HTTPException(status_code=400, detail="Aktuelles Passwort ist falsch")

    user.hashed_password = get_password_hash(data.new_password)
    db.commit()

    log_auth_event("password_changed", ip=client_ip, user_id=user.id)

    return {"message": "Passwort geändert"}


@router.get("/users", response_model=List[schemas.UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """List all users (admin only)"""
    users = db.query(User).order_by(User.created_at).all()
    return users


@router.patch("/users/{user_id}", response_model=schemas.UserResponse)
def update_user_by_admin(
    user_id: int,
    data: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Update user account (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if data.is_active is False and user.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Eigenes Konto kann nicht deaktiviert werden"
        )

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.display_name is not None:
        user.display_name = data.display_name.strip()

    if data.new_password is not None:
        user.hashed_password = get_password_hash(data.new_password)

    db.commit()
    db.refresh(user)

    log_auth_event(
        "admin_user_update",
        ip="internal",
        user_id=user.id,
        user_email=user.email,
        detail=f"updated_by_admin_id={admin.id}",
    )

    return user


@router.get("/setup-required")
def check_setup(db: Session = Depends(get_db)):
    """Check if initial setup (first user registration) is needed"""
    user_count = db.query(User).count()
    return {"setup_required": user_count == 0}


def _assign_legacy_data_to_user(db: Session, user_id: int):
    """Assign all existing data without user_id to the first registered user"""
    db.query(Account).filter(Account.user_id == None).update(
        {"user_id": user_id}, synchronize_session=False
    )
    db.query(Category).filter(Category.user_id == None).update(
        {"user_id": user_id}, synchronize_session=False
    )
    db.query(CategorizationRule).filter(CategorizationRule.user_id == None).update(
        {"user_id": user_id}, synchronize_session=False
    )
    db.commit()
