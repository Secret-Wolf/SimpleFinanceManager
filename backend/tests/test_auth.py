"""Authentication & registration flow."""


def test_setup_required_then_first_user_becomes_admin(api):
    assert api.get("/api/auth/setup-required").json() == {"setup_required": True}

    user = api.register_admin()
    assert user["is_admin"] is True
    assert api.get("/api/auth/setup-required").json() == {"setup_required": False}

    me = api.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@test.de"


def test_public_registration_locked_after_first_user(api, make_api):
    api.register_admin()
    # A fresh (unauthenticated) client must not be able to self-register
    other = make_api()
    r = other.post("/api/auth/register",
                   json={"email": "x@test.de", "password": "TestPasswort123", "display_name": "Xavier"})
    assert r.status_code == 403


def test_weak_password_rejected(api):
    r = api.post("/api/auth/register",
                 json={"email": "a@test.de", "password": "short", "display_name": "Alice"})
    assert r.status_code == 422  # password policy (Pydantic validation)


def test_me_requires_auth(api):
    assert api.get("/api/auth/me").status_code == 401


def test_login_wrong_password(admin):
    bad = admin.post("/api/auth/login", json={"email": "admin@test.de", "password": "WrongPasswort1"})
    assert bad.status_code == 401


def test_admin_can_create_user_but_normal_user_cannot(admin, make_api):
    admin.create_user("member@test.de", name="Member")

    member = make_api()
    member.login("member@test.de")
    # member is not admin → cannot create users
    r = member.post("/api/auth/register-user",
                    json={"email": "z@test.de", "password": "TestPasswort123", "display_name": "Z"})
    assert r.status_code == 403
