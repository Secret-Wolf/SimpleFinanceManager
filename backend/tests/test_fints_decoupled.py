"""Decoupled-TAN (App-Freigabe): Job-Modell, Poll-Parameter, Fehlermeldungen.

Hintergrund: Der Abruf läuft in einem Hintergrund-Thread, der das FinTS-Client-
Objekt bis zum Schluss am Leben hält. Grund: python-fints hält Auftragszustände
(Closures) im RAM des Clients — über HTTP-Requests hinweg gehen die verloren, und
ein Neuabruf nach der Freigabe würde bei Banken mit auftragsbezogener SCA jedes
Mal eine NEUE Freigabe auslösen (Push-Flut beim Nutzer).
"""

import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import fints_service as fs
from app.services.fints_service import (
    BankingError,
    _decoupled_params,
    _friendly_error,
    _normalize_transactions,
    _tan_payload,
)


class _FakeMech(SimpleNamespace):
    pass


class _FakeClient(SimpleNamespace):
    def get_tan_mechanisms(self):
        return self._mechanisms


@pytest.fixture(autouse=True)
def _clean_jobs():
    """Job-Store zwischen den Tests leeren (RAM-global)."""
    with fs._jobs_lock:
        fs._jobs.clear()
    yield
    with fs._jobs_lock:
        fs._jobs.clear()


# --- BPD-Poll-Parameter -------------------------------------------------------

def test_decoupled_params_reads_bpd_values():
    client = _FakeClient(
        selected_security_function="921",
        _mechanisms={
            "921": _FakeMech(
                wait_before_first_poll=5,
                wait_before_next_poll=2,
                decoupled_max_poll_number=10,
                automated_polling_allowed=True,
            )
        },
    )
    assert _decoupled_params(client) == {
        "first_wait": 5, "interval": 2, "max_polls": 10, "automated": True}


def test_decoupled_params_defaults_when_missing():
    client = _FakeClient(selected_security_function="911",
                         _mechanisms={"911": _FakeMech(name="TAN-Verfahren")})
    assert _decoupled_params(client) == {
        "first_wait": 3, "interval": 3, "max_polls": 60, "automated": True}

    class _Broken:
        selected_security_function = "x"

        def get_tan_mechanisms(self):
            raise RuntimeError("BPD kaputt")

    assert _decoupled_params(_Broken())["interval"] == 3


# --- Job-Store & Status-Abfrage ----------------------------------------------

def test_job_lifecycle_and_user_isolation():
    token = fs._new_job(user_id=1, connection_id=7)

    assert fs._get_job(token, 1)["status"] == "running"
    assert fs._get_job(token, 2) is None, "fremder Nutzer darf den Job nicht sehen"

    fs._set_job(token, "done", {"status": "done", "imported": 3})
    assert fs._get_job(token, 1)["payload"]["imported"] == 3

    fs._drop_job(token)
    assert fs._get_job(token, 1) is None


def test_wait_for_job_state_returns_terminal_payload_and_clears_job():
    token = fs._new_job(user_id=1, connection_id=1)
    fs._set_job(token, "done", {"status": "done", "imported": 5, "duplicates": 2})

    result = fs._wait_for_job_state(token, timeout=1)
    assert result["status"] == "done"
    assert result["imported"] == 5
    # Terminalzustand wurde abgeholt -> Job (und damit die PIN) ist weg
    assert fs._get_job(token, 1) is None


def test_wait_for_job_state_reports_tan_required_without_clearing():
    token = fs._new_job(user_id=1, connection_id=1)
    fs._set_job(token, "tan_required", {"status": "tan_required", "job_id": token,
                                        "decoupled": True, "challenge": "Bitte freigeben"})

    result = fs._wait_for_job_state(token, timeout=1)
    assert result["status"] == "tan_required"
    # Job muss bestehen bleiben, der Worker arbeitet weiter
    assert fs._get_job(token, 1) is not None


def test_wait_for_job_state_keeps_frontend_polling_while_running():
    """Noch kein Ergebnis: Das Frontend bekommt einen Warte-Zustand, keinen Fehler."""
    token = fs._new_job(user_id=1, connection_id=1)
    result = fs._wait_for_job_state(token, timeout=0.5)
    assert result["status"] == "tan_required"
    assert result["poll_after"] >= 1


def test_cancel_sync_marks_job_and_wakes_waiter():
    token = fs._new_job(user_id=1, connection_id=1)

    assert fs.cancel_sync(token, user_id=2) is False, "fremder Nutzer darf nicht abbrechen"
    assert fs.cancel_sync(token, user_id=1) is True
    assert fs._job_cancelled(token) is True
    # Ein im TAN-Eingabe-Wait hängender Worker wird geweckt
    assert fs._jobs[token]["tan_event"].is_set()


def test_job_expiry_purges_pin():
    token = fs._new_job(user_id=1, connection_id=1)
    with fs._jobs_lock:
        fs._jobs[token]["expires"] = time.time() - 1
    assert fs._get_job(token, 1) is None
    assert token not in fs._jobs


def test_wait_for_tan_input_raises_when_cancelled():
    token = fs._new_job(user_id=1, connection_id=1)
    fs.cancel_sync(token, user_id=1)
    with pytest.raises(BankingError, match="abgebrochen"):
        fs._wait_for_tan_input(token)


# --- Payload ------------------------------------------------------------------

def test_tan_payload_poll_hints_are_frontend_paced():
    """Das Frontend pollt nur unseren Job-Status (kein Bank-Kontakt) — daher ein
    kurzer, fixer Takt; die BPD-Wartezeiten hält der Worker-Thread ein."""
    need = SimpleNamespace(challenge="Bitte in der App bestätigen",
                           challenge_matrix=None, decoupled=True)
    poll = {"first_wait": 30, "interval": 20, "max_polls": 10, "automated": True}

    payload = _tan_payload(need, "tok", poll=poll)
    assert payload["decoupled"] is True
    assert payload["poll_after"] == 2
    assert payload["poll_interval"] == 2
    assert payload["manual_confirm"] is False

    # Nicht-decoupled (TAN-Eingabe): keine Poll-Felder
    need_tan = SimpleNamespace(challenge="TAN eingeben", challenge_matrix=None, decoupled=False)
    assert "poll_after" not in _tan_payload(need_tan, "tok", poll=poll)


# --- Ergebnis-Aufbereitung ----------------------------------------------------

def test_normalize_transactions_passes_through_mt940_list():
    """MT940-Pfad liefert bereits fertige Transaktionen — unverändert lassen."""
    txs = [SimpleNamespace(data={"amount": 1}), SimpleNamespace(data={"amount": 2})]
    assert _normalize_transactions(txs) is txs
    assert _normalize_transactions([]) == []


def test_normalize_transactions_parses_camt_streams():
    """Nach einer TAN liefert der CAMT-Pfad rohe (booked, pending)-Streams —
    die muss unser Code parsen, weil get_transactions() übersprungen wurde."""
    camt = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.02"><BkToCstmrAcctRpt><Rpt>
<Id>TEST</Id><Acct><Id><IBAN>DE02120300000000202051</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Ntry><Amt Ccy="EUR">12.34</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
<BookgDt><Dt>2026-06-01</Dt></BookgDt><ValDt><Dt>2026-06-01</Dt></ValDt>
<NtryDtls><TxDtls><RmtInf><Ustrd>Testbuchung</Ustrd></RmtInf></TxDtls></NtryDtls>
</Ntry></Rpt></BkToCstmrAcctRpt></Document>"""

    result = _normalize_transactions(([camt], []))
    assert isinstance(result, list)
    assert len(result) == 1
    # DBIT -> negativer Betrag; Decimal bleibt erhalten (nie float!)
    assert result[0].data["amount"].amount == Decimal("-12.34")
    assert result[0].data["date"].isoformat() == "2026-06-01"


# --- Fehlermeldungen ----------------------------------------------------------

def test_friendly_error_9010_context():
    codes = [("9010", "Der Auftrag wurde abgelehnt")]
    assert "URL" in _friendly_error(Exception("x"), codes, context="start")

    resume_msg = _friendly_error(Exception("x"), codes, context="resume")
    assert "URL" not in resume_msg
    assert "erneut abrufen" in resume_msg
    assert "9010" in resume_msg


def test_friendly_error_never_blames_pin_during_approval():
    """python-fints wirft FinTSClientPINError für JEDEN 9xxx-Code. Im Freigabe-
    schritt ist die PIN nachweislich korrekt (die Bank hat ja die Freigabe
    angefordert) — die Meldung darf nicht auf die falsche Fährte führen."""
    exc = Exception("Error during dialog initialization, PIN wrong?")
    codes = [("9955", "Vorgang abgebrochen")]

    resume_msg = _friendly_error(exc, codes, context="resume")
    assert "PIN war korrekt" in resume_msg
    assert "9955" in resume_msg

    start_msg = _friendly_error(exc, codes, context="start")
    assert "PIN oder Zugangsdaten falsch" in start_msg
    assert "9955" in start_msg


def test_hktan_version_helper():
    from app.services.fints_service import _hktan_version

    class _Client:
        def get_tan_mechanisms(self):
            return {"921": SimpleNamespace(VERSION=7)}

        def get_current_tan_mechanism(self):
            return "921"

    assert _hktan_version(_Client()) == 7

    class _Broken:
        def get_tan_mechanisms(self):
            raise RuntimeError("kein BPD")

    assert _hktan_version(_Broken()) is None
