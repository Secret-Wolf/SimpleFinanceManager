# Plan: Multi-Bank Import & Multikonten-Übersicht

## Status: Fertig (inkl. Globaler Konto-Filter)

---

## Phase 1: ING CSV-Parser ✅ Fertig

### ING-Format Analyse
- **Header**: 13 Zeilen Metadaten vor Spaltenüberschriften
- **Zeile 3**: IBAN (Format: `DE75 5001 0517 5456 5425 61` mit Leerzeichen)
- **Zeile 5**: Bank (ING)
- **Zeile 8**: Aktueller Saldo
- **Zeile 14**: Spaltenüberschriften
- **Spalten**: `Buchung;Wertstellungsdatum;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Währung;Betrag;Währung`

### Aufgaben
- [x] ING Column-Mapping definieren
- [x] `parse_ing_csv()` Funktion erstellen
- [x] Header-Metadaten extrahieren (IBAN, Bank, etc.)
- [x] `detect_csv_format()` für ING erweitern

---

## Phase 2: Bank-Auswahl im Import ✅ Fertig

### Backend
- [x] Import-Endpoint um `bank_format` Parameter erweitern
- [x] Validierung des Formats
- [x] Auto-Detect als Fallback beibehalten
- [x] `/api/import/formats` Endpoint für verfügbare Formate

### Frontend
- [x] Dropdown für Bankauswahl im Import-Dialog
- [x] Optionen: "Automatisch erkennen", "Volksbank", "ING"

---

## Phase 3: Multikonten-Übersicht ✅ Fertig

### Backend API-Endpoints
- [x] `GET /api/accounts` - Liste aller Konten
- [x] `GET /api/accounts/summary` - Alle Konten mit Statistiken
- [x] `GET /api/accounts/{id}` - Einzelnes Konto mit Details
- [x] `PATCH /api/accounts/{id}` - Konto bearbeiten (Name, aktiv/inaktiv)

### Frontend
- [x] Neue Seite: Kontenübersicht
- [x] Kontostand pro Konto anzeigen
- [x] Gesamtvermögen berechnen
- [x] Bank-Icons und formatierte IBAN
- [x] Monatliche Ein-/Ausgaben pro Konto

---

## Technische Details

### Unterstützte Bankformate

| Bank | Format-ID | Erkennung |
|------|-----------|-----------|
| Volksbank/Atruvia | `volksbank` | `Bezeichnung Auftragskonto` in Zeile 1 |
| ING | `ing` | `Umsatzanzeige;Datei erstellt am` in Zeile 1 |

### ING Spalten-Mapping
```
Buchung -> booking_date
Wertstellungsdatum -> value_date
Auftraggeber/Empfänger -> counterpart_name
Buchungstext -> booking_type
Verwendungszweck -> purpose
Saldo -> balance_after
Währung (1) -> currency (für Saldo)
Betrag -> amount
Währung (2) -> currency (für Betrag)
```

### IBAN aus Header extrahieren
- Zeile 3: `IBAN;DE75 5001 0517 5456 5425 61`
- Leerzeichen entfernen für DB-Speicherung

---

## Implementierte Dateien

### Backend
- `backend/app/services/csv_parser.py` - ING Parser hinzugefügt
- `backend/app/routers/imports.py` - bank_format Parameter
- `backend/app/routers/accounts.py` - Neuer Router für Konten
- `backend/app/main.py` - accounts Router registriert

### Frontend
- `frontend/index.html` - Konten-Seite und Bank-Auswahl im Import
- `frontend/js/accounts.js` - Konten-Modul
- `frontend/js/api.js` - uploadCSV mit bankFormat Parameter
- `frontend/js/import.js` - Bank-Format Auswahl
- `frontend/js/app.js` - Accounts-Navigation
- `frontend/css/style.css` - Accounts-Styling

---

## Phase 4: Globaler Konto-Filter ✅ Fertig

### Backend
- [x] `GET /api/stats/summary` - account_id Parameter hinzugefügt
- [x] `GET /api/stats/by-category` - account_id Parameter hinzugefügt
- [x] `GET /api/stats/over-time` - account_id Parameter hinzugefügt
- [x] `GET /api/transactions` - account_id Parameter hinzugefügt
- [x] statistics.py Service-Funktionen um account_id erweitert

### Frontend
- [x] Globaler Konto-Selektor in Sidebar
- [x] `selectedAccountId` State-Variable
- [x] `onAccountFilterChange()` Funktion
- [x] Dashboard filtert nach Konto
- [x] Transaktionen filtern nach Konto
- [x] Statistiken filtern nach Konto
- [x] Konto-Dropdown wird nur bei >1 Konto angezeigt
