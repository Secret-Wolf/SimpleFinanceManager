"""Bank-Verzeichnis: Suche nach Name/Ort/BLZ -> BLZ + FinTS-URL.

Liest die gebündelte ``bankdir/banks.json`` (aus der DK-FinTS-Bankenliste erzeugt,
siehe scripts/build_bank_directory.py) einmal lazy in den Speicher. Fehlt die Datei
(z. B. frisch geklontes OSS-Repo ohne die DK-Liste), liefert die Suche einfach keine
Treffer — die App bleibt voll nutzbar (BLZ/URL werden dann manuell eingegeben).
"""

import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bankdir", "banks.json")

_banks: Optional[List[dict]] = None
_loaded_path: Optional[str] = None


def _path() -> str:
    return os.environ.get("BANK_DIRECTORY_PATH", _DEFAULT_PATH)


def _load() -> List[dict]:
    """Lazy-load + cache. Reloads if the configured path changed (tests)."""
    global _banks, _loaded_path
    path = _path()
    if _banks is not None and _loaded_path == path:
        return _banks

    try:
        with open(path, encoding="utf-8") as f:
            _banks = json.load(f)
    except FileNotFoundError:
        logger.warning("Bank-Verzeichnis nicht gefunden (%s) — Bank-Suche liefert keine Treffer", path)
        _banks = []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Bank-Verzeichnis konnte nicht geladen werden (%s): %s", path, e)
        _banks = []

    _loaded_path = path
    return _banks


def reset_cache() -> None:
    """Cache leeren (für Tests, die eine andere Datei setzen)."""
    global _banks, _loaded_path
    _banks = None
    _loaded_path = None


def get_bank_by_blz(blz: str) -> Optional[dict]:
    """Exakter BLZ-Lookup (Leerzeichen werden ignoriert)."""
    blz = (blz or "").replace(" ", "").strip()
    if not blz:
        return None
    for bank in _load():
        if bank["blz"] == blz:
            return bank
    return None


def search_banks(query: str, limit: int = 15) -> List[dict]:
    """Sucht nach BLZ-Präfix oder Name/Ort (alle Suchwörter müssen vorkommen).

    Ranking: exakte BLZ > BLZ-Präfix > Name-Wortanfang > Name enthält > Ort enthält.
    """
    query = (query or "").strip().lower()
    if len(query) < 2:
        return []

    banks = _load()
    if not banks:
        return []

    # Reine Ziffern (ggf. mit Leerzeichen) -> BLZ-Präfixsuche
    digits = query.replace(" ", "")
    if digits.isdigit():
        scored = []
        for b in banks:
            if b["blz"] == digits:
                scored.append((0, b))
            elif b["blz"].startswith(digits):
                scored.append((1, b))
        scored.sort(key=lambda s: (s[0], s[1]["blz"]))
        return [b for _, b in scored[:limit]]

    # Text: alle Tokens müssen in Name+Ort vorkommen (UND-Verknüpfung)
    tokens = [t for t in query.split() if t]
    scored = []
    for b in banks:
        name = b["name"].lower()
        ort = b["ort"].lower()
        haystack = f"{name} {ort}"
        if not all(t in haystack for t in tokens):
            continue
        if name.startswith(query):
            rank = 0
        elif query in name:
            rank = 1
        elif all(t in name for t in tokens):
            rank = 2
        else:
            rank = 3  # nur über den Ort gematcht
        scored.append((rank, b["name"], b))

    scored.sort(key=lambda s: (s[0], s[1]))
    return [b for _, _, b in scored[:limit]]
