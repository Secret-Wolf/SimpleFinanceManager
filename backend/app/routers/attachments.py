"""Belege (PDF/PNG/JPG) zu Transaktionen hochladen, abrufen und löschen.

Sicherheitsmodell:
- Typ-Prüfung ausschließlich über Magic Bytes (kein HTML/SVG/Script-Upload möglich),
  gespeichert wird unter zufälligem UUID-Namen (nie der Original-Dateiname).
- Zugriff strikt benutzer-eigen (Attachment.user_id, beim Upload über die
  Konto-Eigentümerschaft der Transaktion abgeleitet).
- Größenlimit MAX_UPLOAD_SIZE_MB, Chunk-weise geprüft (app/uploads.py).
"""

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import schemas
from ..audit import log_data_event
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Account, Attachment, Transaction, User
from ..services.attachments import (
    MAX_ATTACHMENTS_PER_TRANSACTION,
    delete_file,
    detect_content_type,
    file_path,
    sanitize_filename,
    store_file,
)
from ..uploads import read_upload_limited

router = APIRouter(prefix="/api", tags=["attachments"])


@router.post(
    "/transactions/{transaction_id}/attachments",
    response_model=schemas.AttachmentResponse,
    status_code=201,
)
async def upload_attachment(
    transaction_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Beleg (PDF/PNG/JPG) an eine Transaktion anhängen"""
    user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    count = db.query(Attachment).filter(Attachment.transaction_id == transaction_id).count()
    if count >= MAX_ATTACHMENTS_PER_TRANSACTION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximal {MAX_ATTACHMENTS_PER_TRANSACTION} Belege pro Transaktion",
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    data = await read_upload_limited(
        file, max_bytes, f"Datei zu groß (max. {settings.MAX_UPLOAD_SIZE_MB} MB)"
    )
    if not data:
        raise HTTPException(status_code=400, detail="Leere Datei")

    content_type = detect_content_type(data)
    if content_type is None:
        raise HTTPException(status_code=400, detail="Nur PDF-, PNG- oder JPG-Dateien erlaubt")

    stored_name = store_file(data, content_type)

    attachment = Attachment(
        transaction_id=transaction_id,
        user_id=current_user.id,
        filename=sanitize_filename(file.filename),
        content_type=content_type,
        size_bytes=len(data),
        stored_name=stored_name,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    log_data_event(
        "create", user_id=current_user.id, resource="attachment",
        resource_id=attachment.id,
        detail=f"transaction_id={transaction_id} type={content_type} size={len(data)}",
    )

    return attachment


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Beleg abrufen (inline: PDF/Bild öffnet im Browser-Tab)"""
    attachment = db.query(Attachment).filter(
        Attachment.id == attachment_id,
        Attachment.user_id == current_user.id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    path = file_path(attachment.stored_name)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Beleg-Datei nicht gefunden")

    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.filename,
        content_disposition_type="inline",
    )


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Beleg löschen (DB-Eintrag + Datei)"""
    attachment = db.query(Attachment).filter(
        Attachment.id == attachment_id,
        Attachment.user_id == current_user.id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    delete_file(attachment.stored_name)
    db.delete(attachment)
    db.commit()

    log_data_event(
        "delete", user_id=current_user.id, resource="attachment",
        resource_id=attachment_id, detail=f"transaction_id={attachment.transaction_id}",
    )

    return {"message": "Beleg gelöscht"}
