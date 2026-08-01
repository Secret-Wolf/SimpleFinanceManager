"""Tags: CRUD, Zuweisung, Filter (inkl. Summe), Bulk, Export, Benutzer-Isolation."""


def _mktx(api, amount, desc):
    r = api.post("/api/transactions/manual", json={
        "booking_date": "2026-06-01", "amount": amount, "description": desc,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _mktag(api, name, color=None):
    r = api.post("/api/tags", json={"name": name, "color": color})
    assert r.status_code == 201, r.text
    return r.json()


def test_tag_crud_and_duplicate_check(admin):
    tag = _mktag(admin, "Steuerrelevant", "#10b981")
    assert tag["name"] == "Steuerrelevant"

    # Duplikat (case-insensitive) abgelehnt
    assert admin.post("/api/tags", json={"name": "steuerrelevant"}).status_code == 400

    # Umbenennen + Farbe
    r = admin.patch(f"/api/tags/{tag['id']}", json={"name": "Steuer 2026", "color": "#ef4444"})
    assert r.status_code == 200
    assert r.json()["name"] == "Steuer 2026"

    assert admin.delete(f"/api/tags/{tag['id']}").status_code == 200
    assert admin.get("/api/tags").json() == []


def test_tag_assignment_and_filter_with_sum(admin):
    tag = _mktag(admin, "Steuerrelevant")
    tx1 = _mktx(admin, "-100.00", "Steuerberater")
    tx2 = _mktx(admin, "-50.50", "Fachbuch")
    _mktx(admin, "-999.00", "Privat")

    for tx in (tx1, tx2):
        r = admin.patch(f"/api/transactions/{tx['id']}", json={"tag_ids": [tag["id"]]})
        assert r.status_code == 200
        assert [t["name"] for t in r.json()["tags"]] == ["Steuerrelevant"]

    result = admin.get(f"/api/transactions?tag_id={tag['id']}").json()
    assert result["total"] == 2
    assert float(result["total_amount"]) == -150.5

    # Zuweisung ersetzen (leer = alle entfernen)
    r = admin.patch(f"/api/transactions/{tx1['id']}", json={"tag_ids": []})
    assert r.json()["tags"] == []
    assert admin.get(f"/api/transactions?tag_id={tag['id']}").json()["total"] == 1

    # Tag löschen entfernt die Zuweisungen
    admin.delete(f"/api/tags/{tag['id']}")
    tx2_detail = admin.get(f"/api/transactions/{tx2['id']}").json()
    assert tx2_detail["tags"] == []


def test_bulk_tag_assign_and_remove(admin):
    tag = _mktag(admin, "Urlaub")
    ids = [_mktx(admin, "-10.00", f"Ausgabe {i}")["id"] for i in range(3)]

    r = admin.post("/api/transactions/bulk-tag", json={"transaction_ids": ids, "tag_id": tag["id"]})
    assert r.status_code == 200
    assert r.json()["updated_count"] == 3

    # Idempotent: erneut zuweisen ändert nichts
    r = admin.post("/api/transactions/bulk-tag", json={"transaction_ids": ids, "tag_id": tag["id"]})
    assert r.json()["updated_count"] == 0

    r = admin.post("/api/transactions/bulk-tag",
                   json={"transaction_ids": ids[:2], "tag_id": tag["id"], "remove": True})
    assert r.json()["updated_count"] == 2
    assert admin.get(f"/api/transactions?tag_id={tag['id']}").json()["total"] == 1


def test_tags_are_user_isolated(admin, make_api):
    tag = _mktag(admin, "Steuerrelevant")
    tx = _mktx(admin, "-10.00", "Admins Ausgabe")
    admin.patch(f"/api/transactions/{tx['id']}", json={"tag_ids": [tag["id"]]})

    admin.create_user("user2@test.de")
    other = make_api()
    other.login("user2@test.de")

    # Fremde Tags: unsichtbar, nicht zuweisbar, Filter liefert leer
    assert other.get("/api/tags").json() == []
    other_tx = _mktx(other, "-5.00", "Users Ausgabe")
    r = other.patch(f"/api/transactions/{other_tx['id']}", json={"tag_ids": [tag["id"]]})
    assert r.status_code == 400
    assert other.get(f"/api/transactions?tag_id={tag['id']}").json()["total"] == 0
    assert other.post("/api/transactions/bulk-tag",
                      json={"transaction_ids": [other_tx["id"]], "tag_id": tag["id"]}).status_code == 400


def test_export_contains_tags_column(admin):
    tag = _mktag(admin, "Steuerrelevant")
    tx = _mktx(admin, "-42.00", "Steuersoftware")
    admin.patch(f"/api/transactions/{tx['id']}", json={"tag_ids": [tag["id"]]})

    csv_text = admin.get("/api/transactions/export").text
    header = csv_text.splitlines()[0]
    assert "Tags" in header
    assert "Steuerrelevant" in csv_text


def test_transaction_delete_cleans_tag_assignment(admin):
    tag = _mktag(admin, "Temp")
    tx = _mktx(admin, "-1.00", "Wegwerf")
    admin.patch(f"/api/transactions/{tx['id']}", json={"tag_ids": [tag["id"]]})

    assert admin.delete(f"/api/transactions/{tx['id']}").status_code == 200
    assert admin.get("/api/tags").json()[0]["transaction_count"] == 0
