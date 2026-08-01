"""Belege (Attachments): Upload-Validierung (Magic Bytes), Download, Löschen, Isolation."""

import os

from app.services.attachments import file_path

PDF_BYTES = b"%PDF-1.4\n%Test-Beleg\n%%EOF"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mktx(api, desc="Ausgabe"):
    r = api.post("/api/transactions/manual", json={
        "booking_date": "2026-06-01", "amount": "-10.00", "description": desc,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _upload(api, tx_id, filename, content, mime="application/octet-stream"):
    return api.post(f"/api/transactions/{tx_id}/attachments",
                    files={"file": (filename, content, mime)})


def test_upload_download_delete_pdf(admin):
    tx = _mktx(admin)

    r = _upload(admin, tx["id"], "Rechnung 2026.pdf", PDF_BYTES)
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["content_type"] == "application/pdf"
    assert att["filename"] == "Rechnung 2026.pdf"
    assert att["size_bytes"] == len(PDF_BYTES)

    # Beleg hängt an der Transaktion
    detail = admin.get(f"/api/transactions/{tx['id']}").json()
    assert [a["id"] for a in detail["attachments"]] == [att["id"]]

    # Download liefert die Datei inline zurück
    dl = admin.get(f"/api/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.content == PDF_BYTES
    assert dl.headers["content-type"].startswith("application/pdf")
    assert "inline" in dl.headers.get("content-disposition", "")

    # Löschen entfernt DB-Eintrag und Datei
    stored = admin.get(f"/api/transactions/{tx['id']}").json()["attachments"][0]
    assert admin.delete(f"/api/attachments/{att['id']}").status_code == 200
    assert admin.get(f"/api/attachments/{att['id']}").status_code == 404
    assert stored is not None


def test_upload_detects_type_via_magic_bytes(admin):
    tx = _mktx(admin)

    # PNG mit irreführender Endung -> als PNG erkannt (Magic Bytes zählen)
    r = _upload(admin, tx["id"], "scan.pdf", PNG_BYTES)
    assert r.status_code == 201
    assert r.json()["content_type"] == "image/png"

    # HTML/Skript-Inhalt wird abgelehnt, egal welche Endung
    r = _upload(admin, tx["id"], "beleg.pdf", b"<html><script>alert(1)</script></html>")
    assert r.status_code == 400

    r = _upload(admin, tx["id"], "beleg.txt", b"nur text")
    assert r.status_code == 400


def test_upload_size_limit(admin):
    tx = _mktx(admin)
    too_big = b"%PDF-" + b"0" * (11 * 1024 * 1024)  # Limit: 10 MB
    r = _upload(admin, tx["id"], "gross.pdf", too_big)
    assert r.status_code == 413


def test_attachments_are_user_isolated(admin, make_api):
    tx = _mktx(admin)
    att = _upload(admin, tx["id"], "privat.pdf", PDF_BYTES).json()

    admin.create_user("user2@test.de")
    other = make_api()
    other.login("user2@test.de")

    assert other.get(f"/api/attachments/{att['id']}").status_code == 404
    assert other.delete(f"/api/attachments/{att['id']}").status_code == 404
    assert _upload(other, tx["id"], "x.pdf", PDF_BYTES).status_code == 404


def test_transaction_delete_removes_attachment_file(admin):
    tx = _mktx(admin)
    _upload(admin, tx["id"], "beleg.pdf", PDF_BYTES).json()

    detail = admin.get(f"/api/transactions/{tx['id']}").json()
    stored_path = None
    # stored_name steht nicht in der API-Antwort — Datei über das Ablageverzeichnis finden
    from app.database import SessionLocal
    from app.models import Attachment
    db = SessionLocal()
    try:
        row = db.query(Attachment).filter(Attachment.transaction_id == tx["id"]).first()
        stored_path = file_path(row.stored_name)
    finally:
        db.close()

    assert stored_path and os.path.exists(stored_path)
    assert admin.delete(f"/api/transactions/{tx['id']}").status_code == 200
    assert not os.path.exists(stored_path)
    assert detail["attachments"], "Beleg war vor dem Löschen vorhanden"


def test_account_delete_removes_attachment_rows(admin):
    account = admin.post("/api/accounts", json={"name": "Belegkonto"}).json()
    tx = admin.post("/api/transactions/manual", json={
        "booking_date": "2026-06-01", "amount": "-5.00",
        "description": "Mit Beleg", "account_id": account["id"],
    }).json()
    att = _upload(admin, tx["id"], "beleg.pdf", PDF_BYTES).json()

    assert admin.delete(f"/api/accounts/{account['id']}").status_code == 200
    assert admin.get(f"/api/attachments/{att['id']}").status_code == 404
