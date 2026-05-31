"""Online-banking (FinTS) endpoints: CRUD, SSRF guard, auth, clean error path.

The real credentialed sync needs a bank + PIN/TAN and is not exercised here; we verify
the connection is reachable-but-failing yields a structured error rather than a 500.
"""


def test_connection_crud(admin):
    r = admin.post("/api/banking/connections", json={
        "name": "ING", "bank_code": "50010517", "login_name": "demo",
        "fints_url": "https://fints.ing.de/fints/",
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert any(c["id"] == cid for c in admin.get("/api/banking/connections").json())
    assert admin.delete(f"/api/banking/connections/{cid}").status_code == 200
    assert admin.get("/api/banking/connections").json() == []


def test_ssrf_internal_urls_rejected(admin):
    for url in ["https://127.0.0.1/x", "https://192.168.0.1/x", "https://localhost/x", "http://fints.ing.de/x"]:
        r = admin.post("/api/banking/connections",
                       json={"name": "x", "bank_code": "123", "login_name": "y", "fints_url": url})
        assert r.status_code == 422, f"{url} should be rejected"


def test_banking_requires_auth(api):
    assert api.get("/api/banking/connections").status_code == 401


def test_sync_unreachable_host_returns_clean_error(admin):
    cid = admin.post("/api/banking/connections", json={
        "name": "x", "bank_code": "50010517", "login_name": "demo",
        "fints_url": "https://fints.example.invalid/fints/",
    }).json()["id"]

    r = admin.post(f"/api/banking/connections/{cid}/sync", json={"pin": "00000"})
    assert r.status_code == 200  # structured result, not a 500
    assert r.json()["status"] == "error"
    assert r.json()["message"]


def test_connection_isolation(make_api):
    usera = make_api()
    usera.register_admin("a@test.de")
    usera.create_user("b@test.de")
    userb = make_api()
    userb.login("b@test.de")

    cid = usera.post("/api/banking/connections", json={
        "name": "A-Bank", "bank_code": "50010517", "login_name": "demo",
        "fints_url": "https://fints.ing.de/fints/",
    }).json()["id"]

    assert userb.get("/api/banking/connections").json() == []
    assert userb.delete(f"/api/banking/connections/{cid}").status_code == 404
