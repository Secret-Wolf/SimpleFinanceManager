"""Decoupled-TAN-Fixes: decoupled-Flag-Restaurierung, BPD-Poll-Parameter, Payload-Hints.

Hintergrund: python-fints 5.0.0 verliert das decoupled-Flag bei
NeedTANResponse.get_data()/from_data() — ohne Restaurierung geht beim Poll
HKTAN-Prozess '2' (leere TAN) statt 'S' (Statusabfrage) raus und Atruvia
bricht den Freigabevorgang mit 9010 ab.
"""

from types import SimpleNamespace

from app.services.fints_service import (
    _decoupled_params,
    _friendly_error,
    _restore_decoupled_flag,
    _tan_payload,
)


class _FakeMech(SimpleNamespace):
    pass


class _FakeClient(SimpleNamespace):
    def get_tan_mechanisms(self):
        return self._mechanisms


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
    params = _decoupled_params(client)
    assert params == {"first_wait": 5, "interval": 2, "max_polls": 10, "automated": True}


def test_decoupled_params_defaults_when_missing():
    # Mechanismus ohne Decoupled-Felder (z.B. HITANS6) -> konservative Defaults
    client = _FakeClient(selected_security_function="911",
                         _mechanisms={"911": _FakeMech(name="TAN-Verfahren")})
    params = _decoupled_params(client)
    assert params == {"first_wait": 3, "interval": 3, "max_polls": 60, "automated": True}

    # get_tan_mechanisms wirft -> Defaults statt Absturz
    class _Broken:
        selected_security_function = "x"

        def get_tan_mechanisms(self):
            raise RuntimeError("BPD kaputt")

    assert _decoupled_params(_Broken())["interval"] == 3


def test_decoupled_params_manual_confirm():
    client = _FakeClient(
        selected_security_function="922",
        _mechanisms={"922": _FakeMech(automated_polling_allowed=False,
                                      wait_before_first_poll=3,
                                      wait_before_next_poll=3)},
    )
    assert _decoupled_params(client)["automated"] is False


def test_restore_decoupled_flag():
    # from_data liefert decoupled=False (Bibliotheks-Bug) -> restaurieren
    need = SimpleNamespace(decoupled=False)
    assert _restore_decoupled_flag(need, True).decoupled is True
    # Nicht-decoupled Vorgänge bleiben unangetastet
    need2 = SimpleNamespace(decoupled=False)
    assert _restore_decoupled_flag(need2, False).decoupled is False


def test_tan_payload_contains_poll_hints():
    need = SimpleNamespace(challenge="Bitte in der App bestätigen",
                           challenge_matrix=None, decoupled=True)
    poll = {"first_wait": 5, "interval": 2, "max_polls": 10, "automated": True}

    payload = _tan_payload(need, "tok", poll=poll)
    assert payload["decoupled"] is True
    assert payload["poll_after"] == 5
    assert payload["poll_interval"] == 2
    assert payload["manual_confirm"] is False

    # Folge-Polls: poll_after = Intervall
    payload = _tan_payload(need, "tok", poll=poll, poll_after=2)
    assert payload["poll_after"] == 2

    # Kein automatisches Polling erlaubt -> manueller Bestätigen-Modus
    poll_manual = {**poll, "automated": False}
    assert _tan_payload(need, "tok", poll=poll_manual)["manual_confirm"] is True

    # Nicht-decoupled: keine Poll-Felder
    need_tan = SimpleNamespace(challenge="TAN eingeben", challenge_matrix=None, decoupled=False)
    payload = _tan_payload(need_tan, "tok", poll=poll)
    assert "poll_after" not in payload


def test_friendly_error_9010_context():
    codes = [("9010", "Der Auftrag wurde abgelehnt")]
    # Beim Verbindungsaufbau: URL-Hinweis
    assert "URL" in _friendly_error(Exception("x"), codes, context="start")
    # Mitten im Freigabevorgang: KEIN irreführender URL-Hinweis, sondern Abbruch-Meldung
    resume_msg = _friendly_error(Exception("x"), codes, context="resume")
    assert "URL" not in resume_msg
    assert "erneut abrufen" in resume_msg
    assert "9010" in resume_msg
