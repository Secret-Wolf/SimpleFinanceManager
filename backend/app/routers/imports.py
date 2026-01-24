from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..models import Import
from ..services.csv_parser import import_csv, SUPPORTED_FORMATS
from ..services.categorizer import apply_rules_to_uncategorized
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
    db: Session = Depends(get_db)
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

    # Read file content
    try:
        content = await file.read()

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
            detail=f"Fehler beim Lesen der Datei: {str(e)}"
        )

    # Import CSV
    try:
        import_result = import_csv(db, content_str, file.filename, bank_format)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Import fehlgeschlagen: {str(e)}"
        )

    # Auto-categorize new transactions
    if auto_categorize and import_result.transactions_new > 0:
        apply_rules_to_uncategorized(db)

    return import_result


@router.get("", response_model=List[schemas.ImportResult])
def get_imports(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get import history"""
    imports = db.query(Import).order_by(
        Import.import_date.desc()
    ).limit(limit).all()

    return imports


@router.get("/{import_id}", response_model=schemas.ImportResult)
def get_import(import_id: int, db: Session = Depends(get_db)):
    """Get single import record"""
    import_record = db.query(Import).filter(Import.id == import_id).first()

    if not import_record:
        raise HTTPException(status_code=404, detail="Import nicht gefunden")

    return import_record
