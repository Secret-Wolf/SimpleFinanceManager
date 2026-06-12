# Übergabe / offene Punkte

> Arbeitsdokument — kann gelöscht werden, sobald die Punkte erledigt sind.
> Vollständiger Projektstand: siehe **CLAUDE.md** (Abschnitt „Project status (Stand 2026-06-13)").

## Erledigt (Sessions 2026-06-12/13, committet)

- **Tiefe Kategorien** (bis 5 Ebenen) inkl. Statistik-Roll-up und Dropdowns über alle Ebenen.
- **Regeln:** Aktiv-Indikator + **Regel-Sets** (Migration 16) mit Auswahl-Modal beim Anwenden.
- **Budgets fertiggestellt:** `GET /api/stats/budgets` + Budget-Karte (Fortschrittsbalken) auf der
  Statistik-Seite; „Ist" = Teilbaum-Ausgaben des Monats.
- **Umbuchungserkennung** (`is_transfer`, Migration 17): automatisch bei jedem Import (auch
  rückwirkend), manueller Toggle, Filter, ⇄-Badge; Statistiken ignorieren Umbuchungen.
- **Backup/Restore** (Admin): DB-Download + validierte Wiederherstellung mit Sicherheitskopie,
  Karte auf der Benutzerverwaltungs-Seite.
- Modernisierung (lifespan/ConfigDict), **FinTS-PDF aus Git-Tracking entfernt** (Historie!).
- Tests: 41 grün, ruff/bandit sauber; Migrationen gegen Bestands-DB-Kopie verifiziert.

**Image gepusht (2026-06-13, digest `fb8f897b…`):** alle o. g. Features sind in
`192.168.178.30:5000/finanzmanager:latest`. Auf dem Server nur noch:
`docker compose pull && docker compose up -d` (Migrationen 16+17 laufen automatisch, additiv).

## Nächste geplante Schritte (besprochen 2026-06-13)

1. **Public-Repo-Vorbereitung** (siehe CLAUDE.md → „Publication prep"): frisches Repo ohne
   Historie, Lizenz-Entscheidung (MIT vs. AGPL) **vor** dem ersten Public-Commit, Compose
   generisch + ghcr-Release-Workflow, neue Screenshots mit Demo-Daten, README-Disclaimer.
2. **PWA-Schritt** (Manifest + Service Worker) als günstige „Companion App"-Stufe 1.
3. Optional: Scalable-Capital-FinTS testen (eigenes Depot/Tagesgeld des Nutzers).

## Offene Verifikation aus der FinTS-Session (user-seitig, falls noch nicht erledigt)

- [ ] Server-Deploy ok (`docker compose ps` → healthy, Login funktioniert, altes Datenbild intakt)
- [ ] Erster FinTS-Abruf ab **24.04.2026** → keine Duplikate, Konto per IBAN verknüpft (kein neues Konto)
- [ ] Danach: Backup `~/SimpleFinanceManagerBACKUP` kann (irgendwann) weg
