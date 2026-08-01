"""TOTP-Zwei-Faktor: Einrichtung, Login-Flow, Replay-Schutz, Recovery, Admin-Reset."""

import time

import pyotp

PW = "TestPasswort123"  # entspricht conftest.PW


def _enable_totp(api):
    """Richtet 2FA für den eingeloggten Benutzer ein; gibt (secret, recovery_codes) zurück."""
    setup = api.post("/api/auth/totp/setup", json={"password": PW})
    assert setup.status_code == 200, setup.text
    data = setup.json()
    assert data["otpauth_url"].startswith("otpauth://totp/")
    assert "<svg" in data["qr_svg"]

    code = pyotp.TOTP(data["secret"]).now()
    enable = api.post("/api/auth/totp/enable", json={"code": code})
    assert enable.status_code == 200, enable.text
    codes = enable.json()["recovery_codes"]
    assert len(codes) == 8
    return data["secret"], codes


def _next_window_code(secret):
    """Code des nächsten Zeitfensters — das Enable hat das aktuelle bereits verbraucht;
    der Server akzeptiert ±1 Fenster."""
    return pyotp.TOTP(secret).at(int(time.time()) + 30)


def test_totp_setup_requires_password(admin):
    assert admin.post("/api/auth/totp/setup", json={"password": "falsch"}).status_code == 400
    assert admin.get("/api/auth/totp/status").json() == {
        "enabled": False, "recovery_codes_remaining": 0}


def test_totp_enable_rejects_wrong_code(admin):
    setup = admin.post("/api/auth/totp/setup", json={"password": PW})
    assert setup.status_code == 200
    assert admin.post("/api/auth/totp/enable", json={"code": "000000"}).status_code == 400
    assert admin.get("/api/auth/totp/status").json()["enabled"] is False


def test_login_flow_with_totp_and_replay_protection(admin, make_api):
    secret, _codes = _enable_totp(admin)

    status = admin.get("/api/auth/totp/status").json()
    assert status == {"enabled": True, "recovery_codes_remaining": 8}

    # Ohne Code: Passwort ok -> totp_required, aber KEINE Session-Cookies
    fresh = make_api()
    r = fresh.post("/api/auth/login", json={"email": "admin@test.de", "password": PW})
    assert r.status_code == 200
    assert r.json() == {"totp_required": True}
    assert fresh.get("/api/auth/me").status_code == 401

    # Falscher Code -> 401
    r = fresh.post("/api/auth/login",
                   json={"email": "admin@test.de", "password": PW, "totp_code": "000000"})
    assert r.status_code == 401

    # Gültiger Code -> eingeloggt
    code = _next_window_code(secret)
    r = fresh.post("/api/auth/login",
                   json={"email": "admin@test.de", "password": PW, "totp_code": code})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["totp_enabled"] is True
    assert fresh.get("/api/auth/me").status_code == 200

    # Replay: derselbe Code funktioniert kein zweites Mal
    replay = make_api()
    r = replay.post("/api/auth/login",
                    json={"email": "admin@test.de", "password": PW, "totp_code": code})
    assert r.status_code == 401
    assert "bereits verwendet" in r.json()["detail"]


def test_login_with_recovery_code_consumes_it(admin, make_api):
    _secret, codes = _enable_totp(admin)

    fresh = make_api()
    r = fresh.post("/api/auth/login",
                   json={"email": "admin@test.de", "password": PW, "totp_code": codes[0]})
    assert r.status_code == 200, r.text
    assert fresh.get("/api/auth/totp/status").json()["recovery_codes_remaining"] == 7

    # Derselbe Recovery-Code ist verbraucht
    again = make_api()
    r = again.post("/api/auth/login",
                   json={"email": "admin@test.de", "password": PW, "totp_code": codes[0]})
    assert r.status_code == 401


def test_totp_disable(admin):
    secret, _codes = _enable_totp(admin)

    # Falsches Passwort / falscher Code -> 400, bleibt aktiv
    assert admin.post("/api/auth/totp/disable",
                      json={"password": "falsch", "code": "000000"}).status_code == 400
    code = _next_window_code(secret)
    assert admin.post("/api/auth/totp/disable",
                      json={"password": PW, "code": code}).status_code == 200
    assert admin.get("/api/auth/totp/status").json()["enabled"] is False


def test_admin_can_reset_totp(admin, make_api):
    admin.create_user("user2@test.de")
    other = make_api()
    other.login("user2@test.de")
    _enable_totp(other)

    users = admin.get("/api/auth/users").json()
    user2 = next(u for u in users if u["email"] == "user2@test.de")
    assert user2["totp_enabled"] is True

    r = admin.patch(f"/api/auth/users/{user2['id']}", json={"reset_totp": True})
    assert r.status_code == 200
    assert r.json()["totp_enabled"] is False

    # Login funktioniert wieder ohne Code (neuer Client, alte Sessions sind invalidiert)
    fresh = make_api()
    r = fresh.post("/api/auth/login", json={"email": "user2@test.de", "password": PW})
    assert r.status_code == 200
    assert "totp_required" not in r.json()
