# Finanzmanager als Android-App (PWA)

Der Finanzmanager ist eine installierbare **Progressive Web App**: Auf dem
Handy installiert startet er als eigene App (Vollbild, eigenes Icon, App-Switcher-
Eintrag) und spricht direkt mit dem selbst gehosteten Server — im WLAN oder
unterwegs per VPN (WireGuard/Tailscale). Es gibt bewusst keine Store-App und
keine App mit eigener Datenbank: Der Server bleibt die einzige Datenquelle
(siehe Roadmap in CLAUDE.md).

## Voraussetzung: HTTPS

Chrome installiert PWAs nur aus einem **Secure Context**. Über
`http://192.168.178.30:8000` läuft die Seite zwar (responsive, voll nutzbar),
aber ohne Installation und ohne Service Worker. Es braucht also HTTPS:

- **Empfohlen: eigener nginx davor** (`docker-compose.nginx.yml` +
  `docs/nginx-finanzmanager.conf.example`): App an `127.0.0.1:8000` binden,
  nginx terminiert TLS. Zertifikat z. B. Let's Encrypt; wenn die Domain nicht
  öffentlich erreichbar sein soll, per **DNS-01-Challenge** ausstellen und
  intern (lokaler DNS/hosts) auf die Server-IP zeigen.
- Selbstsigniertes Zertifikat geht nur, wenn dessen CA auf dem Handy als
  Nutzer-CA installiert wird — funktioniert, ist aber fummelig.
- `localhost` zählt als Secure Context (relevant nur für Entwicklung).

## Installation auf Android

1. Server-URL in Chrome öffnen (per HTTPS, im WLAN oder via VPN).
2. Anmelden, dann Menü (⋮) → **„App installieren"** / „Zum Startbildschirm
   hinzufügen".
3. Die App erscheint mit dem grünen €-Icon im Launcher und startet standalone.

Auf iOS analog: Safari → Teilen → „Zum Home-Bildschirm".

## Was die PWA technisch macht

- `frontend/manifest.json` — Name, Icons (inkl. maskable), `display: standalone`.
- `frontend/sw.js` — Service Worker, wird über den SPA-Catch-all unter `/sw.js`
  ausgeliefert (Scope = ganze App). Strategie: **Netz zuerst, Cache nur als
  Offline-Fallback** — nach einem Deploy gibt es nie veraltete JS/CSS-Stände.
  `/api/*` wird nie gecacht (Finanzdaten, Auth).
- Offline-Start zeigt die App-Shell (Login-Screen); ohne Server geht inhaltlich
  nichts — gewollt, es gibt keine lokale Datenhaltung.
- `theme-color` folgt dem Dark Mode (auth.js `applyTheme`).
- Mobile-Layout: Bottom-Navigation, Bottom-Sheet-Modals, Transaktionsliste als
  Karten — alles in `frontend/css/style.css` (`@media (max-width: 768px)`).

## Stolperfallen

- **Kein horizontaler Overflow auf Mobil einführen!** Chrome (Android) zoomt
  sonst die ganze Seite heraus und fixierte Elemente (Bottom-Nav, Modal-Footer)
  hängen außerhalb des sichtbaren Bereichs. Nowrap-Button-Gruppen sind der
  Klassiker; `body { overflow-x: clip }` im Mobile-Block fängt Restfälle ab.
- Neue Frontend-Dateien in die `SHELL_ASSETS`-Liste in `frontend/sw.js`
  aufnehmen, wenn sie zur App-Shell gehören (nur für den Offline-Start relevant).
- Kein `<style>`-Element per JS injizieren — die CSP (`style-src 'self'`)
  blockt das stumm (war der Grund für unsichtbare Statistik-Charts).
