# Übergabe / Prompt für die nächste Session

> Arbeitsdokument — kann gelöscht werden, sobald die Punkte umgesetzt sind.
> Vollständiger Projektstand: siehe **CLAUDE.md** (Abschnitt „Project status (Stand 2026-06-12)").

## Prompt zum Kopieren in den neuen Chat

```
Lies zuerst CLAUDE.md (insb. „Project status (Stand 2026-06-12)" und die Konventionen).

Kurzfassung wo wir stehen:
- FinTS-Online-Banking läuft end-to-end (ING + Volksbank/Atruvia, registrierte DK-Produkt-ID
  ist im Code). Security-Pass, 26 Tests, CI und das „Modern Fintech"-UI-Rework sind committet.
- Letzter Schritt der Vorsession: neues Image wurde in die private Registry gepusht
  (192.168.178.30:5000/finanzmanager:latest). Ich habe auf dem Server deployed bzw. bin dabei.
  Falls ich Probleme melde: Produktions-DB hat 802 Transaktionen / 80 Kategorien / 19 Regeln /
  2 User; Backup liegt in ~/SimpleFinanceManagerBACKUP; erster FinTS-Abruf muss mit
  „Umsätze ab 24.04.2026" laufen, damit es keine Duplikate mit den alten Excel-Importen gibt.

Jetzt möchte ich zwei Verbesserungen umsetzen (bitte erst planen, dann bauen):

1) Detailliertere / tiefer verschachtelte Kategorien
   - Aktuell sind Kategorien hart auf 2 Ebenen begrenzt (Konvention #5 in CLAUDE.md).
   - Ich will tiefere Hierarchien (z.B. Mobilität > Auto > Tanken).
   - Zu beachten: Tiefen-Checks in routers/categories.py, full_path-Cache (update_full_path),
     Statistik-Roll-up über Teilbäume, include_subcategories-Filter (holt aktuell nur 1 Ebene
     Kinder!), Frontend-Dropdowns/Einrückung (generateCategoryOptions), Monatsbudget-Aggregation,
     Migration nicht nötig (parent_id existiert schon) — aber Tests anpassen/ergänzen.

2) Regeln: Sichtbarkeit + Regel-Sets
   a) In der Regelliste ist kaum erkennbar, welche Regel aktiv/inaktiv ist
      → klarer visueller Indikator (z.B. grüner/roter Punkt), passend zum neuen Design-System.
   b) Ich möchte auswählen können, WELCHE Regeln bei „Regeln anwenden" laufen
      (Regel-Sets/Gruppen oder Checkbox-Auswahl), statt immer alle.
      → braucht vermutlich Schema-Erweiterung an categorization_rules (Gruppe/Tag) —
        dann BEIDE Stellen: models.py UND additive Migration in migrations.py (Muster beachten),
        UI (Checkboxen/Gruppenfilter) CSP-konform über data-action,
        /api/rules/apply um Auswahl-Parameter erweitern, User-Scoping beibehalten, Tests ergänzen.

Konventionen aus CLAUDE.md strikt einhalten (User-Isolation, Decimal, CSP/event-handlers,
deutsche UI, ruff/pytest grün). Entwickeln/Testen gegen die Dev-DB (DATABASE_PATH), nicht
gegen data/finanzmanager.db. Am Ende nicht ungefragt pushen.
```

## Offene Verifikation aus der Vorsession (falls noch nicht erledigt)
- [ ] Server-Deploy ok (`docker compose ps` → healthy, Login funktioniert, altes Datenbild intakt)
- [ ] Erster FinTS-Abruf ab **24.04.2026** → keine Duplikate, Konto per IBAN verknüpft (kein neues Konto)
- [ ] Danach: Backup `~/SimpleFinanceManagerBACKUP` kann (irgendwann) weg
