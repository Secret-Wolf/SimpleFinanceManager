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
from .transfers import detect_transfers_for_user

logger = logging.getLogger(__name__)

# python-fints v4+ requires a product_id. This is the official FinTS product-registration
# number assigned by the Deutsche Kreditwirtschaft for "SimpleFinanceManager" (category
# Web-Server). It is a public product identifier — sent to the bank in the HKVVB
# "Produktbezeichnung" field — and ships with the product so end users don't each have to
# register. Per the DK letter it must be exactly 25 characters. Power users can override it
# per-instance via the FINTS_PRODUCT_ID env var.
_FALLBACK_PRODUCT_ID = "FCA446B4054E9C1DD2E5189AB"


class BankingError(Exception):
    """User-facing banking error with a clean German message."""


# --- Transient pending-TAN store (RAM only, never written to disk) -------------

_PENDING_TTL = 300  # seconds
# Wie oft darf die Bank innerhalb eines Abrufs eine weitere Freigabe verlangen
# (Login-SCA, danach ggf. SCA für den Umsatzabruf) bevor wir abbrechen
_MAX_COLLECT_ROUNDS = 3
_pending: dict = {}
_pending_lock = threading.Lock()


def _purge_expired():
    now = time.time()
    for token in [t for t, p in _pending.items() if p["expires"] < now]:
        _pending.pop(token, None)


def _store_pending(*, user_id: int, connection_id: int, pin: str, client_data: bytes,
                   dialog_data: bytes, tan_data: bytes, from_date: date,
                   decoupled: bool = False, poll: Optional[dict] = None) -> str:
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
            # Decoupled-Polling-Zustand (BPD-Wartezeiten der Bank, Zählerstand)
            "decoupled": decoupled,
            "poll": poll or {},
            "polls_done": 0,
            "collect_rounds": 0,
            "in_flight": False,
            "last_payload": None,
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
        # HKVVB "Produktbezeichnung" — exactly the 25-char registration ID, no extra chars
        "product_id": (settings.FINTS_PRODUCT_ID or _FALLBACK_PRODUCT_ID).strip(),
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
        # Umbuchungen zuerst markieren, dann kategorisieren (Regeln ueberspringen Umbuchungen)
        detect_transfers_for_user(db, user_id)
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


def _decoupled_params(client: FinTS3PinTanClient) -> dict:
    """Liest die Decoupled-Polling-Vorgaben der Bank aus dem BPD (HITANS7):
    Wartezeit vor der ersten/nächsten Statusabfrage, max. Anzahl Abfragen und ob
    automatisches Polling überhaupt erlaubt ist. Wer schneller/öfter pollt als
    erlaubt, riskiert einen Abbruch des Freigabevorgangs (z.B. Atruvia → 9010)."""
    params = {"first_wait": 3, "interval": 3, "max_polls": 60, "automated": True}
    try:
        mechanisms = client.get_tan_mechanisms()
        mech = mechanisms.get(str(client.selected_security_function))
        if mech is None and mechanisms:
            mech = next(iter(mechanisms.values()))
        if mech is not None:
            first = getattr(mech, "wait_before_first_poll", None)
            nxt = getattr(mech, "wait_before_next_poll", None)
            maxp = getattr(mech, "decoupled_max_poll_number", None)
            auto = getattr(mech, "automated_polling_allowed", None)
            if first:
                params["first_wait"] = max(1, int(first))
            if nxt:
                params["interval"] = max(2, int(nxt))
            if maxp:
                params["max_polls"] = max(1, int(maxp))
            if auto is not None:
                params["automated"] = bool(auto)
    except Exception as e:  # BPD unvollständig o.ä. — konservative Defaults verwenden
        logger.info("Decoupled-Parameter nicht lesbar (%s) — Defaults aktiv", e)
    return params


def _hktan_version(client) -> Optional[int]:
    """HKTAN-Segmentversion des gewählten TAN-Verfahrens. Der Decoupled-Prozess 'S'
    existiert erst ab Version 7 — bei einem älteren Verfahren wäre die Statusabfrage
    gar nicht spezifiziert (nützlich für die Fehlersuche)."""
    try:
        mech = client.get_tan_mechanisms()[client.get_current_tan_mechanism()]
        return int(getattr(mech, "VERSION", 0)) or None
    except Exception:
        return None


def _restore_decoupled_flag(need_obj, decoupled: bool):
    """python-fints 5.0.0 verliert das decoupled-Flag bei get_data()/from_data():
    _from_data_v1 rekonstruiert NeedTANResponse immer mit decoupled=False. Ohne
    Korrektur schickt send_tan dann HKTAN-Prozess '2' (TAN-Einreichung mit leerer
    TAN) statt 'S' (Statusabfrage) — Atruvia bricht den Vorgang damit ab (9010)."""
    if decoupled and getattr(need_obj, "decoupled", None) is not True:
        need_obj.decoupled = True
    return need_obj


# Fortsetzungs-Methode ohne Client-Zustand: gibt die Bank-Antwort unveraendert zurueck
_NEUTRAL_RESUME = "_continue_dialog_initialization"


def _neutralize_resume_method(need_obj, client) -> bool:
    """Verhindert den AttributeError '_touchdown_args' beim stateless TAN-Flow.

    Loest ein Datenabruf (HKKAZ/HKCAZ) die SCA aus, merkt sich python-fints als
    Fortsetzung `_continue_fetch_with_touchdowns`. Diese Methode braucht den
    Touchdown-Zustand (Segment-Factory, Response-Processor, Segment-Typ), der nur
    im RAM des damaligen Client-Objekts liegt und weder von deconstruct() noch von
    pause_dialog() mitgespeichert wird — Closures sind nicht serialisierbar. Im
    Folge-Request ist der Client neu, die Attribute fehlen, und die Verarbeitung
    stirbt mit AttributeError, obwohl die Bank die Freigabe (0900) und die Umsaetze
    (0020) bereits geliefert hat.

    Loesung: Fortsetzung auf eine zustandslose Methode umbiegen, die die Antwort
    nur durchreicht. Die Umsaetze holen wir danach im authentifizierten Dialog
    ohnehin frisch ab (`_run_collect`) — dasselbe Muster, das nach jeder TAN greift.
    """
    if getattr(need_obj, "resume_method", None) != "_continue_fetch_with_touchdowns":
        return False
    if hasattr(client, "_touchdown_args"):
        return False  # gleicher Client wie beim Absetzen — Zustand ist da
    need_obj.resume_method = _NEUTRAL_RESUME
    return True


def _tan_payload(need: NeedTANResponse, token: str, poll: Optional[dict] = None,
                 poll_after: Optional[int] = None) -> dict:
    """Build the API payload describing a required TAN."""
    challenge_image = None
    try:
        if getattr(need, "challenge_matrix", None):
            mime, data = need.challenge_matrix
            challenge_image = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        challenge_image = None

    decoupled = bool(getattr(need, "decoupled", False))
    payload = {
        "status": "tan_required",
        "job_id": token,
        "challenge": (getattr(need, "challenge", None) or "").strip() or
                     ("Bitte die Aktion in deiner Banking-App bestätigen." if decoupled
                      else "Bitte TAN eingeben."),
        "decoupled": decoupled,
        "challenge_image": challenge_image,
    }
    if decoupled and poll:
        payload["poll_after"] = poll_after if poll_after is not None else poll.get("first_wait", 3)
        payload["poll_interval"] = poll.get("interval", 3)
        payload["manual_confirm"] = not poll.get("automated", True)
    return payload


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
            decoupled = bool(getattr(need, "decoupled", False))
            poll = _decoupled_params(client) if decoupled else {}
            logger.info(
                "FinTS start: conn=%s TAN erforderlich (decoupled=%s) mechanism=%s hktan_v=%s poll=%s | codes: %s",
                connection.id, decoupled, client.selected_security_function,
                _hktan_version(client), poll, _format_codes(codes),
            )
            token = _store_pending(
                user_id=connection.user_id, connection_id=connection.id, pin=pin,
                client_data=client_data, dialog_data=dialog_data,
                tan_data=need.get_data(), from_date=from_date,
                decoupled=decoupled, poll=poll,
            )
            payload = _tan_payload(need, token, poll=poll)
            with _pending_lock:
                if token in _pending:
                    # Erste Statusabfrage frühestens nach der Bank-Wartezeit
                    _pending[token]["not_before"] = time.time() + poll.get("first_wait", 3) if decoupled else 0
                    _pending[token]["last_payload"] = dict(payload)
            return payload

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
    """Resume a paused sync after the user provided a TAN (or for decoupled polling).

    Decoupled (App-Freigabe): pro Aufruf genau EINE Statusabfrage bei der Bank,
    und nur im von der Bank vorgegebenen Takt (BPD-Wartezeiten). Zu frühe oder
    parallele Polls werden ohne Bank-Kontakt beantwortet."""
    pending = _get_pending(token, connection.user_id)
    if not pending:
        raise BankingError("TAN-Vorgang abgelaufen oder ungültig. Bitte erneut abrufen.")

    decoupled = bool(pending.get("decoupled"))
    poll = pending.get("poll") or {}

    if decoupled:
        with _pending_lock:
            p = _pending.get(token)
            if not p:
                raise BankingError("TAN-Vorgang abgelaufen oder ungültig. Bitte erneut abrufen.")
            # Paralleler Poll läuft schon → letzten Stand zurückgeben, Bank nicht anfassen
            if p.get("in_flight") and p.get("last_payload"):
                payload = dict(p["last_payload"])
                payload["poll_after"] = poll.get("interval", 3)
                return payload
            # Zu früh (Bank-Wartezeit läuft noch) → ohne Bank-Kontakt vertrösten
            remaining = p.get("not_before", 0) - time.time()
            if remaining > 1.5 and p.get("last_payload"):
                payload = dict(p["last_payload"])
                payload["poll_after"] = max(1, int(remaining + 0.999))
                return payload
            # Maximale Anzahl Statusabfragen der Bank respektieren
            if p.get("polls_done", 0) >= poll.get("max_polls", 60):
                _pending.pop(token, None)
                raise BankingError(
                    "Freigabe nicht innerhalb der erlaubten Wartezeit bestätigt – "
                    "bitte die Umsätze erneut abrufen."
                )
            p["in_flight"] = True
        # Rest der Wartezeit (≤1.5s) kurz aussitzen statt einen Roundtrip zu verschwenden
        remaining = pending.get("not_before", 0) - time.time()
        if 0 < remaining <= 1.5:
            time.sleep(remaining)

    codes: list = []
    try:
        client = _build_client(connection, pending["pin"], from_data=pending["client_data"])
        codes = _attach_code_recorder(client)
        # python-fints 5.0.0 verliert das decoupled-Flag beim Serialisieren → restaurieren,
        # sonst geht statt der Statusabfrage (Prozess 'S') eine leere TAN (Prozess '2') raus
        need_obj = _restore_decoupled_flag(NeedRetryResponse.from_data(pending["tan_data"]), decoupled)
        neutralized = _neutralize_resume_method(need_obj, client)
        logger.info(
            "FinTS resume: conn=%s decoupled=%s poll=%s/%s mechanism=%s hktan_v=%s resume=%s%s",
            connection.id, decoupled, pending.get("polls_done", 0), poll.get("max_polls"),
            client.selected_security_function, _hktan_version(client),
            getattr(need_obj, "resume_method", "?"), " (neutralisiert)" if neutralized else "",
        )

        still_need = None
        dialog_data = None
        collected = None

        new_round = False

        with client.resume_dialog(pending["dialog_data"]):
            resp = client.send_tan(need_obj, tan or "")

            if isinstance(resp, NeedTANResponse) and getattr(resp, "decoupled", False):
                # Freigabe noch ausstehend (3956) — weiter pollen
                still_need = resp
                dialog_data = client.pause_dialog()
            else:
                # Freigabe erteilt: im jetzt authentifizierten Dialog frisch einsammeln
                status, payload = _run_collect(client, pending["from_date"])
                if status == "tan":
                    # Die Bank verlangt für den Datenabruf eine eigene Freigabe (bei
                    # Atruvia möglich, wenn schon der Login eine brauchte) — als neue
                    # Runde weiterführen statt den Vorgang abzubrechen.
                    rounds = pending.get("collect_rounds", 0) + 1
                    if rounds > _MAX_COLLECT_ROUNDS:
                        raise BankingError(
                            "Die Bank verlangt wiederholt neue Freigaben – Abruf abgebrochen. "
                            "Bitte später erneut versuchen."
                        )
                    still_need = payload
                    dialog_data = client.pause_dialog()
                    new_round = True
                else:
                    collected = payload

        client_data = client.deconstruct(including_private=True)
        _save_system_data(db, connection, client_data)

        if still_need is not None:
            # Update the pending entry for the next poll request (reuse the same token)
            if new_round:
                # Neuer Auftrag → Decoupled-Status und Bank-Takt neu bestimmen
                decoupled = bool(getattr(still_need, "decoupled", False))
                poll = _decoupled_params(client) if decoupled else {}
                polls_done = 0
                wait = poll.get("first_wait", 3)
            else:
                polls_done = pending.get("polls_done", 0) + 1
                wait = poll.get("interval", 3)

            payload = _tan_payload(still_need, token, poll=poll, poll_after=wait)
            with _pending_lock:
                if token in _pending:
                    _pending[token].update({
                        "client_data": client_data,
                        "dialog_data": dialog_data,
                        "tan_data": still_need.get_data(),
                        "decoupled": decoupled,
                        "poll": poll,
                        "polls_done": polls_done,
                        "collect_rounds": pending.get("collect_rounds", 0) + (1 if new_round else 0),
                        "not_before": time.time() + wait,
                        "last_payload": dict(payload),
                        "in_flight": False,
                        "expires": time.time() + _PENDING_TTL,
                    })
            return payload

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
        raise BankingError(_friendly_error(e, codes, context="resume")) from e
    finally:
        with _pending_lock:
            if token in _pending:
                _pending[token]["in_flight"] = False


def _friendly_error(e: Exception, codes: Optional[list] = None, context: str = "start") -> str:
    msg = str(e) or e.__class__.__name__
    low = msg.lower()
    code_set = {c for c, _ in (codes or [])}

    if "connection" in low or "timed out" in low or "name or service" in low or "getaddrinfo" in low:
        return "Bankserver nicht erreichbar – FinTS-URL prüfen."
    if "9010" in code_set:
        if context == "resume":
            # Mitten im TAN-/Freigabevorgang bedeutet 9010 NICHT "falsche URL",
            # sondern dass die Bank den laufenden Vorgang abgebrochen/abgelehnt hat
            return ("Die Bank hat den Freigabe-Vorgang abgebrochen (Code 9010). "
                    "Bitte die Umsätze erneut abrufen und die Freigabe in der App zeitnah bestätigen. "
                    f"Bank-Meldung: {_format_codes(codes)}")
        return "Falsche Bank/FinTS-URL für diese BLZ (BPD-Fehler 9010) – URL prüfen (ggf. fints1 vs. fints2.atruvia.de)."
    if code_set & {"9078", "9079"}:
        return ("Die Bank verlangt eine registrierte FinTS-Produkt-ID (Code 9078). Bitte eine kostenlose "
                "Produkt-Registrierungsnummer bei der Deutschen Kreditwirtschaft beantragen "
                "(registrierung@hbci-zka.de) und als FINTS_PRODUCT_ID setzen. "
                "Volksbank/Atruvia erzwingt dies – ING meist nicht.")
    if code_set & {"9340", "9910", "9930", "9931", "9942"} or "pin" in low:
        if context == "resume":
            # Im Freigabe-/TAN-Schritt ist die PIN längst akzeptiert (sonst hätte die Bank
            # gar keine Freigabe angefordert). python-fints wirft hier FinTSClientPINError
            # für JEDEN 9xxx-Code — die Meldung "PIN falsch" wäre schlicht falsch.
            return ("Die Bank hat die Freigabe nicht akzeptiert. Die PIN war korrekt (die "
                    "Freigabe-Anfrage kam ja an) – vermutlich ist der Vorgang abgelaufen "
                    f"oder die Bank lehnt die Statusabfrage ab. Bank-Meldung: {_format_codes(codes)}")
        return f"Anmeldung fehlgeschlagen – PIN oder Zugangsdaten falsch. Bank-Meldung: {_format_codes(codes)}"
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
