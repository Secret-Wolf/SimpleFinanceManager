"""Erzeugt aus der offiziellen FinTS-Bankenliste der Deutschen Kreditwirtschaft
eine schlanke ``banks.json`` für die Bank-Suche (Name/Ort/BLZ -> BLZ + FinTS-URL).

Die Quell-CSV (``fints_institute ... Master.csv``) ist die DK-Bankenliste, die
Produkt-Registranten per E-Mail erhalten. Sie ist NICHT Teil des Repos
(Urheberrecht DK); nur die hieraus erzeugte ``banks.json`` wird ins Image gebacken
und ist per .gitignore vom Git-Tracking ausgenommen.

Aufruf (aus repo root, venv aktiv):
    python backend/scripts/build_bank_directory.py "C:/Pfad/zur/fints_institute ... Master.csv"

Ohne Argument wird die Default-CSV neben diesem Skript bzw. im Download-Ordner gesucht.
"""

import csv
import json
import sys
from pathlib import Path

# Spaltenindizes der DK-CSV (0-basiert); siehe Header der Quelldatei
COL_BLZ = 1
COL_BIC = 2
COL_NAME = 3
COL_ORT = 4
COL_URL = 24  # "PIN/TAN-Zugang URL"

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "bankdir" / "banks.json"


def build(csv_path: Path) -> int:
    seen = set()  # BLZ
    banks = []

    # Die DK-Liste ist Windows-kodiert (cp1252) und semikolon-getrennt.
    with open(csv_path, encoding="cp1252", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader, None)  # Header überspringen
        for row in reader:
            if len(row) <= COL_URL:
                continue
            url = row[COL_URL].strip()
            blz = row[COL_BLZ].strip()
            if not url or not blz:
                continue
            if blz in seen:  # eine Bank pro BLZ (Filialzeilen teilen die BLZ)
                continue
            seen.add(blz)
            banks.append({
                "blz": blz,
                "name": row[COL_NAME].strip(),
                "ort": row[COL_ORT].strip(),
                "bic": row[COL_BIC].strip(),
                "url": url,
            })

    banks.sort(key=lambda b: b["blz"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(banks, f, ensure_ascii=False, separators=(",", ":"))

    return len(banks)


def _find_default_csv() -> Path | None:
    candidates = [
        Path.home() / "Downloads" / "fints_institute NEU mit BIC Master.csv",
        Path(__file__).resolve().parent / "fints_institute NEU mit BIC Master.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = _find_default_csv()
        if not csv_path:
            print("Quell-CSV nicht gefunden. Pfad als Argument angeben.", file=sys.stderr)
            sys.exit(1)

    count = build(csv_path)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"{count} Banken -> {OUTPUT} ({size_kb:.0f} KB)")
