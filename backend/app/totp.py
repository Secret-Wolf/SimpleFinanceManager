"""TOTP-Zwei-Faktor-Authentifizierung (RFC 6238) — Helfer rund um pyotp.

Das TOTP-Secret liegt (wie der bcrypt-Passwort-Hash) in der Datenbank; die
Recovery-Codes werden nur als SHA256-Hashes gespeichert und genau einmal im
Klartext an den Benutzer ausgegeben. Replay-Schutz: der Zeitfenster-Zähler des
zuletzt akzeptierten Codes wird gespeichert und ältere/gleiche Fenster werden
abgelehnt (ein abgefangener Code ist damit nach Benutzung wertlos).
"""

import hashlib
import hmac
import json
import secrets
import time
from typing import List, Optional, Tuple

import pyotp
import qrcode
import qrcode.image.svg

TOTP_ISSUER = "Finanzmanager"
TOTP_PERIOD = 30
RECOVERY_CODE_COUNT = 8
# Alphabet ohne verwechselbare Zeichen (0/O, 1/I/L)
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=TOTP_ISSUER)


def qr_svg(uri: str) -> str:
    """QR-Code als eigenständiges SVG (kein Pillow nötig, CSP-konform inline einsetzbar)."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=12)
    return img.to_string(encoding="unicode")


def verify_totp(secret: str, code: str, last_counter: Optional[int]) -> Tuple[str, Optional[int]]:
    """Prüft einen TOTP-Code gegen das aktuelle Zeitfenster (±1 Fenster Toleranz).

    Rückgabe: ("ok", counter) bei Erfolg, ("used", None) wenn der Code korrekt,
    aber sein Zeitfenster bereits verbraucht ist (Replay), sonst ("invalid", None).
    """
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return ("invalid", None)

    totp = pyotp.TOTP(secret)
    current_counter = int(time.time()) // TOTP_PERIOD

    for offset in (0, -1, 1):
        counter = current_counter + offset
        if hmac.compare_digest(totp.at(counter * TOTP_PERIOD), code):
            if last_counter is not None and counter <= last_counter:
                return ("used", None)
            return ("ok", counter)
    return ("invalid", None)


def _normalize_recovery(code: str) -> str:
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def _hash_recovery(code: str) -> str:
    return hashlib.sha256(_normalize_recovery(code).encode("utf-8")).hexdigest()


def generate_recovery_codes() -> Tuple[List[str], str]:
    """Erzeugt Einmal-Recovery-Codes. Rückgabe: (Klartext-Liste, JSON der Hashes)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    hashes = [_hash_recovery(c) for c in codes]
    return codes, json.dumps(hashes)


def use_recovery_code(stored_json: Optional[str], code: str) -> Optional[str]:
    """Verbraucht einen Recovery-Code. Rückgabe: neues JSON ohne den benutzten
    Code — oder None, wenn der Code nicht (mehr) gültig ist."""
    if not stored_json:
        return None
    try:
        hashes = json.loads(stored_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(hashes, list):
        return None

    code_hash = _hash_recovery(code)
    matched = False
    remaining = []
    for h in hashes:
        # Konstantzeit-Vergleich; jeder Code ist nur einmal benutzbar
        if not matched and isinstance(h, str) and hmac.compare_digest(h, code_hash):
            matched = True
            continue
        remaining.append(h)

    if not matched:
        return None
    return json.dumps(remaining)


def remaining_recovery_codes(stored_json: Optional[str]) -> int:
    if not stored_json:
        return 0
    try:
        hashes = json.loads(stored_json)
    except (ValueError, TypeError):
        return 0
    return len(hashes) if isinstance(hashes, list) else 0
