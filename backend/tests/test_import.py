"""CSV import + duplicate detection for both supported bank formats."""

VOLKSBANK_CSV = (
    "Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;Bankname Auftragskonto;"
    "Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;"
    "BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;Waehrung;"
    "Saldo nach Buchung;Kategorie;Glaeubiger ID;Mandatsreferenz\n"
    "Mein Konto;DE00111122223333444455;GENODEF1XXX;Meine VB;01.04.2026;01.04.2026;REWE;DE99;XXXX;"
    "Lastschrift;Einkauf;-12,34;EUR;1000,00;;;\n"
    "Mein Konto;DE00111122223333444455;GENODEF1XXX;Meine VB;02.04.2026;02.04.2026;Arbeitgeber;DE12;YYYY;"
    "Gutschrift;Gehalt;2500,00;EUR;3500,00;;;\n"
)

ING_CSV = (
    "Umsatzanzeige;Datei erstellt am: 01.04.2026\n"
    "IBAN;DE75 5001 0517 5456 5425 61\n"
    "Kontoname;Girokonto\n"
    "Bank;ING\n"
    "Kunde;Max\n"
    ";\n"
    "Buchung;Wertstellungsdatum;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Betrag\n"
    "03.04.2026;03.04.2026;EDEKA;Lastschrift;Lebensmittel;900,00;-25,00\n"
)


def _upload(api, content: str, fmt="auto"):
    return api.post(f"/api/import?bank_format={fmt}",
                    files={"file": ("export.csv", content.encode("utf-8"), "text/csv")})


def test_volksbank_import_creates_account_and_transactions(admin):
    r = _upload(admin, VOLKSBANK_CSV)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transactions_new"] == 2
    assert body["transactions_duplicate"] == 0

    accounts = admin.get("/api/accounts").json()
    assert any(a["iban"] == "DE00111122223333444455" for a in accounts)
    assert admin.get("/api/transactions").json()["total"] == 2


def test_reimport_is_fully_deduplicated(admin):
    _upload(admin, VOLKSBANK_CSV)
    second = _upload(admin, VOLKSBANK_CSV).json()
    assert second["transactions_new"] == 0
    assert second["transactions_duplicate"] == 2
    assert admin.get("/api/transactions").json()["total"] == 2  # still only 2


def test_ing_format_autodetected(admin):
    r = _upload(admin, ING_CSV)
    assert r.status_code == 200, r.text
    assert r.json()["transactions_new"] == 1
    accounts = admin.get("/api/accounts").json()
    assert any(a["iban"] == "DE75500105175456542561" for a in accounts)  # IBAN spaces stripped


def test_non_csv_rejected(admin):
    r = admin.post("/api/import", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
