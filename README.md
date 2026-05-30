# Finanzmanager

Eine selbst-gehostete Webanwendung zum Verwalten von Banktransaktionen. Importiere CSV-Exporte deutscher Banken (Volksbank/Atruvia, ING), kategorisiere Transaktionen automatisch per Regeln und behalte – allein oder gemeinsam im Haushalt – den Überblick über deine Finanzen.

Mehrbenutzerfähig mit Login, strikter Datentrennung pro Benutzer und gemeinsamen Haushalts-Auswertungen. Backend: FastAPI + SQLite. Frontend: schlankes Vanilla-JavaScript ohne Build-Schritt.

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

### Transaktionen & Import
- **CSV-Import** – Drag & Drop von Volksbank/Atruvia- und ING-Exporten, Format wird automatisch erkannt
- **Automatische Duplikaterkennung** – Bereits importierte Buchungen werden übersprungen
- **Mehrere Konten** – Buchungen werden automatisch dem Konto (per IBAN) zugeordnet, globaler Kontofilter
- **Manuelle Einträge** – Bargeld, Geschenke o. Ä. ohne CSV erfassen
- **Splitbuchungen** – Eine Transaktion auf mehrere Kategorien aufteilen
- **Notizen** – Eigene Notizen zu Transaktionen
- **CSV-Export** – Gefilterte Transaktionen als CSV (Excel-kompatibel) herunterladen

### Kategorisierung
- **Hierarchische Kategorien** (2 Ebenen) mit Farbcodes und optionalem Monatsbudget
- **Automatische Regeln** – Buchungen nach Empfänger, IBAN, Verwendungszweck, Buchungsart oder Betrag kategorisieren; mit Priorität und Wildcard-/Regex-Mustern
- **Bulk-Aktionen** – Mehrere Buchungen gleichzeitig kategorisieren oder als „gemeinsam" markieren

### Auswertungen
- **Dashboard** – Kontostand, Einnahmen/Ausgaben des Monats inkl. Vergleich zum Vormonat, Top-Ausgaben, Anzahl unkategorisierter Buchungen
- **Statistiken** – Ausgaben nach Kategorie und Zeitverläufe
- **Flexible Zeiträume** – Woche, Monat, letzter Monat, Quartal, Jahr, „Seit letztem Gehalt" oder eigener Zeitraum
- **Deutsches Format** – Beträge als `1.234,56 €`, Daten als `TT.MM.JJJJ`

### Mehrbenutzer & Haushalt
- **Login & Benutzerverwaltung** – Erster registrierter Benutzer wird Admin; weitere Benutzer legt der Admin an
- **Strikte Datentrennung** – Jeder Benutzer sieht nur seine eigenen Konten, Buchungen, Kategorien und Regeln
- **Haushalte** – Benutzer per E-Mail einladen, gemeinsame Ausgaben markieren und über alle Haushaltsmitglieder hinweg auswerten (z. B. Kosten pro Person)
- **Dark Mode** – Umschaltbar im Benutzerprofil

### Sicherheit
- JWT in HttpOnly-Cookies (Access- + Refresh-Token), Passwörter mit bcrypt gehasht
- Passwort-Richtlinie (min. 12 Zeichen, Groß-/Kleinbuchstaben, Ziffer)
- Rate-Limiting (allgemein + verschärft beim Login), strenge Security-Header & Content-Security-Policy
- Strukturiertes Audit-Log sicherheitsrelevanter Ereignisse (`data/logs/audit.log`, IBANs maskiert)

## Installation

### Option 1: Docker (empfohlen)

#### Voraussetzungen
- Docker
- Docker Compose

#### A) LAN-Betrieb ohne HTTPS

Am einfachsten für den Heimgebrauch. Veröffentlicht den Port `8000` direkt.

1. **Repository klonen:**
   ```bash
   git clone https://github.com/Secret-Wolf/SimpleFinanceManager.git
   cd SimpleFinanceManager
   ```

2. **`SECRET_KEY` erzeugen** (einmalig, sicher aufbewahren):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

3. **Image bauen und starten:**
   ```bash
   docker build -t finanzmanager:latest .
   SECRET_KEY="dein-erzeugter-key" docker compose -f docker-compose.local.yml up -d
   ```

4. **Im Browser öffnen:** `http://<server-ip>:8000`

#### B) Externer Zugriff mit automatischem HTTPS (Traefik)

`docker-compose.yml` enthält einen Traefik-Reverse-Proxy mit Let's Encrypt. Vor dem Start anpassen:

- In `docker-compose.yml` `finance.deinedomain.de` durch deine Domain ersetzen
- `.env` anlegen (siehe unten) mit `SECRET_KEY`, `ACME_EMAIL`, `COOKIE_SECURE=true` und ggf. `ALLOWED_ORIGINS=https://deine-domain`

```bash
docker compose up -d
```

Der App-Container wird dabei nur intern `expose`d und ist ausschließlich über Traefik erreichbar.

#### Eigene Docker-Registry (optional)

Hast du eine eigene Registry im Netzwerk (z. B. `192.168.178.30:5000`), kannst du das Image dorthin pushen und auf dem Zielserver nur noch ziehen. In `docker-compose.yml` / `docker-compose.local.yml` ist als `image` bereits eine solche Registry-Adresse hinterlegt – passe sie an deine an.

```bash
docker build -t finanzmanager:latest .
docker tag finanzmanager:latest <registry-host>:5000/finanzmanager:latest
docker push <registry-host>:5000/finanzmanager:latest

# Auf dem Zielserver:
docker compose pull && docker compose up -d
```

> Eine HTTP-Registry muss in der Docker-Daemon-Konfiguration (`/etc/docker/daemon.json`) als `insecure-registries` eingetragen sein.

#### Bestehende Datenbank übernehmen

Die Datenbank wird als Volume gemountet (`./data:/app/data`). Kopiere deine vorhandene `finanzmanager.db` in den `data/`-Ordner, bevor du den Container startest. Schema-Migrationen laufen beim Start automatisch.

---

### Option 2: Lokale Installation

#### Voraussetzungen
- Python 3.10 oder höher
- pip

#### Setup

```bash
git clone https://github.com/Secret-Wolf/SimpleFinanceManager.git
cd SimpleFinanceManager/backend

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
python run.py
```

Im Browser öffnen: `http://localhost:8000`

> Ohne gesetztes `SECRET_KEY` wird beim ersten Start automatisch ein Schlüssel erzeugt und in `data/.secret_key` gespeichert (bleibt über Neustarts stabil). Für `DEBUG=true` (Auto-Reload + API-Dokumentation) die Umgebungsvariable vor dem Start setzen.

## Konfiguration (Umgebungsvariablen)

Für Docker eine `.env` neben der `docker-compose.yml` anlegen (Vorlage: [`.env.example`](.env.example)):

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `SECRET_KEY` | *(auto)* | JWT-Signaturschlüssel. In Production zwingend setzen. Wird sonst erzeugt und in `data/.secret_key` persistiert. |
| `DEBUG` | `false` | Auto-Reload und API-Docs unter `/api/docs`. In Production immer `false`. |
| `COOKIE_SECURE` | `false` | Auf `true` setzen, wenn die App hinter HTTPS läuft. |
| `ALLOWED_ORIGINS` | *(leer)* | Komma-separierte CORS-Origins. Leer = same-origin (LAN-Standard). |
| `ACME_EMAIL` | – | E-Mail für Let's Encrypt (nur Traefik). |
| `RATE_LIMIT_PER_MINUTE` | `100` | Allgemeines Anfrage-Limit pro IP. |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `5` | Limit für Login/Registrierung pro IP. |
| `MAX_UPLOAD_SIZE_MB` | `10` | Maximale Größe einer CSV-Datei. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Gültigkeit des Access-Tokens. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Gültigkeit des Refresh-Tokens. |

## Verwendung

### Erster Start

Beim ersten Aufruf erscheint die **Ersteinrichtung**: Lege das erste Benutzerkonto an – dieser Benutzer wird automatisch **Administrator**. Anschließend werden Standardkategorien erstellt. Weitere Benutzer können nur vom Admin unter **Benutzer** angelegt werden.

### CSV importieren

1. Gehe zu **Import** in der Seitenleiste
2. Wähle optional das Bankformat (Standard: automatisch erkennen)
3. Ziehe deine CSV-Datei in den Upload-Bereich (oder klicke zum Auswählen)
4. Das Ergebnis zeigt: neu importiert, übersprungene Duplikate und eventuelle Fehler. Neue Buchungen werden direkt anhand deiner Regeln kategorisiert.

### Transaktionen kategorisieren

- **Manuell:** In der Transaktionsliste die Kategorie per Dropdown ändern
- **Per Regel (automatisch):** Transaktion öffnen → „Regel erstellen", Kriterium (Empfängername, IBAN, …) und Kategorie wählen. Alle künftigen Importe werden automatisch zugeordnet.
- **Bulk:** Mehrere Buchungen per Checkbox auswählen und gemeinsam einer Kategorie zuweisen

Unter **Regeln** → „Regeln anwenden" werden alle aktiven Regeln auf unkategorisierte (optional auch bereits kategorisierte) Buchungen angewendet. Regel-Muster unterstützen einfaches Enthalten, Wildcards (`*` / `%`) und Regex (`/muster/i`).

### Splitbuchungen

Für Buchungen, die mehrere Kategorien betreffen (z. B. Supermarkteinkauf inkl. Haushaltswaren):

1. Transaktion öffnen → „Aufteilen"
2. Beträge und Kategorien je Teil eingeben (die Summe muss dem Originalbetrag entsprechen)

### Haushalt & gemeinsame Ausgaben

1. Unter **Haushalt** einen Haushalt anlegen und Mitglieder per E-Mail einladen (eingeladene Person muss ein Konto haben und die Einladung annehmen)
2. Gemeinsame Buchungen über die Detailansicht oder per Bulk-Aktion als „gemeinsam" markieren – Regeln können das ebenfalls automatisch setzen
3. Das Dashboard und die Haushalts-Auswertung zeigen gemeinsame Ausgaben sowie den Anteil pro Person

### Statistiken

Verschiedene Zeiträume: dieser/letzter Monat, Quartal, Jahr, **„Seit letztem Gehalt"** (erkennt den letzten Gehaltseingang über die Kategorie *Gehalt* bzw. Schlüsselwörter) oder ein eigener Zeitraum.

## Tastaturkürzel

| Taste | Funktion |
|-------|----------|
| `i` | Import-Seite öffnen |
| `f` | Suchfeld fokussieren (auf der Transaktionsseite) |
| `Esc` | Modal schließen |

## Datenbank

Die Datenbank ist eine SQLite-Datei unter `data/finanzmanager.db`.

- **Backup:** Einfach die Datei `finanzmanager.db` kopieren. Fertig.
- **Zurücksetzen:** Datenbank löschen und Server neu starten:
  ```bash
  del data\finanzmanager.db   # Windows
  rm data/finanzmanager.db    # Linux/Mac
  ```

Schemaänderungen werden beim Start automatisch über eingebaute Migrationen angewendet – eine alte DB wird also weiterverwendet, nicht überschrieben.

## Projektstruktur

```
SimpleFinanceManager/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI-App, Static-Hosting, Security-Header
│   │   ├── config.py         # Konfiguration via Environment Variables
│   │   ├── database.py       # SQLite-Verbindung (SQLAlchemy)
│   │   ├── models.py         # Datenbank-Modelle
│   │   ├── migrations.py     # Idempotente Schema-Migrationen (beim Start)
│   │   ├── schemas.py        # Pydantic-Schemas / Validierung
│   │   ├── auth.py           # JWT, Cookies, Passwort-Hashing
│   │   ├── audit.py          # Strukturiertes Audit-Logging
│   │   ├── routers/          # API-Endpunkte (auth, transactions, categories,
│   │   │                     #   rules, imports, stats, accounts, households)
│   │   └── services/         # Business-Logik (csv_parser, categorizer, statistics)
│   ├── requirements.txt
│   └── run.py                # Startskript (uvicorn)
├── frontend/                 # Vanilla-JS-SPA (kein Build-Schritt)
│   ├── index.html
│   ├── css/style.css
│   └── js/                   # api, auth, app, transactions, … (globale Module)
├── data/
│   └── finanzmanager.db      # SQLite-Datenbank (Volume)
├── Dockerfile
├── docker-compose.yml        # Production (Traefik + HTTPS)
├── docker-compose.local.yml  # LAN-Betrieb ohne HTTPS
└── Bilder/                   # Screenshots
```

## Unterstützte CSV-Formate

Das Format wird beim Import automatisch anhand der Kopfzeile erkannt. Weitere Banken lassen sich in [`backend/app/services/csv_parser.py`](backend/app/services/csv_parser.py) ergänzen.

### Volksbank / Atruvia
Semikolon-getrennt, UTF-8 (mit BOM). Relevante Spalten: Buchungstag (`TT.MM.JJJJ`), Name/IBAN/BIC Zahlungsbeteiligter, Buchungstext, Verwendungszweck, Betrag (`-123,45`), Saldo nach Buchung, Kategorie, Gläubiger-ID, Mandatsreferenz u. a.

### ING
Semikolon-getrennt. Kontodaten (IBAN, Kontoname, Bank) stehen im Kopfbereich; die Buchungstabelle beginnt ab der Spaltenzeile `Buchung;Wertstellungsdatum;…`.

## API-Dokumentation

Nur bei `DEBUG=true` aktiv:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

Health-Check (immer erreichbar, ohne Auth): `http://localhost:8000/api/health`

## Troubleshooting

**„Port already in use"** – Ein anderer Prozess nutzt Port 8000. Prozess beenden oder den Port anpassen (`backend/run.py` bzw. Compose-Datei).

**Import schlägt fehl** – Prüfe, ob die Datei eine `.csv` im Volksbank- oder ING-Format ist. Das Encoding wird automatisch erkannt (UTF-8 mit/ohne BOM, Latin-1, CP1252).

**Kategorien werden nicht angezeigt** – Auf der Kategorien-Seite „Standardkategorien erstellen" klicken. Kategorien sind benutzergebunden – jeder Benutzer hat seine eigenen.

**Login nicht möglich / Sitzung läuft ständig ab** – Hinter HTTPS muss `COOKIE_SECURE=true` gesetzt sein; ohne HTTPS muss es `false` sein, sonst werden die Auth-Cookies verworfen.

## Lizenz

MIT License – siehe [LICENSE](LICENSE) für Details.
