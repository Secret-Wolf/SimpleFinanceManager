"""FinTS / HBCI online-banking service (read-only).

Retrieves balances and transactions from German banks via the FinTS 3.0 protocol
(python-fints) and imports them into the existing transaction store, reusing the
CSV import's deduplication and account-linking so FinTS and CSV imports merge cleanly.

Security notes:
- The banking PIN is NEVER persisted. It is supplied per sync and only held in
  memory inside the transient pending-TAN store (RAM only, short TTL) for the
  duration of a TAN round-trip, then discarded.
- ``BankConnection.fints_system_data`` stores the serialized FinTS client state
  (``deconstruct``) for system-id continuity. It contains no credentials.
"""

import base64
import logging
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fints.client import FinTS3PinTanClient, NeedRetryResponse, NeedTANResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import BankConnection, Import, Transaction
from .categorizer import apply_rules_to_uncategorized
from .csv_parser import ensure_account_exists, generate_import_hash

logger = logging.getLogger(__name__)

# python-fints v4+ requires a product_id. Officially you register one (free) with the
# Deutsche Kreditwirtschaft and set FINTS_PRODUCT_ID. This neutral fallback lets the
# feature work with banks that don't enforce registration; banks that do will reject it
# with a clear error, prompting the user to register and set FINTS_PRODUCT_ID.
_FALLBACK_PRODUCT_ID = "SIMPLEFINANCEMANAGER"


class BankingError(Exception):
    """User-facing banking error with a clean German message."""


# --- Transient pending-TAN store (RAM only, never written to disk) -------------

_PENDING_TTL = 300  # seconds
_pending: dict = {}
_pending_lock = threading.Lock()


def _purge_expired():
    now = time.time()
    for token in [t for t, p in _pending.items() if p["expires"] < now]:
        _pending.pop(token, None)


def _store_pending(*, user_id: int, connection_id: int, pin: str, client_data: bytes,
                   dialog_data: bytes, tan_data: bytes, from_date: date) -> str:
    token = secrets.token_urlsafe(24)
    with _pending_lock:
        _purge_expired()
        _pending[token] = {
            "user_id": user_id,
            "connection_id": connection_id,
            "pin": pin,
            "client_data": client_data,
            "dialog_data": dialog_data,
            "tan_data": tan_data,
            "from_date": from_date,
            "expires": time.time() + _PENDING_TTL,
        }
    return token


def _get_pending(token: str, user_id: int) -> Optional[dict]:
    with _pending_lock:
        _purge_expired()
        p = _pending.get(token)
        if not p or p["user_id"] != user_id:
            return None
        return p


def _drop_pending(token: str):
    with _pending_lock:
        _pending.pop(token, None)


# --- Client construction & TAN bootstrap --------------------------------------

def _build_client(connection: BankConnection, pin: str, from_data: Optional[bytes] = None) -> FinTS3PinTanClient:
    kwargs = {
        "product_id": settings.FINTS_PRODUCT_ID or _FALLBACK_PRODUCT_ID,
    }
    if settings.FINTS_PRODUCT_VERSION:
        kwargs["product_version"] = settings.FINTS_PRODUCT_VERSION
    if from_data:
        kwargs["from_data"] = from_data
    return FinTS3PinTanClient(
        connection.bank_code,
        connection.login_name,
        pin,
        connection.fints_url,
        **kwargs,
    )


_SINGLE_STEP = "999"  # security function for the non-SCA "single step" mechanism


def _bootstrap_tan(client: FinTS3PinTanClient, connection: BankConnection):
    """Ensure a usable (SCA-capable) TAN mechanism/medium is selected before a dialog.

    For PSD2 banks (e.g. Atruvia/Volksbank) the system_id can only be obtained by
    completing SCA during dialog initialisation. python-fints' fetch_tan_mechanisms()
    then raises 'Could not find system_id' after its HKSYN sync — but it has already
    parsed the bank's TAN mechanisms (BPD) as a side effect, so we catch that and pick a
    real mechanism. The actual login TAN is handled via client.init_tan_response in the
    dialog (see start_sync)."""
    if client.selected_security_function in (None, "", _SINGLE_STEP):
        try:
            client.fetch_tan_mechanisms()
        except ValueError as e:
            if "system_id" not in str(e).lower():
                raise
            logger.info("Connection %s: system_id deferred to login SCA", connection.id)

        # fetch_tan_mechanisms internally selects '999'; force a real (SCA) mechanism.
        mechanisms = [(sf, p) for sf, p in client.get_tan_mechanisms().items() if str(sf) != _SINGLE_STEP]
        if client.selected_security_function in (None, "", _SINGLE_STEP) and mechanisms:
            client.set_tan_mechanism(_preferred_mechanism(mechanisms))

    # TAN medium (guarded: may be unavailable while system_id is still deferred)
    try:
        if client.selected_tan_medium is None and client.is_tan_media_required():
            media = client.get_tan_media()
            options = list(media[1]) if media and len(media) > 1 else []
            if options:
                client.set_tan_medium(options[0])
            else:
                client.selected_tan_medium = ""
    except Exception as e:
        logger.info("Connection %s: TAN media selection skipped (%s)", connection.id, e)

    # Persist the chosen method on the connection (best effort — purely informational)
    try:
        if client.selected_security_function:
            connection.tan_mechanism = str(client.selected_security_function)
        if client.selected_tan_medium:
            connection.tan_medium = str(client.selected_tan_medium)
    except Exception:  # nosec B110 - informational only; must never block a sync
        pass


def _preferred_mechanism(mechanisms):
    """Prefer an app/push/decoupled-style mechanism by name, else the first non-single-step."""
    keywords = ("push", "app", "secure", "photo", "decoupled", "best", "mobile")
    real = [(sf, p) for sf, p in mechanisms if str(sf) != _SINGLE_STEP] or list(mechanisms)
    for sec_func, param in real:
        name = (getattr(param, "name", "") or "").lower()
        if any(k in name for k in keywords):
            return sec_func
    return real[0][0]


# --- Transaction collection & import ------------------------------------------

def _default_from_date(from_date: Optional[date]) -> date:
    return from_date or (date.today() - timedelta(days=90))


def _run_collect(client: FinTS3PinTanClient, from_date: date):
    """Fetch SEPA accounts and their transactions. Returns ('tan', need) if a TAN
    is required, else ('done', (accounts, statements)). Safe to re-run after auth."""
    accounts = client.get_sepa_accounts()
    if isinstance(accounts, NeedTANResponse):
        return ("tan", accounts)

    end = date.today()
    statements = []
    for acc in accounts:
        tx = client.get_transactions(acc, from_date, end)
        if isinstance(tx, NeedTANResponse):
            return ("tan", tx)
        balance = None
        try:
            balance = client.get_balance(acc)
        except Exception:
            balance = None
        statements.append((acc, tx, balance))
    return ("done", (accounts, statements))


def _balance_amount(balance) -> Optional[Decimal]:
    try:
        amt = balance.amount
        return amt.amount if hasattr(amt, "amount") else Decimal(str(amt))
    except Exception:
        return None


def _import_statements(db: Session, connection: BankConnection, statements, user_id: int) -> dict:
    total = new = dup = err = 0
    account_ibans: List[str] = []

    for acc, txlist, balance in statements:
        iban = getattr(acc, "iban", None)
        bic = getattr(acc, "bic", None)
        account = ensure_account_exists(db, iban, name=connection.name, bic=bic,
                                        bank_name=connection.name, user_id=user_id)
        db.commit()
        if iban:
            account_ibans.append(iban)

        created = []  # (tx, booking_date)
        for t in txlist:
            d = getattr(t, "data", {}) or {}
            booking_date = d.get("date")
            amount_obj = d.get("amount")
            amount = getattr(amount_obj, "amount", None)
            total += 1
            if not booking_date or amount is None:
                err += 1
                continue

            row = {
                "booking_date": booking_date,
                "amount": amount,
                "counterpart_iban": d.get("applicant_iban"),
                "purpose": d.get("purpose"),
            }
            import_hash = generate_import_hash(row)

            existing = db.query(Transaction).filter(Transaction.import_hash == import_hash).first()
            if existing:
                dup += 1
                continue

            tx = Transaction(
                import_hash=import_hash,
                account_id=account.id if account else None,
                account_name=account.name if account else None,
                account_iban=iban,
                account_bic=bic,
                bank_name=connection.name,
                booking_date=booking_date,
                value_date=d.get("entry_date") or d.get("guessed_entry_date") or booking_date,
                counterpart_name=d.get("applicant_name"),
                counterpart_iban=d.get("applicant_iban"),
                counterpart_bic=d.get("applicant_bin"),
                booking_type=d.get("posting_text"),
                purpose=d.get("purpose"),
                amount=amount,
                currency=getattr(amount_obj, "currency", None) or "EUR",
            )
            db.add(tx)
            try:
                db.flush()
                new += 1
                created.append((tx, booking_date))
            except IntegrityError:
                db.rollback()
                dup += 1

        # Stamp the fetched closing balance onto the newest imported transaction
        # so the dashboard's "current balance" works for FinTS-only accounts.
        bal_value = _balance_amount(balance)
        if bal_value is not None and created:
            newest = max(created, key=lambda c: (c[1], c[0].id or 0))
            newest[0].balance_after = bal_value

    db.commit()

    status = "success" if err == 0 else ("partial" if new > 0 else "failed")
    db.add(Import(
        filename=f"FinTS: {connection.name}",
        transactions_total=total,
        transactions_new=new,
        transactions_duplicate=dup,
        transactions_error=err,
        status=status,
        user_id=user_id,
    ))
    db.commit()

    if new > 0:
        apply_rules_to_uncategorized(db, user_id)

    return {"imported": new, "duplicates": dup, "errors": err, "accounts": account_ibans}


# --- Persistence helpers ------------------------------------------------------

def _save_system_data(db: Session, connection: BankConnection, client_data: bytes):
    try:
        connection.fints_system_data = base64.b64encode(client_data).decode("ascii")
        db.commit()
    except Exception:
        db.rollback()


def _load_system_data(connection: BankConnection) -> Optional[bytes]:
    if not connection.fints_system_data:
        return None
    try:
        return base64.b64decode(connection.fints_system_data)
    except Exception:
        return None


def _tan_payload(need: NeedTANResponse, token: str) -> dict:
    """Build the API payload describing a required TAN."""
    challenge_image = None
    try:
        if getattr(need, "challenge_matrix", None):
            mime, data = need.challenge_matrix
            challenge_image = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        challenge_image = None

    return {
        "status": "tan_required",
        "job_id": token,
        "challenge": (getattr(need, "challenge", None) or "").strip() or
                     ("Bitte die Aktion in deiner Banking-App bestätigen." if getattr(need, "decoupled", False)
                      else "Bitte TAN eingeben."),
        "decoupled": bool(getattr(need, "decoupled", False)),
        "challenge_image": challenge_image,
    }


# --- Diagnostics: capture the bank's FinTS return codes (incl. internal sends) -----

def _attach_code_recorder(client: FinTS3PinTanClient) -> list:
    """Wrap the client's _process_response to record (code, text) of every bank response,
    including internal sends (system_id sync), which add_response_callback does not see."""
    codes: list = []
    orig = client._process_response

    def wrapper(dialog, segment, response):
        try:
            code = getattr(response, "code", None)
            if code:
                codes.append((str(code), (getattr(response, "text", "") or "")[:140]))
        except Exception:  # nosec B110 - diagnostics only; never disturb the real response flow
            pass
        return orig(dialog, segment, response)

    client._process_response = wrapper
    return codes


def _format_codes(codes: list) -> str:
    if not codes:
        return "(keine Antwortcodes erhalten)"
    seen = []
    for code, text in codes:
        entry = f"{code}: {text}".strip().rstrip(":").strip()
        if entry not in seen:
            seen.append(entry)
    return " | ".join(seen)


# --- Public entry points (called by the router) -------------------------------

def start_sync(db: Session, connection: BankConnection, pin: str, from_date: Optional[date]) -> dict:
    """Begin a sync. Returns a 'done' result or a 'tan_required' result."""
    from_date = _default_from_date(from_date)
    codes: list = []

    try:
        client = _build_client(connection, pin, from_data=_load_system_data(connection))
        codes = _attach_code_recorder(client)
        _bootstrap_tan(client, connection)
        db.commit()  # persist any tan_mechanism/medium choice

        need = None
        dialog_data = None
        payload = None
        with client:
            # PSD2: completing the login may itself require a TAN. This also assigns the
            # system_id, so it must be handled before any read operation.
            if getattr(client, "init_tan_response", None) is not None:
                need = client.init_tan_response
                dialog_data = client.pause_dialog()
            else:
                status, payload = _run_collect(client, from_date)
                if status == "tan":
                    need = payload
                    dialog_data = client.pause_dialog()

        client_data = client.deconstruct(including_private=True)
        _save_system_data(db, connection, client_data)

        if need is not None:
            token = _store_pending(
                user_id=connection.user_id, connection_id=connection.id, pin=pin,
                client_data=client_data, dialog_data=dialog_data,
                tan_data=need.get_data(), from_date=from_date,
            )
            return _tan_payload(need, token)

        _, statements = payload
        result = _import_statements(db, connection, statements, connection.user_id)
        connection.last_sync = datetime.utcnow()
        db.commit()
        return {"status": "done", **result}

    except BankingError:
        raise
    except Exception as e:
        logger.warning("FinTS start_sync failed for connection %s: %s | bank codes: %s",
                       connection.id, e, _format_codes(codes))
        raise BankingError(_friendly_error(e, codes)) from e


def resume_sync(db: Session, connection: BankConnection, token: str, tan: Optional[str]) -> dict:
    """Resume a paused sync after the user provided a TAN (or for decoupled polling)."""
    pending = _get_pending(token, connection.user_id)
    if not pending:
        raise BankingError("TAN-Vorgang abgelaufen oder ungültig. Bitte erneut abrufen.")

    client = _build_client(connection, pending["pin"], from_data=pending["client_data"])
    codes = _attach_code_recorder(client)
    need_obj = NeedRetryResponse.from_data(pending["tan_data"])

    try:
        still_need = None
        dialog_data = None
        collected = None

        with client.resume_dialog(pending["dialog_data"]):
            resp = client.send_tan(need_obj, tan or "")

            # Decoupled: poll a few times within this dialog before handing control back
            polls = 0
            while isinstance(resp, NeedTANResponse) and getattr(resp, "decoupled", False) and polls < 3:
                time.sleep(3)
                resp = client.send_tan(resp, "")
                polls += 1

            if isinstance(resp, NeedTANResponse) and getattr(resp, "decoupled", False):
                still_need = resp
                dialog_data = client.pause_dialog()
            else:
                # Authenticated now: collect everything fresh in this dialog.
                status, payload = _run_collect(client, pending["from_date"])
                if status == "tan":
                    raise BankingError(
                        "Diese Bank verlangt eine weitere TAN pro Umsatzabruf – in v1 nicht unterstützt."
                    )
                collected = payload

        client_data = client.deconstruct(including_private=True)
        _save_system_data(db, connection, client_data)

        if still_need is not None:
            # Update the pending entry for the next poll request (reuse the same token)
            with _pending_lock:
                if token in _pending:
                    _pending[token].update({
                        "client_data": client_data,
                        "dialog_data": dialog_data,
                        "tan_data": still_need.get_data(),
                        "expires": time.time() + _PENDING_TTL,
                    })
            return _tan_payload(still_need, token)

        _drop_pending(token)
        _, statements = collected
        result = _import_statements(db, connection, statements, connection.user_id)
        connection.last_sync = datetime.utcnow()
        db.commit()
        return {"status": "done", **result}

    except BankingError:
        raise
    except Exception as e:
        logger.warning("FinTS resume_sync failed for connection %s: %s | bank codes: %s",
                       connection.id, e, _format_codes(codes))
        _drop_pending(token)
        raise BankingError(_friendly_error(e, codes)) from e


def _friendly_error(e: Exception, codes: Optional[list] = None) -> str:
    msg = str(e) or e.__class__.__name__
    low = msg.lower()
    code_set = {c for c, _ in (codes or [])}

    if "connection" in low or "timed out" in low or "name or service" in low or "getaddrinfo" in low:
        return "Bankserver nicht erreichbar – FinTS-URL prüfen."
    if "9010" in code_set:
        return "Falsche Bank/FinTS-URL für diese BLZ (BPD-Fehler 9010) – URL prüfen (ggf. fints1 vs. fints2.atruvia.de)."
    if code_set & {"9078", "9079"}:
        return ("Die Bank verlangt eine registrierte FinTS-Produkt-ID (Code 9078). Bitte eine kostenlose "
                "Produkt-Registrierungsnummer bei der Deutschen Kreditwirtschaft beantragen "
                "(registrierung@hbci-zka.de) und als FINTS_PRODUCT_ID setzen. "
                "Volksbank/Atruvia erzwingt dies – ING meist nicht.")
    if code_set & {"9340", "9910", "9930", "9931", "9942"} or "pin" in low:
        return "Anmeldung fehlgeschlagen – PIN oder Zugangsdaten falsch."
    if "tan" in low and "wrong" in low:
        return "TAN falsch oder abgelaufen."

    # system_id failure: surface the bank's actual return codes so the cause is visible
    if "system_id" in low:
        detail = _format_codes(codes or [])
        if "9075" in code_set:
            return ("Bank verlangt starke Authentifizierung (TAN) bereits für die Synchronisation – "
                    f"vom aktuellen Ablauf noch nicht unterstützt. Bank-Codes: {detail}")
        return (f"Synchronisation mit der Bank fehlgeschlagen (keine system_id). Bank-Codes: {detail}")

    detail = _format_codes(codes or []) if codes else ""
    return f"FinTS-Fehler: {msg}" + (f" | Bank-Codes: {detail}" if detail else "")
