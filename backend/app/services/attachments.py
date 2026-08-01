"""Datei-Ablage für Belege (Attachments) zu Transaktionen.

Dateien liegen unter <data>/attachments/ mit zufälligem UUID-Dateinamen
(stored_name) — der Original-Dateiname wird nur in der DB (zur Anzeige)
gehalten. Der Datei-Typ wird über Magic Bytes bestimmt, nie über die
Datei-Endung oder den Client-Content-Type (kein HTML/Script-Upload möglich).
"""

import logging
import os
import re
import uuid
from typing import List, Optional

from ..config import settings
from ..models import Attachment

logger = logging.getLogger(__name__)

# Erlaubte Typen: Magic-Byte-Signatur -> (content_type, Datei-Endung)
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}

MAX_ATTACHMENTS_PER_TRANSACTION = 10

_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg)$")


def attachments_dir() -> str:
    """Ablage-Verzeichnis neben der SQLite-DB (folgt DATABASE_PATH, auch im Test)."""
    return os.path.join(os.path.dirname(os.path.abspath(settings.DATABASE_PATH)), "attachments")


def detect_content_type(data: bytes) -> Optional[str]:
    """Bestimmt den Typ ausschließlich über Magic Bytes (PDF/PNG/JPEG), sonst None."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def sanitize_filename(name: Optional[str]) -> str:
    """Original-Dateinamen für Anzeige/Download-Header entschärfen
    (keine Pfadanteile, keine Steuerzeichen/Quotes)."""
    base = os.path.basename(name or "").strip()
    base = re.sub(r'[\x00-\x1f"\\]', "_", base)
    return base[:255] or "beleg"


def store_file(data: bytes, content_type: str) -> str:
    """Schreibt die Datei und gibt den erzeugten stored_name zurück."""
    ext = ALLOWED_CONTENT_TYPES[content_type]
    stored_name = uuid.uuid4().hex + ext
    directory = attachments_dir()
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, stored_name), "wb") as f:
        f.write(data)
    return stored_name


def file_path(stored_name: str) -> Optional[str]:
    """Absoluter Pfad zu einer abgelegten Datei; None bei ungültigem stored_name
    (Format-Whitelist statt Pfad-Sanitizing — schließt Traversal aus)."""
    if not _STORED_NAME_RE.match(stored_name or ""):
        return None
    return os.path.join(attachments_dir(), stored_name)


def delete_file(stored_name: str) -> None:
    """Löscht die Datei von der Platte (best effort — DB-Konsistenz geht vor)."""
    path = file_path(stored_name)
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning(f"Attachment-Datei konnte nicht gelöscht werden ({stored_name}): {e}")


def delete_attachments_for_transactions(db, transaction_ids: List[int]) -> int:
    """Entfernt alle Attachment-Zeilen + Dateien der angegebenen Transaktionen.
    Muss VOR dem (Bulk-)Löschen der Transaktionen laufen. Kein commit hier —
    der Aufrufer committet seine Gesamtoperation."""
    if not transaction_ids:
        return 0
    rows = db.query(Attachment).filter(Attachment.transaction_id.in_(transaction_ids)).all()
    for row in rows:
        delete_file(row.stored_name)
        db.delete(row)
    return len(rows)
