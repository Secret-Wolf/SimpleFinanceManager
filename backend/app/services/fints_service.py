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

from fints.camt_parser import camt053_to_dict
from fints.client import FinTS3PinTanClient, NeedTANResponse
from fints.models import Transaction as FinTSTransaction
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
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


# --- Hintergrund-Sync-Jobs (RAM only, never written to disk) -------------------
#
# Warum ein Hintergrund-Thread statt eines request-übergreifenden Zustands:
# python-fints hält für einen laufenden Auftrag nicht-serialisierbare Zustände
# (Closures für Blättern und Ergebnisaufbereitung, siehe `_touchdown_*`). Über
# HTTP-Requests hinweg gehen die verloren. Ein Neuabruf nach der Freigabe ist
# keine Alternative: Banken mit auftragsbezogener SCA (Atruvia/Volksbank)
# verlangen dann für JEDEN Abruf eine neue Freigabe — der Nutzer wird mit
# Push-Nachrichten überflutet. Im Thread lebt das Client-Objekt bis zum Schluss,
# damit reicht **genau eine** Freigabe pro Abruf.
#
# Die PIN liegt weiterhin nur im RAM (Job-Eintrag) und verschwindet mit dem Job.

_JOB_TTL = 900  # seconds
_TAN_INPUT_TIMEOUT = 300  # wie lange ein Job auf eine eingegebene TAN wartet

_jobs: dict = {}
_jobs_lock = threading.Lock()


def _purge_expired():
    now = time.time()
    for token in [t for t, j in _jobs.items() if j["expires"] < now]:
        _jobs.pop(token, None)


def _new_job(user_id: int, connection_id: int) -> str:
    token = secrets.token_urlsafe(24)
    with _jobs_lock:
        _purge_expired()
        _jobs[token] = {
            "user_id": user_id,
            "connection_id": connection_id,
            "status": "running",          # running | tan_required | done | error
            "payload": {},
            "sca_done": False,            # True, sobald eine Freigabe/TAN akzeptiert wurde
            "tan_event": threading.Event(),
            "tan_value": None,
            "cancelled": False,
            "expires": time.time() + _JOB_TTL,
        }
    return token


def _set_job(token: str, status: str, payload: dict):
    with _jobs_lock:
        job = _jobs.get(token)
        if job:
            job["status"] = status
            job["payload"] = payload
            job["expires"] = time.time() + _JOB_TTL


def _get_job(token: str, user_id: int) -> Optional[dict]:
    with _jobs_lock:
        _purge_expired()
        job = _jobs.get(token)
        if not job or job["user_id"] != user_id:
            return None
        return job


def _mark_sca_done(token: str):
    """Merkt, dass eine Freigabe/TAN erfolgreich war. Steuert die Fehlermeldung:
    danach ist die PIN nachweislich korrekt, davor kann sie die Ursache sein."""
    with _jobs_lock:
        job = _jobs.get(token)
        if job:
            job["sca_done"] = True
            job["status"] = "running"
            job["payload"] = {}


def _error_context(token: str) -> str:
    with _jobs_lock:
        job = _jobs.get(token)
        return "resume" if job and job.get("sca_done") else "start"


def _job_cancelled(token: str) -> bool:
    with _jobs_lock:
        job = _jobs.get(token)
        return job is None or job.get("cancelled", False)


def _drop_job(token: str):
    with _jobs_lock:
        _jobs.pop(token, None)


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


def _normalize_transactions(result):
    """Nach einer TAN liefert python-fints beim CAMT-Pfad (HKCAZ) die rohen XML-Streams
    als Tupel (booked, pending) zurück — das Parsen macht sonst `get_transactions()`
    selbst, das wir hier übersprungen haben. Für MT940 (HKKAZ) kommt bereits die
    fertige Liste. Nicht erkannte Formen unverändert durchreichen."""
    if isinstance(result, tuple) and len(result) == 2:
        booked_streams, _pending_streams = result
        transactions = []
        for stream in booked_streams:
            transactions += [FinTSTransaction(t) for t in camt053_to_dict(stream)]
        return transactions
    return result


def _collect_with_tan(token: str, client: FinTS3PinTanClient, from_date: date):
    """Sammelt Konten, Umsätze und Salden ein und löst eine unterwegs verlangte
    TAN/Freigabe direkt hier auf — im selben Thread und damit im selben lebenden
    Client-Objekt. Nur so bleibt der Auftragszustand erhalten und die Bank fordert
    genau eine Freigabe an."""
    accounts = client.get_sepa_accounts()
    if isinstance(accounts, NeedTANResponse):
        accounts = _await_tan(token, client, accounts)

    end = date.today()
    statements = []
    for acc in accounts:
        tx = client.get_transactions(acc, from_date, end)
        if isinstance(tx, NeedTANResponse):
            tx = _normalize_transactions(_await_tan(token, client, tx))

        balance = None
        try:
            balance = client.get_balance(acc)
            if isinstance(balance, NeedTANResponse):
                balance = _await_tan(token, client, balance)
        except Exception:
            balance = None

        statements.append((acc, tx, balance))
    return statements


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
        # Das Frontend fragt nur noch UNSEREN Job-Status ab (kein Bank-Kontakt),
        # deshalb ist ein fixer, kurzer Takt richtig — die Bank-Wartezeiten hält
        # der Worker-Thread ein.
        payload["poll_after"] = poll_after if poll_after is not None else 2
        payload["poll_interval"] = 2
        payload["manual_confirm"] = False
    return payload


def _await_tan(token: str, client: FinTS3PinTanClient, need: NeedTANResponse):
    """Blockiert den Worker, bis die Freigabe erteilt bzw. die TAN eingegeben ist.

    Decoupled: im BPD-Takt der Bank nachfragen (Prozess 'S'), bis sie die Freigabe
    meldet. Sonst: auf die vom Nutzer über /tan gelieferte TAN warten.
    Rückgabe ist das Ergebnis von send_tan — bei Datenabrufen enthält es bereits
    die Umsätze, weil der Auftragszustand im lebenden Client erhalten ist."""
    decoupled = bool(getattr(need, "decoupled", False))
    poll = _decoupled_params(client) if decoupled else {}
    _set_job(token, "tan_required", _tan_payload(need, token, poll=poll))

    if not decoupled:
        tan = _wait_for_tan_input(token)
        resp = client.send_tan(need, tan)
        _mark_sca_done(token)
        return resp

    time.sleep(poll.get("first_wait", 3))
    for _ in range(poll.get("max_polls", 60)):
        if _job_cancelled(token):
            raise BankingError("Abruf abgebrochen.")
        resp = client.send_tan(need, "")
        if not (isinstance(resp, NeedTANResponse) and getattr(resp, "decoupled", False)):
            _mark_sca_done(token)
            return resp
        need = resp
        time.sleep(poll.get("interval", 3))

    raise BankingError(
        "Die Freigabe wurde nicht rechtzeitig bestätigt – bitte die Umsätze erneut abrufen."
    )


def _wait_for_tan_input(token: str) -> str:
    """Wartet auf die per /tan eingereichte TAN (klassisches TAN-Verfahren)."""
    with _jobs_lock:
        job = _jobs.get(token)
    if not job:
        raise BankingError("TAN-Vorgang abgelaufen oder ungültig. Bitte erneut abrufen.")
    if not job["tan_event"].wait(_TAN_INPUT_TIMEOUT):
        raise BankingError("Es wurde keine TAN eingegeben – Vorgang abgebrochen.")
    if job.get("cancelled"):
        raise BankingError("Abruf abgebrochen.")
    return job.get("tan_value") or ""


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

def _sync_worker(token: str, connection_id: int, user_id: int, pin: str, from_date: date):
    """Führt den kompletten Abruf in einem Hintergrund-Thread aus.

    Der Thread hält das FinTS-Client-Objekt von Anfang bis Ende am Leben. Damit
    bleiben auch die nicht-serialisierbaren Auftragszustände von python-fints
    erhalten, und eine unterwegs verlangte Freigabe kann direkt beantwortet
    werden — die Bank fordert genau EINE Freigabe an. Das Frontend fragt
    derweil nur den Job-Status ab und löst dabei keinen Bank-Kontakt aus."""
    db = SessionLocal()
    codes: list = []
    try:
        connection = db.query(BankConnection).filter(
            BankConnection.id == connection_id,
            BankConnection.user_id == user_id,
        ).first()
        if connection is None:
            _set_job(token, "error", {"status": "error", "message": "Bankverbindung nicht gefunden"})
            return

        client = _build_client(connection, pin, from_data=_load_system_data(connection))
        codes = _attach_code_recorder(client)
        _bootstrap_tan(client, connection)
        db.commit()  # persist any tan_mechanism/medium choice

        logger.info(
            "FinTS sync: conn=%s mechanism=%s hktan_v=%s",
            connection_id, client.selected_security_function, _hktan_version(client),
        )

        with client:
            # PSD2: schon die Anmeldung kann eine Freigabe verlangen (weist zugleich
            # die system_id zu) — vor jedem Lesezugriff auflösen.
            if getattr(client, "init_tan_response", None) is not None:
                _await_tan(token, client, client.init_tan_response)
            statements = _collect_with_tan(token, client, from_date)

        _save_system_data(db, connection, client.deconstruct(including_private=True))

        result = _import_statements(db, connection, statements, user_id)
        connection.last_sync = datetime.utcnow()
        db.commit()

        logger.info("FinTS sync: conn=%s fertig — %s neu, %s Duplikate",
                    connection_id, result.get("imported"), result.get("duplicates"))
        _set_job(token, "done", {"status": "done", **result})

    except BankingError as e:
        _set_job(token, "error", {"status": "error", "message": str(e)})
    except Exception as e:
        logger.warning("FinTS sync failed for connection %s: %s | bank codes: %s",
                       connection_id, e, _format_codes(codes))
        _set_job(token, "error",
                 {"status": "error",
                  "message": _friendly_error(e, codes, context=_error_context(token))})
    finally:
        db.close()


def _wait_for_job_state(token: str, timeout: float = 12.0) -> dict:
    """Wartet kurz, bis der Worker einen für das Frontend verwertbaren Zustand
    erreicht hat (TAN nötig, fertig oder Fehler). Schnelle Abrufe ohne Freigabe
    sind damit weiterhin in einem einzigen Request erledigt."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _jobs_lock:
            job = _jobs.get(token)
            if job is None:
                return {"status": "error", "message": "Abruf-Vorgang nicht mehr vorhanden."}
            status, payload = job["status"], dict(job["payload"] or {})
        if status in ("tan_required", "done", "error"):
            if status in ("done", "error"):
                _drop_job(token)
            return payload or {"status": status}
        time.sleep(0.25)

    # Läuft noch (z.B. langsame Bank): das Frontend soll weiter Status abfragen
    return {"status": "tan_required", "job_id": token, "decoupled": True,
            "challenge": "Verbindung zur Bank wird aufgebaut …",
            "poll_after": 2, "poll_interval": 2}


def start_sync(db: Session, connection: BankConnection, pin: str, from_date: Optional[date]) -> dict:
    """Startet einen Abruf. Liefert ein 'done'-, 'tan_required'- oder 'error'-Ergebnis."""
    from_date = _default_from_date(from_date)

    token = _new_job(connection.user_id, connection.id)
    thread = threading.Thread(
        target=_sync_worker,
        args=(token, connection.id, connection.user_id, pin, from_date),
        name=f"fints-sync-{connection.id}",
        daemon=True,
    )
    thread.start()

    return _wait_for_job_state(token)


def resume_sync(db: Session, connection: BankConnection, token: str, tan: Optional[str]) -> dict:
    """Fragt den Status eines laufenden Abrufs ab bzw. reicht eine eingegebene TAN
    an den wartenden Worker weiter. Löst selbst KEINEN Bank-Kontakt aus — dadurch
    kann kein zusätzlicher Freigabe-Vorgang entstehen, egal wie oft das Frontend
    (oder ein hängengebliebener Tab) pollt."""
    job = _get_job(token, connection.user_id)
    if not job:
        raise BankingError("Abruf-Vorgang abgelaufen oder ungültig. Bitte erneut abrufen.")

    if tan:
        with _jobs_lock:
            live = _jobs.get(token)
            if live is not None:
                live["tan_value"] = tan
                live["tan_event"].set()

    return _wait_for_job_state(token)


def cancel_sync(token: str, user_id: int) -> bool:
    """Bricht einen laufenden Abruf ab (Nutzer schließt den Dialog)."""
    with _jobs_lock:
        job = _jobs.get(token)
        if not job or job["user_id"] != user_id:
            return False
        job["cancelled"] = True
        job["tan_event"].set()  # einen wartenden TAN-Eingabe-Worker aufwecken
    return True


def _bank_instruction(codes: Optional[list]) -> str:
    """Die aussagekräftigste Klartext-Meldung der Bank (längster Text gewinnt) —
    für Fälle, in denen die Bank dem Nutzer selbst sagt, was zu tun ist."""
    texts = [t.strip() for _c, t in (codes or []) if t and t.strip()]
    if not texts:
        return ""
    best = max(texts, key=len)
    return best if best.endswith((".", "!", "?")) else best + "."


def _friendly_error(e: Exception, codes: Optional[list] = None, context: str = "start") -> str:
    msg = str(e) or e.__class__.__name__
    low = msg.lower()
    code_set = {c for c, _ in (codes or [])}

    if "connection" in low or "timed out" in low or "name or service" in low or "getaddrinfo" in low:
        return "Bankserver nicht erreichbar – FinTS-URL prüfen."

    # PSD2: Manche Banken (z.B. ING) verlangen periodisch — üblicherweise alle 90 Tage —
    # ein Login im Web-Banking, bevor der FinTS-Zugang weiterläuft. Die Bank liefert dazu
    # eine eindeutige Handlungsanweisung im Klartext; die gehört nach vorn, nicht hinter
    # unsere Vermutungen. Erkennung über den Text, weil derselbe Code je nach Bank auch
    # "PIN falsch" bedeuten kann.
    codes_text = " ".join(t for _c, t in (codes or [])).lower()
    if "authentifizierung" in codes_text and ("erneuern" in codes_text or "einloggen" in codes_text):
        return (f"Die Bank verlangt eine Erneuerung der Authentifizierung: {_bank_instruction(codes)} "
                "Danach funktioniert der Abruf wieder. Das ist eine PSD2-Vorgabe und wiederholt "
                "sich in der Regel alle 90 Tage – kein Fehler der App.")

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
