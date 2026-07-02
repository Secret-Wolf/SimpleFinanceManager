"""Gemeinsame Helfer für Datei-Uploads."""

from fastapi import HTTPException, UploadFile

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def read_upload_limited(file: UploadFile, max_bytes: int, detail: str) -> bytes:
    """Upload in Chunks lesen und bei Überschreitung sofort mit 413 abbrechen,
    statt erst den kompletten Body in den Speicher zu laden."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=detail)
        chunks.append(chunk)
    return b"".join(chunks)
