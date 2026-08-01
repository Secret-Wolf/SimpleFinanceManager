"""Authentication endpoints"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from sqlalchemy.orm import Session

from .. import schemas
from ..audit import log_auth_event
from ..auth import (
    DUMMY_PASSWORD_HASH,
    clear_auth_cookies,
    get_current_admin,
    get_current_user,
    get_password_hash,
    set_auth_cookies,
    validate_refresh_token,
    verify_password,
)
from ..client_ip import client_ip_key, get_client_ip
from ..config import settings as app_settings
from ..database import get_db
from ..models import Account, CategorizationRule, Category, User
from ..totp import (
    generate_recovery_codes,
    generate_secret,
    provisioning_uri,
    qr_svg,
    remaining_recovery_codes,
    use_recovery_code,
    verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=client_ip_key)


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
    set_auth_cookies(response, user)

    log_auth_event(
        "register",
        ip=get_client_ip(request),
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

    client_ip = get_client_ip(request)

    # Bei unbekannter E-Mail gegen einen Dummy-Hash prüfen (Timing-Angleich)
    password_ok = verify_password(data.password, user.hashed_password if user else DUMMY_PASSWORD_HASH)

    if not user or not password_ok:
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

    # Zwei-Faktor: Passwort allein reicht nicht, wenn TOTP aktiviert ist
    if user.totp_enabled and user.totp_secret:
        code = (data.totp_code or "").strip()
        if not code:
            # Passwort war korrekt, aber es fehlt der 2FA-Code — keine Cookies setzen.
            # Das Frontend blendet daraufhin das Code-Feld ein und sendet erneut.
            return {"totp_required": True}
        _check_second_factor(db, user, code, client_ip)

    set_auth_cookies(response, user)

    log_auth_event("login", ip=client_ip, user_id=user.id, user_email=user.email)

    return {
        "message": "Erfolgreich eingeloggt",
        "user": schemas.UserResponse.model_validate(user),
    }


def _check_second_factor(db: Session, user: User, code: str, client_ip: str) -> None:
    """Prüft beim Login den zweiten Faktor: TOTP-Code (6 Ziffern) oder Recovery-Code.
    Wirft 401 bei ungültigem/bereits benutztem Code; verbraucht benutzte Recovery-Codes."""
    compact = code.replace(" ", "")
    if compact.isdigit() and len(compact) == 6:
        result, counter = verify_totp(user.totp_secret, compact, user.totp_last_counter)
        if result == "ok":
            user.totp_last_counter = counter
            db.commit()
            return
        if result == "used":
            log_auth_event(
                "login_failed", ip=client_ip, user_id=user.id, user_email=user.email,
                status="failure", detail="totp_replay",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Dieser 2FA-Code wurde bereits verwendet — bitte den nächsten Code eingeben",
            )
    else:
        remaining = use_recovery_code(user.totp_recovery_codes, code)
        if remaining is not None:
            user.totp_recovery_codes = remaining
            db.commit()
            log_auth_event(
                "login_recovery_code", ip=client_ip, user_id=user.id, user_email=user.email,
                detail=f"remaining={remaining_recovery_codes(remaining)}",
            )
            return

    log_auth_event(
        "login_failed", ip=client_ip, user_id=user.id, user_email=user.email,
        status="failure", detail="invalid_totp",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ungültiger 2FA-Code",
    )


@router.post("/logout")
def logout(request: Request, response: Response):
    """Logout - clear auth cookies"""
    clear_auth_cookies(response)
    log_auth_event("logout", ip=get_client_ip(request))
    return {"message": "Erfolgreich ausgeloggt"}


@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """Refresh access token using refresh token cookie"""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Refresh-Token vorhanden")

    payload = validate_refresh_token(token)
    if payload is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh-Token ungültig oder abgelaufen")

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Benutzer nicht gefunden")

    # Refresh-Tokens von vor einem Passwortwechsel sind ungültig
    if payload.get("ver", 0) != (user.token_version or 0):
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Sitzung abgelaufen, bitte neu einloggen")

    set_auth_cookies(response, user)

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
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change password for current user"""
    client_ip = get_client_ip(request)

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
    # Alle bestehenden Sessions (auch auf anderen Geräten) invalidieren
    user.token_version = (user.token_version or 0) + 1
    db.commit()

    # Die aktuelle Session bleibt eingeloggt: neue Cookies mit neuer Version
    set_auth_cookies(response, user)

    log_auth_event("password_changed", ip=client_ip, user_id=user.id)

    return {"message": "Passwort geändert"}


# --- TOTP-Zwei-Faktor (Selfservice) -----------------------------------------

@router.get("/totp/status")
def totp_status(user: User = Depends(get_current_user)):
    """2FA-Status des eingeloggten Benutzers (für die Profil-Ansicht)"""
    return {
        "enabled": bool(user.totp_enabled),
        "recovery_codes_remaining": remaining_recovery_codes(user.totp_recovery_codes)
        if user.totp_enabled else 0,
    }


@router.post("/totp/setup")
def totp_setup(
    request: Request,
    data: schemas.TotpSetupRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Startet die 2FA-Einrichtung: erzeugt ein Secret und liefert QR-Code + otpauth-URL.
    Aktiv wird 2FA erst nach Bestätigung eines gültigen Codes via /totp/enable."""
    client_ip = get_client_ip(request)

    if not verify_password(data.password, user.hashed_password):
        log_auth_event(
            "totp_setup_failed", ip=client_ip, user_id=user.id,
            status="failure", detail="wrong_password",
        )
        raise HTTPException(status_code=400, detail="Passwort ist falsch")

    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA ist bereits aktiviert")

    secret = generate_secret()
    user.totp_secret = secret
    user.totp_last_counter = None
    db.commit()

    uri = provisioning_uri(secret, user.email)
    return {"secret": secret, "otpauth_url": uri, "qr_svg": qr_svg(uri)}


@router.post("/totp/enable")
def totp_enable(
    request: Request,
    data: schemas.TotpEnableRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Aktiviert 2FA nach Bestätigung eines gültigen Codes aus der Authenticator-App.
    Liefert die Recovery-Codes — sie werden genau einmal im Klartext angezeigt."""
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA ist bereits aktiviert")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Bitte zuerst die Einrichtung starten")

    result, counter = verify_totp(user.totp_secret, data.code, None)
    if result != "ok":
        raise HTTPException(
            status_code=400,
            detail="Ungültiger Code — bitte den aktuellen Code aus der App eingeben",
        )

    codes, hashes_json = generate_recovery_codes()
    user.totp_enabled = True
    user.totp_last_counter = counter
    user.totp_recovery_codes = hashes_json
    db.commit()

    log_auth_event("totp_enabled", ip=get_client_ip(request), user_id=user.id, user_email=user.email)

    return {
        "message": "2FA aktiviert",
        "recovery_codes": codes,
    }


@router.post("/totp/disable")
def totp_disable(
    request: Request,
    data: schemas.TotpDisableRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Deaktiviert 2FA (erfordert Passwort + gültigen TOTP- oder Recovery-Code)."""
    client_ip = get_client_ip(request)

    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA ist nicht aktiviert")

    if not verify_password(data.password, user.hashed_password):
        log_auth_event(
            "totp_disable_failed", ip=client_ip, user_id=user.id,
            status="failure", detail="wrong_password",
        )
        raise HTTPException(status_code=400, detail="Passwort ist falsch")

    compact = (data.code or "").strip().replace(" ", "")
    valid = False
    if compact.isdigit() and len(compact) == 6:
        result, _counter = verify_totp(user.totp_secret, compact, user.totp_last_counter)
        valid = result == "ok"
    else:
        valid = use_recovery_code(user.totp_recovery_codes, data.code) is not None

    if not valid:
        log_auth_event(
            "totp_disable_failed", ip=client_ip, user_id=user.id,
            status="failure", detail="invalid_code",
        )
        raise HTTPException(status_code=400, detail="Ungültiger 2FA-Code")

    user.totp_secret = None
    user.totp_enabled = False
    user.totp_recovery_codes = None
    user.totp_last_counter = None
    db.commit()

    log_auth_event("totp_disabled", ip=client_ip, user_id=user.id, user_email=user.email)

    return {"message": "2FA deaktiviert"}


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

    if data.is_admin is False and user.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Eigene Admin-Rechte können nicht entfernt werden"
        )

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.is_admin is not None:
        user.is_admin = data.is_admin

    if data.display_name is not None:
        user.display_name = data.display_name.strip()

    if data.new_password is not None:
        user.hashed_password = get_password_hash(data.new_password)
        # Bestehende Sessions des Benutzers invalidieren
        user.token_version = (user.token_version or 0) + 1

    if data.reset_totp:
        # 2FA-Reset (z.B. Gerät verloren): Secret + Recovery-Codes löschen und
        # sicherheitshalber alle Sessions des Benutzers invalidieren
        user.totp_secret = None
        user.totp_enabled = False
        user.totp_recovery_codes = None
        user.totp_last_counter = None
        user.token_version = (user.token_version or 0) + 1
        log_auth_event(
            "totp_reset_by_admin", ip="internal", user_id=user.id, user_email=user.email,
            detail=f"reset_by_admin_id={admin.id}",
        )

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
