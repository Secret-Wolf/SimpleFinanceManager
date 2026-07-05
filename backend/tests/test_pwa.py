"""PWA-Auslieferung.

Der Service Worker MUSS an der Wurzel liegen (/sw.js), sonst umfasst sein Scope
nicht die ganze App; ausgeliefert wird er über den SPA-Catch-all in main.py,
der Dateien aus frontend/ auch ohne /static-Präfix serviert. Diese Tests
sichern das Routing + die Manifest-Grundstruktur ab.
"""


def test_manifest_wird_ausgeliefert(api):
    r = api.get("/manifest.json")
    assert r.status_code == 200
    data = r.json()
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert any(icon["sizes"] == "512x512" for icon in data["icons"])


def test_service_worker_an_der_wurzel(api):
    r = api.get("/sw.js")
    assert r.status_code == 200
    # Muss als JavaScript kommen (nosniff!) und der echte SW sein, nicht die SPA-index.html
    assert "javascript" in r.headers["content-type"]
    assert "networkFirst" in r.text
    assert "<!DOCTYPE html>" not in r.text


def test_icons_erreichbar(api):
    for path in (
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png",
        "/static/icons/icon-maskable-512.png",
        "/static/icons/apple-touch-icon.png",
    ):
        r = api.get(path)
        assert r.status_code == 200, path
        assert r.headers["content-type"] == "image/png", path


def test_unbekannter_pfad_liefert_weiter_die_spa(api):
    r = api.get("/irgendeine/spa-route")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
