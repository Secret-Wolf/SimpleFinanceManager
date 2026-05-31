"""Split transactions: sum validation, parent exclusion, un-split on last child delete."""


def _expense(admin, amount="-30.00"):
    return admin.post("/api/transactions/manual",
                      json={"booking_date": "2026-04-01", "amount": amount, "description": "Einkauf"}).json()


def test_split_sum_must_match_original(admin):
    cat = admin.post("/api/categories", json={"name": "A"}).json()
    tx = _expense(admin, "-30.00")

    bad = admin.post(f"/api/transactions/{tx['id']}/split",
                     json={"parts": [{"amount": "10.00", "category_id": cat["id"]}]})
    assert bad.status_code == 400  # 10 != 30


def test_split_creates_children_and_hides_parent(admin):
    cat1 = admin.post("/api/categories", json={"name": "A"}).json()
    cat2 = admin.post("/api/categories", json={"name": "B"}).json()
    tx = _expense(admin, "-30.00")

    ok = admin.post(f"/api/transactions/{tx['id']}/split", json={"parts": [
        {"amount": "20.00", "category_id": cat1["id"]},
        {"amount": "10.00", "category_id": cat2["id"]},
    ]})
    assert ok.status_code == 200
    assert len(ok.json()) == 2

    listed = [t["id"] for t in admin.get("/api/transactions").json()["items"]]
    assert tx["id"] not in listed  # split parent is excluded from listings


def test_deleting_last_child_unsplits_parent(admin):
    cat = admin.post("/api/categories", json={"name": "A"}).json()
    tx = _expense(admin, "-30.00")
    children = admin.post(f"/api/transactions/{tx['id']}/split", json={"parts": [
        {"amount": "20.00", "category_id": cat["id"]},
        {"amount": "10.00", "category_id": cat["id"]},
    ]}).json()

    for child in children:
        admin.delete(f"/api/transactions/{child['id']}")

    listed = [t["id"] for t in admin.get("/api/transactions").json()["items"]]
    assert tx["id"] in listed  # parent reappears once un-split
