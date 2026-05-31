"""Per-user data isolation — the load-bearing multi-user guarantee."""


def _two_users(make_api):
    admin = make_api()
    admin.register_admin("a@test.de", name="UserA")
    admin.create_user("b@test.de", name="UserB")
    userb = make_api()
    userb.login("b@test.de")
    return admin, userb


def test_transactions_are_not_visible_across_users(make_api):
    usera, userb = _two_users(make_api)

    r = usera.post("/api/transactions/manual",
                   json={"booking_date": "2026-04-01", "amount": "-10.00", "description": "Geheim A"})
    assert r.status_code == 200, r.text

    a_list = usera.get("/api/transactions").json()
    assert a_list["total"] == 1
    assert a_list["items"][0]["purpose"] == "Geheim A"

    b_list = userb.get("/api/transactions").json()
    assert b_list["total"] == 0  # user B sees nothing of user A's data


def test_user_cannot_read_other_users_transaction_by_id(make_api):
    usera, userb = _two_users(make_api)
    tx = usera.post("/api/transactions/manual",
                    json={"booking_date": "2026-04-01", "amount": "5.00", "description": "A"}).json()

    assert userb.get(f"/api/transactions/{tx['id']}").status_code == 404
    assert userb.delete(f"/api/transactions/{tx['id']}").status_code == 404


def test_categories_are_isolated(make_api):
    usera, userb = _two_users(make_api)
    usera.post("/api/categories", json={"name": "Nur fuer A"})

    a_names = [c["name"] for c in usera.get("/api/categories?flat=true").json()]
    b_names = [c["name"] for c in userb.get("/api/categories?flat=true").json()]
    assert "Nur fuer A" in a_names
    assert "Nur fuer A" not in b_names


def test_user_with_no_accounts_sees_nothing(make_api):
    # A brand-new user (no accounts/transactions) must get an empty, not-leaking list
    admin = make_api()
    admin.register_admin("a@test.de")
    admin.create_user("fresh@test.de")
    fresh = make_api()
    fresh.login("fresh@test.de")
    assert fresh.get("/api/transactions").json()["total"] == 0
