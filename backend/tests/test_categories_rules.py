"""Categories (2-level limit, path cache) and rule application (incl. user scoping)."""


def test_two_level_nesting_and_full_path(admin):
    parent = admin.post("/api/categories", json={"name": "Mobilität"}).json()
    child = admin.post("/api/categories", json={"name": "Tanken", "parent_id": parent["id"]}).json()
    assert child["full_path"] == "Mobilität:Tanken"

    # a third level must be rejected
    r = admin.post("/api/categories", json={"name": "Super", "parent_id": child["id"]})
    assert r.status_code == 400


def test_duplicate_category_name_rejected(admin):
    admin.post("/api/categories", json={"name": "Wohnen"})
    r = admin.post("/api/categories", json={"name": "Wohnen"})
    assert r.status_code == 400


def test_apply_rules_categorizes_matching_transaction(admin):
    cat = admin.post("/api/categories", json={"name": "Supermarkt"}).json()
    admin.post("/api/rules", json={"match_counterpart_name": "REWE", "assign_category_id": cat["id"]})
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE Markt"})

    result = admin.post("/api/rules/apply").json()
    assert result["categorized_count"] == 1
    tx = admin.get("/api/transactions").json()["items"][0]
    assert tx["category"]["name"] == "Supermarkt"


def test_rules_do_not_cross_user_boundaries(make_api):
    """A user's rules must never categorize another user's transactions."""
    usera = make_api()
    usera.register_admin("a@test.de")
    usera.create_user("b@test.de")
    userb = make_api()
    userb.login("b@test.de")

    cat = usera.post("/api/categories", json={"name": "Supermarkt"}).json()
    usera.post("/api/rules", json={"match_counterpart_name": "REWE", "assign_category_id": cat["id"]})

    usera.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE"})
    userb.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE"})

    assert usera.post("/api/rules/apply").json()["categorized_count"] == 1

    assert usera.get("/api/transactions").json()["items"][0]["category"]["name"] == "Supermarkt"
    assert userb.get("/api/transactions").json()["items"][0]["category"] is None
