"""Datensicherung: SQLite-Backup herunterladen / wiederherstellen (nur Admin).

Das Backup ist ein konsistenter Snapshot der kompletten Datenbank (alle User!)
über die sqlite3-Backup-API. Restore ersetzt die laufende DB: vorher wird die
aktuelle DB als .pre-restore-Kopie gesichert, der Upload validiert
(SQLite-Header, integrity_check, Kerntabellen) und nach dem Tausch laufen die
Migrationen, damit auch ältere Backups auf den aktuellen Stand kommen.
"""

import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..audit import log_data_event
from ..auth import get_current_admin
from ..config import settings
from ..database import engine, get_db
from ..migrations import run_migrations
from ..models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])

_REQUIRED_TABLES = {"users", "accounts", "transactions", "categories"}
_MAX_RESTORE_SIZE_MB = 200


@router.get("/download")
def download_backup(current_user: User = Depends(get_current_admin)):
    """Komplette Datenbank als Datei herunterladen (konsistenter Snapshot)."""
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=db_dir)
    os.close(fd)

    try:
        src = sqlite3.connect(settings.DATABASE_PATH)
        try:
            dst = sqlite3.connect(tmp_path)
            with dst:
                src.backup(dst)
            dst.close()
        finally:
            src.close()
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.exception("Backup-Snapshot fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Backup fehlgeschlagen") from None

    log_data_event("backup_download", user_id=current_user.id, resource="database")

    filename = f"finanzmanager-backup-{date.today().isoformat()}.db"
    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(os.unlink, tmp_path),
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Datenbank aus einem Backup wiederherstellen. ERSETZT alle aktuellen Daten;
    die bisherige DB bleibt als .pre-restore-Kopie im data-Verzeichnis liegen."""
    content = await file.read()

    if len(content) > _MAX_RESTORE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Datei zu groß (max. {_MAX_RESTORE_SIZE_MB} MB)")

    if not content.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Keine gültige SQLite-Datenbankdatei")

    # Upload in eine Temp-Datei im selben Verzeichnis (für atomares os.replace)
    db_dir = os.path.dirname(settings.DATABASE_PATH)
    fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=db_dir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        # Validierung: Integrität + Kerntabellen vorhanden
        check = sqlite3.connect(tmp_path)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise HTTPException(status_code=400, detail="Datenbankdatei ist beschädigt (integrity_check)")
            tables = {r[0] for r in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            missing = _REQUIRED_TABLES - tables
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Kein Finanzmanager-Backup (fehlende Tabellen: {', '.join(sorted(missing))})"
                )
        finally:
            check.close()

        # Aktuelle DB sichern, Verbindungen schließen, Datei tauschen.
        # Wichtig (Windows): auch die Request-Session schließen — get_db ist pro
        # Request gecacht, d. h. `db` ist dieselbe Session wie die der Auth-Dependency;
        # eine offene Verbindung würde os.replace blockieren.
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_copy = f"{settings.DATABASE_PATH}.pre-restore-{timestamp}"
        shutil.copy2(settings.DATABASE_PATH, safety_copy)

        db.close()
        engine.dispose()
        # Verwaiste WAL/SHM-Dateien der alten DB dürfen die neue nicht "reparieren"
        for suffix in ("-wal", "-shm"):
            stale = settings.DATABASE_PATH + suffix
            if os.path.exists(stale):
                os.unlink(stale)
        os.replace(tmp_path, settings.DATABASE_PATH)

        # Älteres Backup ggf. auf aktuelles Schema heben
        run_migrations()
    except HTTPException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.exception("Restore fehlgeschlagen")
        raise HTTPException(status_code=500, detail="Wiederherstellung fehlgeschlagen") from None

    log_data_event(
        "backup_restore",
        user_id=current_user.id,
        resource="database",
        detail=f"file={file.filename} safety_copy={os.path.basename(safety_copy)}",
    )

    return {
        "message": "Datenbank wiederhergestellt. Bitte neu anmelden.",
        "safety_copy": os.path.basename(safety_copy),
    }
