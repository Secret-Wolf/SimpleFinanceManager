"""Umbuchungen (is_transfer), Budget-Auswertung und Backup/Restore."""

import io
import os
import sqlite3
import tempfile

_CSV_HEADER = (
    "Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;Bankname Auftragskonto;"
    "Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;"
    "BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;Waehrung;"
    "Saldo nach Buchung;Kategorie;Glaeubiger ID;Mandatsreferenz\n"
)

# Giro-Export: Einkauf (fremde IBAN) + Umbuchung aufs eigene Tagesgeld
GIRO_CSV = _CSV_HEADER + (
    "Giro;DE00111122223333444455;GENODEF1XXX;Meine VB;01.06.2026;01.06.2026;REWE;DE99000000000000000001;XXXX;"
    "Lastschrift;Einkauf;-25,00;EUR;975,00;;;\n"
    "Giro;DE00111122223333444455;GENODEF1XXX;Meine VB;02.06.2026;02.06.2026;Eigenuebertrag;DE00999988887777666655;XXXX;"
    "Ueberweisung;Sparen;-200,00;EUR;775,00;;;\n"
)

# Tagesgeld-Export: die Gegenbuchung (legt das zweite Konto an)
TAGESGELD_CSV = _CSV_HEADER + (
    "Tagesgeld;DE00999988887777666655;GENODEF1XXX;Meine VB;02.06.2026;02.06.2026;Eigenuebertrag;DE00111122223333444455;XXXX;"
    "Gutschrift;Sparen;200,00;EUR;200,00;;;\n"
)


def _upload(api, content):
    return api.post("/api/import?bank_format=auto",
                    files={"file": ("export.csv", content.encode("utf-8"), "text/csv")})


def test_transfer_detection_on_import_and_stats_exclusion(admin):
    """Import erkennt Umbuchungen automatisch — auch rückwirkend, sobald das
    Gegenkonto durch einen späteren Import entsteht. Statistiken ignorieren sie."""
    # 1) Nur Giro importiert: Tagesgeld-Konto existiert noch nicht -> keine Umbuchung erkennbar
    r = _upload(admin, GIRO_CSV)
    assert r.status_code == 200, r.text
    assert r.json()["transactions_new"] == 2
    assert admin.get("/api/transactions?transfers_only=true").json()["total"] == 0

    # 2) Tagesgeld importiert: beide Seiten werden markiert (die Giro-Seite rückwirkend)
    r = _upload(admin, TAGESGELD_CSV)
    assert r.status_code == 200, r.text
    assert r.json()["transactions_new"] == 1

    transfers = admin.get("/api/transactions?transfers_only=true").json()
    assert transfers["total"] == 2
    assert all(t["is_transfer"] for t in transfers["items"])

    # Statistik sieht nur den REWE-Einkauf (keine 200 € "Ausgabe"/"Einnahme")
    stats = admin.get(
        "/api/stats/by-category?period=custom&start_date=2026-06-01&end_date=2026-06-30"
    ).json()
    assert float(stats["total_expenses"]) == 25.0
    assert float(stats["total_income"]) == 0.0

    # Umbuchungen gelten nicht als unkategorisiert
    uncat = admin.get("/api/transactions?uncategorized_only=true").json()
    assert uncat["total"] == 1  # nur REWE

    # Erneuter Lauf erkennt nichts Neues
    assert admin.post("/api/transactions/detect-transfers").json()["detected_count"] == 0


def test_transfer_manual_toggle(admin):
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-06-01", "amount": "-50.00", "description": "Bar abgehoben"})
    tx = admin.get("/api/transactions").json()["items"][0]

    r = admin.patch(f"/api/transactions/{tx['id']}", json={"is_transfer": True})
    assert r.status_code == 200
    assert r.json()["is_transfer"] is True

    stats = admin.get(
        "/api/stats/by-category?period=custom&start_date=2026-06-01&end_date=2026-06-30"
    ).json()
    assert float(stats["total_expenses"]) == 0.0

    r = admin.patch(f"/api/transactions/{tx['id']}", json={"is_transfer": False})
    assert r.json()["is_transfer"] is False


def test_rules_skip_transfers(admin):
    cat = admin.post("/api/categories", json={"name": "Sparen"}).json()
    admin.post("/api/rules", json={"match_counterpart_name": "Eigen", "assign_category_id": cat["id"]})

    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-06-01", "amount": "-50.00", "description": "Eigenuebertrag"})
    tx = admin.get("/api/transactions").json()["items"][0]
    admin.patch(f"/api/transactions/{tx['id']}", json={"is_transfer": True})

    assert admin.post("/api/rules/apply").json()["categorized_count"] == 0


def test_budget_stats_with_subtree_rollup(admin):
    parent = admin.post("/api/categories",
                        json={"name": "Mobilität", "budget_monthly": "300.00"}).json()
    child = admin.post("/api/categories",
                       json={"name": "Tanken", "parent_id": parent["id"], "budget_monthly": "150.00"}).json()

    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-06-05", "amount": "-120.00", "description": "Aral",
                     "category_id": child["id"]})
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-06-06", "amount": "-30.00", "description": "Werkstatt",
                     "category_id": parent["id"]})

    stats = admin.get("/api/stats/budgets?year=2026&month=6").json()
    assert stats["year"] == 2026 and stats["month"] == 6

    by_name = {i["category_name"]: i for i in stats["items"]}
    # Parent: Teilbaum (120 + 30) gegen 300
    assert float(by_name["Mobilität"]["spent"]) == 150.0
    assert float(by_name["Mobilität"]["remaining"]) == 150.0
    assert float(by_name["Mobilität"]["percent"]) == 50.0
    # Kind: eigener Teilbaum gegen eigenes Budget
    assert float(by_name["Tanken"]["spent"]) == 120.0
    assert float(by_name["Tanken"]["percent"]) == 80.0

    # Gesamtzeile zählt das Kind-Budget nicht doppelt (liegt im budgetierten Parent)
    assert float(stats["total_budget"]) == 300.0
    assert float(stats["total_spent"]) == 150.0

    # Anderer Monat: Budget gelistet, aber nichts ausgegeben
    stats_jan = admin.get("/api/stats/budgets?year=2026&month=1").json()
    assert all(float(i["spent"]) == 0.0 for i in stats_jan["items"])


def test_budgets_are_user_scoped(make_api):
    usera = make_api()
    usera.register_admin("a@test.de")
    usera.create_user("b@test.de")
    userb = make_api()
    userb.login("b@test.de")

    usera.post("/api/categories", json={"name": "Essen", "budget_monthly": "400.00"})
    assert userb.get("/api/stats/budgets").json()["items"] == []


def test_backup_download_and_restore_roundtrip(admin):
    cat = admin.post("/api/categories", json={"name": "Supermarkt"}).json()
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-06-01", "amount": "-5.00", "description": "REWE",
                     "category_id": cat["id"]})

    # Download liefert eine gültige SQLite-Datei
    r = admin.get("/api/backup/download")
    assert r.status_code == 200
    backup_bytes = r.content
    assert backup_bytes.startswith(b"SQLite format 3\x00")

    # Daten ändern (Transaktion löschen) …
    tx = admin.get("/api/transactions").json()["items"][0]
    admin.delete(f"/api/transactions/{tx['id']}")
    assert admin.get("/api/transactions").json()["total"] == 0

    # … Restore bringt sie zurück
    r = admin.post("/api/backup/restore",
                   files={"file": ("backup.db", io.BytesIO(backup_bytes), "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert admin.get("/api/transactions").json()["total"] == 1


def test_backup_restore_rejects_invalid_files(admin):
    # Kein SQLite-Header
    r = admin.post("/api/backup/restore",
                   files={"file": ("evil.db", io.BytesIO(b"not a database"), "application/octet-stream")})
    assert r.status_code == 400

    # Echte SQLite-Datei, aber ohne Finanzmanager-Tabellen
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE foo (id INTEGER)")
        con.commit()
        con.close()
        with open(path, "rb") as f:
            foreign_db = f.read()
    finally:
        os.unlink(path)

    r = admin.post("/api/backup/restore",
                   files={"file": ("foreign.db", io.BytesIO(foreign_db), "application/octet-stream")})
    assert r.status_code == 400
    assert "Tabellen" in r.json()["detail"]


def test_backup_admin_only(make_api):
    usera = make_api()
    usera.register_admin("a@test.de")
    usera.create_user("b@test.de")
    userb = make_api()
    userb.login("b@test.de")

    assert userb.get("/api/backup/download").status_code == 403
    r = userb.post("/api/backup/restore",
                   files={"file": ("x.db", io.BytesIO(b"SQLite format 3\x00"), "application/octet-stream")})
    assert r.status_code == 403
