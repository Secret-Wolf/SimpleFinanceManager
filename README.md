# Finanzmanager

Eine selbst-gehostete Webanwendung zum Verwalten von Banktransaktionen. Importiere CSV-Exporte von deutschen Banken (Volksbank/Atruvia), kategorisiere Transaktionen und behalte den Überblick über deine Finanzen.

## Screenshots

### Dashboard
![Dashboard](Bilder/Finanzmanager%20Dashboard.jpg)

### Transaktionen
![Transaktionen](Bilder/Finanzmanager%20Transaktionen%20Default.jpg)

![Transaktionen mit Filtern](Bilder/Finanzmanager%20Transaktionen%20Datum+Kategorie.jpg)

### Kategorien
![Kategorien](Bilder/Finanzmanager%20Kategorien.jpg)

### Regeln
![Regeln](Bilder/Finanzmanager%20Regeln.jpg)

### Statistiken
![Statistiken](Bilder/Finanzmanager%20Statistiken%20Default.jpg)

![Statistiken mit Zeitraum](Bilder/Finanzmanager%20Statistiken%20Zeitraum.jpg)

## Features

- **CSV-Import** - Drag & Drop Import von Volksbank/Atruvia CSV-Dateien
- **Automatische Duplikaterkennung** - Bereits importierte Transaktionen werden übersprungen
- **Kategorisierung** - Hierarchische Kategorien (2 Ebenen) mit Farbcodes und optionalem Monatsbudget
- **Automatische Regeln** - Transaktionen automatisch kategorisieren lassen
- **Splitbuchungen** - Eine Transaktion auf mehrere Kategorien aufteilen
- **Notizen** - Eigene Notizen zu Transaktionen hinzufügen
- **Dashboard** - Übersicht über Kontostand, Einnahmen/Ausgaben, Top-Kategorien
- **Statistiken** - Ausgaben nach Kategorie, Zeitverläufe, CSV-Export
- **Flexible Zeiträume** - Woche, Monat, Quartal, Jahr, "Seit letztem Gehalt" oder eigener Zeitraum
- **Deutsches Format** - Beträge in 1.234,56 € Format

## Installation

### Option 1: Docker (empfohlen)

#### Voraussetzungen
- Docker
- Docker Compose (optional, aber empfohlen)

#### Mit Docker Compose

1. **Repository klonen:**
   ```bash
   git clone https://github.com/Secret-Wolf/SimpleFinanceManager.git
   cd SimpleFinanceManager
   ```

2. **Datenverzeichnis vorbereiten:**
   ```bash
   mkdir -p data
   # Falls du eine bestehende DB hast, kopiere sie nach data/finanzmanager.db
   ```

3. **Image bauen und starten:**
   ```bash
   docker compose up -d
   ```

4. **Im Browser öffnen:**
   ```
   http://localhost:8000
   ```

#### Mit eigener Docker Registry

Falls du eine eigene Registry hast (z.B. `192.168.178.30:5000`):

```bash
# Image bauen
docker build -t finanzmanager:latest .

# Image taggen für Registry
docker tag finanzmanager:latest 192.168.178.30:5000/finanzmanager:latest

# In Registry pushen
docker push 192.168.178.30:5000/finanzmanager:latest

# Auf dem Zielserver: Container starten
docker compose up -d
```

#### Bestehende Datenbank übernehmen

Die Datenbank wird als Volume gemountet (`./data:/app/data`). Kopiere deine bestehende `finanzmanager.db` einfach in den `data/` Ordner, bevor du den Container startest.

---

### Option 2: Lokale Installation

#### Voraussetzungen

- Python 3.10 oder höher
- pip (Python Package Manager)

#### Setup

1. **Repository klonen:**
   ```bash
   git clone https://github.com/Secret-Wolf/SimpleFinanceManager.git
   cd SimpleFinanceManager
   ```

2. **In das Backend-Verzeichnis wechseln:**
   ```bash
   cd backend
   ```

3. **Virtuelle Umgebung erstellen (empfohlen):**
   ```bash
   python -m venv venv

   # Windows:
   venv\Scripts\activate

   # Linux/Mac:
   source venv/bin/activate
   ```

4. **Abhängigkeiten installieren:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Server starten:**
   ```bash
   python run.py
   ```

6. **Im Browser öffnen:**
   ```
   http://localhost:8000
   ```

## Verwendung

### Erster Start

Beim ersten Start werden automatisch Standardkategorien erstellt. Falls nicht, klicke auf "Standardkategorien erstellen" in der Kategorieverwaltung.

### CSV importieren

1. Gehe zu **Import** in der Seitenleiste
2. Ziehe deine CSV-Datei in den Upload-Bereich (oder klicke zum Auswählen)
3. Der Import zeigt an:
   - Anzahl neu importierter Transaktionen
   - Anzahl übersprungener Duplikate
   - Eventuelle Fehler

### Transaktionen kategorisieren

**Manuell:**
- In der Transaktionsliste direkt die Kategorie per Dropdown ändern

**Per Regel (automatisch):**
1. Klicke auf eine Transaktion → Details → "Regel erstellen"
2. Wähle das Matching-Kriterium (Empfängername, IBAN, etc.)
3. Wähle die Kategorie
4. Alle zukünftigen Imports werden automatisch kategorisiert

**Bulk-Kategorisierung:**
1. Mehrere Transaktionen mit Checkbox auswählen
2. Kategorie wählen und "Kategorie zuweisen" klicken

### Regeln anwenden

Unter **Regeln** → "Regeln anwenden" werden alle aktiven Regeln auf unkategorisierte Transaktionen angewendet.

### Splitbuchungen

Für Transaktionen, die mehrere Kategorien betreffen (z.B. Supermarkteinkauf mit Haushaltswaren):

1. Transaktion anklicken → Details
2. "Aufteilen" klicken
3. Beträge und Kategorien für jeden Teil eingeben
4. Die Summe muss dem Originalbetrag entsprechen

### Statistiken

Die Statistik-Seite bietet verschiedene Zeiträume:
- **Dieser Monat / Letzter Monat** - Monatsübersicht
- **Dieses Quartal / Dieses Jahr** - Längere Zeiträume
- **Seit letztem Gehalt** - Automatische Erkennung des letzten Gehaltseingangs
- **Eigener Zeitraum** - Frei wählbarer Start- und Endzeitraum

## Tastaturkürzel

| Taste | Funktion |
|-------|----------|
| `i` | Import-Seite öffnen |
| `f` | Suchfeld fokussieren (auf Transaktionsseite) |
| `Esc` | Modal schließen |

## Datenbank

Die Datenbank ist eine SQLite-Datei unter:
```
data/finanzmanager.db
```

### Backup

Einfach die Datei `finanzmanager.db` kopieren. Fertig!

### Zurücksetzen

Datenbank löschen und Server neu starten:
```bash
del data\finanzmanager.db   # Windows
rm data/finanzmanager.db    # Linux/Mac
python run.py
```

## Projektstruktur

```
SimpleFinanceManager/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI App
│   │   ├── database.py       # SQLite Verbindung
│   │   ├── models.py         # Datenbank-Modelle
│   │   ├── schemas.py        # API-Schemas
│   │   ├── routers/          # API-Endpunkte
│   │   └── services/         # Business-Logik
│   ├── requirements.txt
│   └── run.py                # Startskript
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/                   # JavaScript-Module
├── data/
│   └── finanzmanager.db      # SQLite Datenbank
├── Bilder/                   # Screenshots
└── README.md
```

## Unterstützte CSV-Formate

Aktuell wird das **Volksbank/Atruvia**-Format unterstützt. Der CSV-Parser kann leicht für andere Banken erweitert werden - siehe `backend/app/services/csv_parser.py`.

### Volksbank / Atruvia

Semikolon-getrennt, UTF-8 (mit BOM). Spalten:

- Bezeichnung Auftragskonto
- IBAN Auftragskonto
- BIC Auftragskonto
- Bankname Auftragskonto
- Buchungstag (DD.MM.YYYY)
- Valutadatum
- Name Zahlungsbeteiligter
- IBAN Zahlungsbeteiligter
- BIC (SWIFT-Code) Zahlungsbeteiligter
- Buchungstext
- Verwendungszweck
- Betrag (-123,45)
- Waehrung
- Saldo nach Buchung
- Kategorie
- Glaeubiger ID
- Mandatsreferenz

## API-Dokumentation

Die API-Dokumentation ist verfügbar unter:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Troubleshooting

### "Port already in use"

Ein anderer Prozess nutzt Port 8000. Entweder:
- Den anderen Prozess beenden
- Oder in `run.py` den Port ändern

### Import schlägt fehl

- Prüfe, ob die CSV-Datei im Volksbank-Format ist
- Datei muss `.csv` Endung haben
- Encoding sollte UTF-8 sein (mit oder ohne BOM)

### Kategorien werden nicht angezeigt

Auf der Kategorien-Seite "Standardkategorien erstellen" klicken.

## Lizenz

MIT License - siehe [LICENSE](LICENSE) für Details.
