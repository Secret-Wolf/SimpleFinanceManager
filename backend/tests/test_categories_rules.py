"""Categories (deep nesting, path cache, subtree roll-up) and rule application
(incl. user scoping and rule-set selection)."""

from app.services.category_tree import MAX_CATEGORY_DEPTH


def _create_chain(admin, names, parent_id=None):
    """Create a nested category chain, returns list of created categories."""
    created = []
    for name in names:
        r = admin.post("/api/categories", json={"name": name, "parent_id": parent_id})
        assert r.status_code == 200, r.text
        cat = r.json()
        created.append(cat)
        parent_id = cat["id"]
    return created


def test_deep_nesting_and_full_path(admin):
    chain = _create_chain(admin, ["Mobilität", "Auto", "Tanken"])
    assert chain[2]["full_path"] == "Mobilität:Auto:Tanken"

    # nesting up to MAX_CATEGORY_DEPTH levels works ...
    deeper = _create_chain(admin, [f"Ebene{i}" for i in range(4, MAX_CATEGORY_DEPTH + 1)],
                           parent_id=chain[2]["id"])

    # ... one level more is rejected
    r = admin.post("/api/categories", json={"name": "ZuTief", "parent_id": deeper[-1]["id"]})
    assert r.status_code == 400
    assert str(MAX_CATEGORY_DEPTH) in r.json()["detail"]


def test_rename_updates_descendant_paths(admin):
    chain = _create_chain(admin, ["Mobilität", "Auto", "Tanken"])

    r = admin.patch(f"/api/categories/{chain[1]['id']}", json={"name": "PKW"})
    assert r.status_code == 200

    leaf = admin.get(f"/api/categories/{chain[2]['id']}").json()
    assert leaf["full_path"] == "Mobilität:PKW:Tanken"


def test_move_category_under_own_descendant_rejected(admin):
    chain = _create_chain(admin, ["A", "B", "C"])

    # A under C (its own grandchild) must fail
    r = admin.patch(f"/api/categories/{chain[0]['id']}", json={"parent_id": chain[2]["id"]})
    assert r.status_code == 400

    # moving a subtree that would exceed the depth limit must fail too:
    # B (height 2: B->C) under a node at depth MAX-1 -> depth would be MAX+1
    deep = _create_chain(admin, [f"D{i}" for i in range(1, MAX_CATEGORY_DEPTH)])
    r = admin.patch(f"/api/categories/{chain[1]['id']}", json={"parent_id": deep[-1]["id"]})
    assert r.status_code == 400


def test_move_category_to_root(admin):
    """parent_id=0 detaches a category (becomes Hauptkategorie), paths update."""
    chain = _create_chain(admin, ["A", "B", "C"])

    r = admin.patch(f"/api/categories/{chain[1]['id']}", json={"parent_id": 0})
    assert r.status_code == 200
    assert r.json()["parent_id"] is None
    assert r.json()["full_path"] == "B"

    leaf = admin.get(f"/api/categories/{chain[2]['id']}").json()
    assert leaf["full_path"] == "B:C"


def test_duplicate_category_name_rejected(admin):
    admin.post("/api/categories", json={"name": "Wohnen"})
    r = admin.post("/api/categories", json={"name": "Wohnen"})
    assert r.status_code == 400


def test_transactions_filter_includes_deep_subcategories(admin):
    chain = _create_chain(admin, ["Mobilität", "Auto", "Tanken"])
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-50.00", "description": "Aral",
                     "category_id": chain[2]["id"]})

    # filter on the root category must find the grandchild's transaction
    r = admin.get(f"/api/transactions?category_id={chain[0]['id']}").json()
    assert r["total"] == 1

    # without subcategories the root itself has no transactions
    r = admin.get(f"/api/transactions?category_id={chain[0]['id']}&include_subcategories=false").json()
    assert r["total"] == 0


def test_stats_rollup_over_subtree(admin):
    chain = _create_chain(admin, ["Mobilität", "Auto", "Tanken"])
    for cat, amount in [(chain[0], "-2.00"), (chain[1], "-5.00"), (chain[2], "-10.00")]:
        admin.post("/api/transactions/manual",
                   json={"booking_date": "2026-04-15", "amount": amount,
                         "description": "x", "category_id": cat["id"]})

    stats = admin.get(
        "/api/stats/by-category?period=custom&start_date=2026-04-01&end_date=2026-04-30"
    ).json()

    root = next(c for c in stats["categories"] if c["category_name"] == "Mobilität")
    assert float(root["total"]) == 17.0          # 2 + 5 + 10 rolled up
    assert root["transaction_count"] == 3

    auto = next(c for c in root["children"] if c["category_name"] == "Auto")
    assert float(auto["total"]) == 15.0          # 5 + 10
    tanken = next(c for c in auto["children"] if c["category_name"] == "Tanken")
    assert float(tanken["total"]) == 10.0

    # nothing double-counted in the grand total
    assert float(stats["total_expenses"]) == 17.0


def test_apply_rules_categorizes_matching_transaction(admin):
    cat = admin.post("/api/categories", json={"name": "Supermarkt"}).json()
    admin.post("/api/rules", json={"match_counterpart_name": "REWE", "assign_category_id": cat["id"]})
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE Markt"})

    result = admin.post("/api/rules/apply").json()
    assert result["categorized_count"] == 1
    tx = admin.get("/api/transactions").json()["items"][0]
    assert tx["category"]["name"] == "Supermarkt"


def test_apply_rules_with_selection(admin):
    """rule_ids restricts which rules run (Regel-Sets)."""
    cat_a = admin.post("/api/categories", json={"name": "Supermarkt"}).json()
    cat_b = admin.post("/api/categories", json={"name": "Tanken"}).json()
    rule_a = admin.post("/api/rules", json={
        "match_counterpart_name": "REWE", "assign_category_id": cat_a["id"],
        "group_name": "Einkauf"}).json()
    admin.post("/api/rules", json={
        "match_counterpart_name": "ARAL", "assign_category_id": cat_b["id"],
        "group_name": "Auto"})

    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE Markt"})
    admin.post("/api/transactions/manual",
               json={"booking_date": "2026-04-02", "amount": "-50.00", "description": "ARAL Tankstelle"})

    # only the selected rule runs
    result = admin.post("/api/rules/apply", json={"rule_ids": [rule_a["id"]]}).json()
    assert result["categorized_count"] == 1

    items = admin.get("/api/transactions").json()["items"]
    by_name = {tx["counterpart_name"]: tx for tx in items}
    assert by_name["REWE Markt"]["category"]["name"] == "Supermarkt"
    assert by_name["ARAL Tankstelle"]["category"] is None

    # without selection the remaining rule applies as before
    result = admin.post("/api/rules/apply").json()
    assert result["categorized_count"] == 1


def test_rule_group_name_roundtrip(admin):
    cat = admin.post("/api/categories", json={"name": "Supermarkt"}).json()
    rule = admin.post("/api/rules", json={
        "match_counterpart_name": "REWE", "assign_category_id": cat["id"],
        "group_name": "Fixkosten"}).json()
    assert rule["group_name"] == "Fixkosten"

    rule = admin.patch(f"/api/rules/{rule['id']}", json={"group_name": ""}).json()
    assert rule["group_name"] is None

    rule = admin.patch(f"/api/rules/{rule['id']}", json={"group_name": "Variabel"}).json()
    assert rule["group_name"] == "Variabel"


def test_rules_do_not_cross_user_boundaries(make_api):
    """A user's rules must never categorize another user's transactions."""
    usera = make_api()
    usera.register_admin("a@test.de")
    usera.create_user("b@test.de")
    userb = make_api()
    userb.login("b@test.de")

    cat = usera.post("/api/categories", json={"name": "Supermarkt"}).json()
    rule = usera.post("/api/rules", json={"match_counterpart_name": "REWE",
                                          "assign_category_id": cat["id"]}).json()

    usera.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE"})
    userb.post("/api/transactions/manual",
               json={"booking_date": "2026-04-01", "amount": "-5.00", "description": "REWE"})

    assert usera.post("/api/rules/apply").json()["categorized_count"] == 1

    assert usera.get("/api/transactions").json()["items"][0]["category"]["name"] == "Supermarkt"
    assert userb.get("/api/transactions").json()["items"][0]["category"] is None

    # selecting a foreign rule id explicitly must not run it either
    assert userb.post("/api/rules/apply",
                      json={"rule_ids": [rule["id"]]}).json()["categorized_count"] == 0
    assert userb.get("/api/transactions").json()["items"][0]["category"] is None

    # and a rule may not assign another user's category
    r = userb.post("/api/rules", json={"match_counterpart_name": "REWE",
                                       "assign_category_id": cat["id"]})
    assert r.status_code == 400
