"""Transaktionsliste: Sortierung (u. a. nach Betrag der Höhe nach)."""


def _mktx(admin, amount, desc, date="2026-06-01"):
    return admin.post("/api/transactions/manual",
                      json={"booking_date": date, "amount": amount, "description": desc})


def test_sort_by_absolute_amount_desc(admin):
    """amount_abs sortiert nach Betragshöhe unabhängig vom Vorzeichen."""
    _mktx(admin, "-500.00", "Miete")
    _mktx(admin, "2000.00", "Gehalt")
    _mktx(admin, "-12.50", "Bäcker")

    items = admin.get("/api/transactions?sort_by=amount_abs&sort_order=desc").json()["items"]
    amounts = [abs(float(t["amount"])) for t in items]
    assert amounts == [2000.0, 500.0, 12.5]

    items = admin.get("/api/transactions?sort_by=amount_abs&sort_order=asc").json()["items"]
    amounts = [abs(float(t["amount"])) for t in items]
    assert amounts == [12.5, 500.0, 2000.0]


def test_sort_by_absolute_amount_within_expenses(admin):
    """Nur Ausgaben + amount_abs desc = größte Ausgabe zuerst (User-Case)."""
    _mktx(admin, "-5.00", "Klein")
    _mktx(admin, "-999.00", "Groß")
    _mktx(admin, "-50.00", "Mittel")
    _mktx(admin, "1000.00", "Einnahme")  # muss durch Filter rausfallen

    items = admin.get(
        "/api/transactions?amount_type=expenses&sort_by=amount_abs&sort_order=desc"
    ).json()["items"]
    descs = [t["counterpart_name"] for t in items]
    assert descs == ["Groß", "Mittel", "Klein"]


def test_invalid_sort_by_rejected(admin):
    assert admin.get("/api/transactions?sort_by=drop_table").status_code == 422
