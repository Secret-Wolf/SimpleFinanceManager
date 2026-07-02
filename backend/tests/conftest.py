"""Pytest harness.

Configures the app for testing BEFORE importing it (config reads env at import time):
an isolated temp SQLite DB, a fixed test SECRET_KEY, and effectively-disabled rate
limiting. The real `data/finanzmanager.db` is never touched.
"""

import os
import tempfile

import pytest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_PATH"] = _tmp.name
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["DEBUG"] = "true"
os.environ["COOKIE_SECURE"] = "false"
# Effectively disable rate limiting so the suite isn't throttled
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000000"
os.environ["BANKING_SYNC_RATE_LIMIT_PER_MINUTE"] = "1000000"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

PW = "TestPasswort123"  # satisfies the password policy (12+, upper/lower/digit)


class API:
    """Thin wrapper around a TestClient with auth helpers. Cookies persist per client."""

    def __init__(self):
        self.client = TestClient(app)

    # auth
    def register_admin(self, email="admin@test.de", name="Admin", password=PW):
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": password, "display_name": name})
        assert r.status_code == 201, r.text
        return r.json()

    def create_user(self, email, name="User", password=PW):
        """Admin-only: create another user (caller must be logged in as admin)."""
        r = self.client.post("/api/auth/register-user",
                             json={"email": email, "password": password, "display_name": name})
        assert r.status_code == 201, r.text
        return r.json()

    def login(self, email, password=PW):
        r = self.client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r

    # convenience
    def get(self, *a, **k):
        return self.client.get(*a, **k)

    def post(self, *a, **k):
        return self.client.post(*a, **k)

    def patch(self, *a, **k):
        return self.client.patch(*a, **k)

    def delete(self, *a, **k):
        return self.client.delete(*a, **k)


@pytest.fixture(autouse=True)
def fresh_db():
    """Recreate the schema before each test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def make_api():
    """Factory for independent API clients (separate cookie jars → multi-user tests)."""
    return API


@pytest.fixture
def api():
    """A single API client (no user yet)."""
    return API()


@pytest.fixture
def admin():
    """An API client already registered + logged in as the first user (admin)."""
    a = API()
    a.register_admin()  # registration auto-logs-in via cookies
    return a
