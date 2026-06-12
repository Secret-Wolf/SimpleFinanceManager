# Übergabe / offene Punkte

> Arbeitsdokument — kann gelöscht werden, sobald die Punkte erledigt sind.
> Vollständiger Projektstand: siehe **CLAUDE.md** (Abschnitt „Project status (Stand 2026-06-12)").

## Erledigt (Session 2026-06-12, committet)

- **Tiefe Kategorien** (bis 5 Ebenen, z. B. Mobilität > Auto > Tanken) inkl. Statistik-Roll-up,
  `include_subcategories` über alle Ebenen, Frontend-Dropdowns/Einrückung. Keine Migration nötig.
- **Regeln:** grüner/roter Aktiv-Indikator in der Liste; **Regel-Sets** (`group_name`,
  additive Migration 16) mit Auswahl-Modal bei „Regeln anwenden"
  (`POST /api/rules/apply` + optional `{"rule_ids": [...]}`).
- Tests: 32 grün, ruff/bandit sauber; Migration gegen Kopie einer Bestands-DB verifiziert.

**Achtung:** Diese Features sind noch **nicht** im zuletzt gepushten Image (digest `0007d9a6…`).
Wenn sie auf den Server sollen: neu bauen & pushen (siehe CLAUDE.md „Deployment").

## Offene Verifikation aus der FinTS-Session (user-seitig, falls noch nicht erledigt)

- [ ] Server-Deploy ok (`docker compose ps` → healthy, Login funktioniert, altes Datenbild intakt)
- [ ] Erster FinTS-Abruf ab **24.04.2026** → keine Duplikate, Konto per IBAN verknüpft (kein neues Konto)
- [ ] Danach: Backup `~/SimpleFinanceManagerBACKUP` kann (irgendwann) weg
