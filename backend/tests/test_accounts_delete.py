"""Konto löschen: Endpoint, Kaskade (Transaktionen/Tags), Benutzer-Isolation."""


def _create_account(api, name="Testkonto"):
    r = api.post("/api/accounts", json={"name": name, "account_type": "giro"})
    assert r.status_code == 200, r.text
    return r.json()


def _mktx(api, account_id, amount, desc):
    r = api.post("/api/transactions/manual", json={
        "booking_date": "2026-06-01", "amount": amount,
        "description": desc, "account_id": account_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_delete_account_removes_transactions(admin):
    account = _create_account(admin)
    _mktx(admin, account["id"], "-10.00", "Ausgabe 1")
    _mktx(admin, account["id"], "-20.00", "Ausgabe 2")

    r = admin.delete(f"/api/accounts/{account['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted_transactions"] == 2

    # Konto weg (auch inaktive Liste), Transaktionen weg
    accounts = admin.get("/api/accounts?include_inactive=true").json()
    assert all(a["id"] != account["id"] for a in accounts)
    assert admin.get("/api/transactions").json()["total"] == 0


def test_delete_account_with_tagged_transactions(admin):
    """Tag-Zuweisungen dürfen das Löschen nicht blockieren; das Tag selbst bleibt."""
    account = _create_account(admin)
    tx = _mktx(admin, account["id"], "-15.00", "Steuerberater")

    tag = admin.post("/api/tags", json={"name": "Steuerrelevant"}).json()
    r = admin.patch(f"/api/transactions/{tx['id']}", json={"tag_ids": [tag["id"]]})
    assert r.status_code == 200

    assert admin.delete(f"/api/accounts/{account['id']}").status_code == 200

    tags = admin.get("/api/tags").json()
    assert len(tags) == 1
    assert tags[0]["transaction_count"] == 0


def test_delete_account_requires_ownership(admin, make_api):
    """Fremde Konten sind unsichtbar -> 404, nichts wird gelöscht."""
    account = _create_account(admin, "Admins Konto")

    admin.create_user("user2@test.de")
    other = make_api()
    other.login("user2@test.de")

    assert other.delete(f"/api/accounts/{account['id']}").status_code == 404
    assert admin.get("/api/accounts?include_inactive=true").json()[0]["id"] == account["id"]


def test_delete_unknown_account_404(admin):
    assert admin.delete("/api/accounts/9999").status_code == 404
