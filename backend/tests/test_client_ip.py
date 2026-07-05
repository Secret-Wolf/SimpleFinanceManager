"""Client-IP-Ermittlung hinter Reverse Proxy (Rate-Limit/Audit, Spoof-Schutz)."""

import pytest

from app import client_ip
from app.config import settings


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, peer, headers=None):
        self.client = _FakeClient(peer) if peer else None
        self.headers = headers or {}


@pytest.fixture
def trusted(monkeypatch):
    """Setzt TRUSTED_PROXIES für einen Test und leert den Cache danach."""
    def _set(proxies):
        monkeypatch.setattr(settings, "TRUSTED_PROXIES", proxies)
        client_ip._cache["raw"] = None  # Cache invalidieren
    yield _set
    client_ip._cache["raw"] = None


def test_no_trusted_proxies_uses_peer(trusted):
    trusted([])
    req = _FakeRequest("203.0.113.9", {"x-forwarded-for": "1.2.3.4"})
    # Ohne konfigurierten Proxy wird XFF ignoriert -> Socket-Peer zählt
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_direct_connection_ignores_spoofed_xff(trusted):
    """Angreifer verbindet direkt (Peer != Proxy) und faked X-Forwarded-For."""
    trusted(["192.168.178.5"])
    req = _FakeRequest("203.0.113.9", {"x-forwarded-for": "9.9.9.9"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"  # nicht 9.9.9.9


def test_through_proxy_takes_real_client(trusted):
    """Peer IST der Proxy: echte Client-IP = rechtester nicht-vertrauter XFF-Eintrag."""
    trusted(["192.168.178.5"])
    # nginx hängt die echte Client-IP hinten an; links Angehängtes ist gefälscht
    req = _FakeRequest("192.168.178.5", {"x-forwarded-for": "9.9.9.9, 203.0.113.9"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_through_proxy_single_hop(trusted):
    trusted(["192.168.178.5"])
    req = _FakeRequest("192.168.178.5", {"x-forwarded-for": "203.0.113.9"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_spoof_of_trusted_ip_still_resolves_real_client(trusted):
    """Client faked die Proxy-IP im XFF — nginx hängt echte IP an, die gewinnt."""
    trusted(["192.168.178.5"])
    req = _FakeRequest("192.168.178.5", {"x-forwarded-for": "192.168.178.5, 203.0.113.9"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_cidr_trusted_network(trusted):
    trusted(["172.16.0.0/12"])
    req = _FakeRequest("172.18.0.5", {"x-forwarded-for": "203.0.113.9"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_xff_with_port_is_stripped(trusted):
    trusted(["192.168.178.5"])
    req = _FakeRequest("192.168.178.5", {"x-forwarded-for": "203.0.113.9:51234"})
    assert client_ip.get_client_ip(req) == "203.0.113.9"


def test_only_proxies_in_chain_falls_back_to_peer(trusted):
    trusted(["192.168.178.5", "192.168.178.6"])
    req = _FakeRequest("192.168.178.5", {"x-forwarded-for": "192.168.178.6"})
    assert client_ip.get_client_ip(req) == "192.168.178.5"


def test_missing_peer_is_unknown(trusted):
    trusted(["192.168.178.5"])
    req = _FakeRequest(None, {"x-forwarded-for": "9.9.9.9"})
    assert client_ip.get_client_ip(req) == "unknown"


def test_rotating_xff_yields_stable_key_when_untrusted(trusted):
    """Der Rate-Limit-Key (client_ip_key) bleibt bei rotierendem XFF stabil,
    solange der Peer kein vertrauenswuerdiger Proxy ist — kein Bucket-Bypass."""
    trusted(["192.168.178.5"])
    keys = {
        client_ip.client_ip_key(_FakeRequest("203.0.113.9", {"x-forwarded-for": f"10.0.0.{i}"}))
        for i in range(10)
    }
    assert keys == {"203.0.113.9"}
