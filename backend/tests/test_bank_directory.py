"""Bank-Verzeichnis: Suche nach Name/Ort/BLZ -> BLZ + FinTS-URL."""

import json
import os

import pytest

from app.services import bank_directory

_TEST_BANKS = [
    {"blz": "50010517", "name": "ING-DiBa", "ort": "Frankfurt am Main", "bic": "INGDDEFFXXX",
     "url": "https://fints.ing.de/fints/"},
    {"blz": "44060414", "name": "Dortmunder Volksbank", "ort": "Dortmund", "bic": "GENODEM1DOR",
     "url": "https://fints2.atruvia.de/cgi-bin/hbciservlet"},
    {"blz": "10090000", "name": "Berliner Volksbank", "ort": "Berlin", "bic": "BEVODEBBXXX",
     "url": "https://fints2.atruvia.de/cgi-bin/hbciservlet"},
    {"blz": "70033100", "name": "Baader Bank AG", "ort": "Unterschleißheim", "bic": "BDWBDEMMXXX",
     "url": "https://fints.baaderbank.de"},
]


@pytest.fixture
def bank_dir(tmp_path):
    """Provide a temporary bank directory file and point the service at it."""
    path = tmp_path / "banks.json"
    path.write_text(json.dumps(_TEST_BANKS), encoding="utf-8")
    os.environ["BANK_DIRECTORY_PATH"] = str(path)
    bank_directory.reset_cache()
    yield
    os.environ.pop("BANK_DIRECTORY_PATH", None)
    bank_directory.reset_cache()


def test_search_by_blz_prefix(bank_dir):
    results = bank_directory.search_banks("50010")
    assert len(results) == 1
    assert results[0]["blz"] == "50010517"
    assert results[0]["url"] == "https://fints.ing.de/fints/"


def test_search_by_name(bank_dir):
    results = bank_directory.search_banks("ing")
    assert any(b["blz"] == "50010517" for b in results)


def test_search_multi_token_name_and_city(bank_dir):
    # both tokens must match across name+ort -> only Dortmund, not Berlin
    results = bank_directory.search_banks("volksbank dortmund")
    assert len(results) == 1
    assert results[0]["blz"] == "44060414"


def test_search_umlaut_city(bank_dir):
    results = bank_directory.search_banks("unterschleißheim")
    assert len(results) == 1
    assert results[0]["name"] == "Baader Bank AG"


def test_search_too_short_returns_empty(bank_dir):
    assert bank_directory.search_banks("a") == []


def test_get_bank_by_blz_ignores_spaces(bank_dir):
    bank = bank_directory.get_bank_by_blz("500 105 17")
    assert bank is not None
    assert bank["name"] == "ING-DiBa"


def test_missing_directory_is_graceful(tmp_path):
    os.environ["BANK_DIRECTORY_PATH"] = str(tmp_path / "does-not-exist.json")
    bank_directory.reset_cache()
    try:
        assert bank_directory.search_banks("volksbank") == []
        assert bank_directory.get_bank_by_blz("50010517") is None
    finally:
        os.environ.pop("BANK_DIRECTORY_PATH", None)
        bank_directory.reset_cache()


def test_search_endpoint_requires_auth_and_returns_hits(admin, bank_dir):
    r = admin.get("/api/banking/banks?q=volksbank")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2  # Dortmunder + Berliner Volksbank
    assert {b["blz"] for b in data} == {"44060414", "10090000"}


def test_search_endpoint_min_length(admin, bank_dir):
    # q shorter than 2 chars is rejected by the query validator
    assert admin.get("/api/banking/banks?q=a").status_code == 422


def test_search_endpoint_unauthenticated(make_api, bank_dir):
    anon = make_api()  # API instance, not logged in
    assert anon.get("/api/banking/banks?q=ing").status_code == 401
