# Bank-Verzeichnis (FinTS-Bankenliste)

`banks.json` enthält pro deutscher Bank mit FinTS-Zugang: BLZ, Name, Ort, BIC
und FinTS-URL. Sie versorgt die Bank-Suche beim Anlegen einer Online-Banking-
Verbindung (Name/Ort/BLZ eingeben → BLZ + FinTS-URL werden automatisch gefüllt).

## Wichtig: `banks.json` ist NICHT im Git-Repo

Die Datei wird aus der **offiziellen FinTS-Bankenliste der Deutschen
Kreditwirtschaft** erzeugt. Diese Liste erhalten nur registrierte Produkteigner
(per E-Mail mit der FinTS-Produktregistrierung) und darf nicht öffentlich
weiterverteilt werden. Deshalb ist `banks.json` in `.gitignore`.

Beim lokalen `docker build` liegt die Datei im Build-Context und wird ins Image
gebacken — sie muss also vor dem Build erzeugt werden. Fehlt sie, läuft die App
trotzdem: Die Bank-Suche liefert dann keine Treffer und BLZ/URL werden manuell
eingegeben (Fallback).

## Neu erzeugen / aktualisieren

```bash
# aus repo root, venv aktiv; Pfad zur aktuellen DK-CSV angeben
python backend/scripts/build_bank_directory.py "/Pfad/zu/fints_institute ... Master.csv"
```

Die DK verschickt aktualisierte Listen unregelmäßig per E-Mail an den Verteiler.
Bei Änderungen einfach neu erzeugen und das Image neu bauen/pushen.

## Vor einem Open-Source-Release

Für ein öffentliches Repo muss die Datenquelle geklärt/ersetzt werden (z. B.
frei lizenzierte Bundesbank-BLZ-Datei + eigene BLZ→URL-Zuordnung), da die
DK-Liste nicht öffentlich verteilt werden darf.
