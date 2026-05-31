"""Online-banking (FinTS/HBCI) endpoints — read-only balance & transaction retrieval."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .. import schemas
from ..audit import log_data_event
from ..auth import get_current_user
from ..config import settings as app_settings
from ..database import get_db
from ..models import BankConnection, User
from ..services import fints_service
from ..services.fints_service import BankingError

router = APIRouter(prefix="/api/banking", tags=["banking"])
limiter = Limiter(key_func=get_remote_address)


def _get_owned_connection(connection_id: int, user: User, db: Session) -> BankConnection:
    conn = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user.id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Bankverbindung nicht gefunden")
    return conn


@router.get("/connections", response_model=List[schemas.BankConnectionResponse])
def list_connections(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List the current user's bank connections (no secrets)."""
    return db.query(BankConnection).filter(
        BankConnection.user_id == current_user.id
    ).order_by(BankConnection.created_at).all()


@router.post("/connections", response_model=schemas.BankConnectionResponse, status_code=201)
def create_connection(
    data: schemas.BankConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a bank connection. No network call and no PIN — login happens on sync."""
    conn = BankConnection(
        user_id=current_user.id,
        name=data.name,
        bank_code=data.bank_code,
        fints_url=data.fints_url,
        login_name=data.login_name,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)

    log_data_event("create", user_id=current_user.id, resource="bank_connection", resource_id=conn.id,
                   detail=f"bank={data.bank_code}")
    return conn


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a bank connection (does not delete already-imported transactions)."""
    conn = _get_owned_connection(connection_id, current_user, db)
    db.delete(conn)
    db.commit()
    log_data_event("delete", user_id=current_user.id, resource="bank_connection", resource_id=connection_id)
    return {"message": "Bankverbindung gelöscht"}


@router.post("/connections/{connection_id}/sync", response_model=schemas.SyncResult)
@limiter.limit(f"{app_settings.BANKING_SYNC_RATE_LIMIT_PER_MINUTE}/minute")
def sync_connection(
    request: Request,
    connection_id: int,
    data: schemas.SyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a sync: log in, fetch transactions. May return a TAN challenge to complete."""
    conn = _get_owned_connection(connection_id, current_user, db)
    try:
        result = fints_service.start_sync(db, conn, data.pin, data.from_date)
    except BankingError as e:
        return schemas.SyncResult(status="error", message=str(e))

    if result.get("status") == "done":
        log_data_event("fints_sync", user_id=current_user.id, resource="bank_connection",
                       resource_id=conn.id, detail=f"new={result.get('imported')} dup={result.get('duplicates')}")
    return schemas.SyncResult(**result)


@router.post("/connections/{connection_id}/tan", response_model=schemas.SyncResult)
def submit_tan(
    connection_id: int,
    data: schemas.TanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a TAN (or poll a decoupled approval) to finish a paused sync."""
    conn = _get_owned_connection(connection_id, current_user, db)
    try:
        result = fints_service.resume_sync(db, conn, data.job_id, data.tan)
    except BankingError as e:
        return schemas.SyncResult(status="error", message=str(e))

    if result.get("status") == "done":
        log_data_event("fints_sync", user_id=current_user.id, resource="bank_connection",
                       resource_id=conn.id, detail=f"new={result.get('imported')} dup={result.get('duplicates')}")
    return schemas.SyncResult(**result)
