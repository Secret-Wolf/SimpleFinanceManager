from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..audit import log_data_event
from ..database import get_db
from ..auth import get_current_user
from ..models import Import, User
from ..services.csv_parser import import_csv, SUPPORTED_FORMATS
from ..services.categorizer import apply_rules_to_uncategorized
from ..config import settings
from .. import schemas

router = APIRouter(prefix="/api/import", tags=["import"])


@router.get("/formats")
def get_supported_formats():
    """Get list of supported bank formats"""
    return {
        "formats": [
            {"id": "auto", "name": "Automatisch erkennen", "description": "Format wird automatisch erkannt"},
            {"id": "volksbank", "name": "Volksbank / VR-Bank", "description": "Atruvia CSV-Export"},
            {"id": "ing", "name": "ING", "description": "ING Umsatzanzeige CSV"},
        ]
    }


@router.post("", response_model=schemas.ImportResult)
async def upload_csv(
    file: UploadFile = File(...),
    bank_format: str = Query(default="auto", description="Bank format: auto, volksbank, ing"),
    auto_categorize: bool = True,
    profile_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and import CSV file"""
    # Validate bank format
    if bank_format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekanntes Bankformat: {bank_format}. Unterstützt: {', '.join(SUPPORTED_FORMATS)}"
        )

    # Check file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Nur CSV-Dateien werden unterstützt"
        )

    # Read file content with size limit
    try:
        content = await file.read()
        max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Datei zu groß. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
            )

        # Try different encodings
        for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                content_str = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(
                status_code=400,
                detail="Datei-Encoding konnte nicht erkannt werden"
            )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Fehler beim Lesen der Datei"
        )

    # Import CSV
    try:
        import_result = import_csv(db, content_str, file.filename, bank_format, profile_id=profile_id, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Import fehlgeschlagen"
        )

    log_data_event(
        "csv_import",
        user_id=current_user.id,
        resource="import",
        detail=f"file={file.filename} format={bank_format} new={import_result.transactions_new} duplicates={import_result.transactions_duplicate}",
    )

    # Auto-categorize new transactions
    if auto_categorize and import_result.transactions_new > 0:
        apply_rules_to_uncategorized(db)

    return import_result


@router.get("", response_model=List[schemas.ImportResult])
def get_imports(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get import history"""
    imports = db.query(Import).filter(
        Import.user_id == current_user.id
    ).order_by(
        Import.import_date.desc()
    ).limit(limit).all()

    return imports


@router.get("/{import_id}", response_model=schemas.ImportResult)
def get_import(import_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get single import record"""
    import_record = db.query(Import).filter(
        Import.id == import_id,
        Import.user_id == current_user.id,
    ).first()

    if not import_record:
        raise HTTPException(status_code=404, detail="Import nicht gefunden")

    return import_record
