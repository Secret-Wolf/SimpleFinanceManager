# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Self-hosted personal-finance web app ("Finanzmanager"). German users import bank CSV exports, categorize transactions, and view stats. FastAPI backend serves a no-build vanilla-JS SPA from the same origin; data lives in a single SQLite file. UI strings, comments, and commit messages are in German.

## Commands

There is **no frontend build step** (vanilla JS, served as-is — no `npm`). The backend has tests, linting, and security scans; run them from the repo root (config in `pyproject.toml`):

```bash
pytest                        # API test suite (backend/tests/, each test gets an isolated temp DB)
ruff check backend            # lint  (use `ruff format backend` to auto-format)
bandit -r backend/app         # security static analysis (SAST)
pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-87   # dependency CVEs
```

Install the tooling with `pip install -r backend/requirements-dev.txt`. CI (`.github/workflows/ci.yml`) runs all four on every push/PR. Beyond automated checks, verify behavior by running the app.

```powershell
# Local dev (from repo root). DEBUG=true enables uvicorn reload + API docs at /api/docs.
cd backend
python -m venv venv; venv\Scripts\activate
pip install -r requirements.txt
$env:DEBUG="true"; python run.py        # serves http://localhost:8000

# Docker, LAN-only (publishes :8000, DEBUG=true). SECRET_KEY is required.
$env:SECRET_KEY="local-dev-secret"; docker compose -f docker-compose.local.yml up -d

# Docker, production (Traefik + Let's Encrypt; app only `expose`d, not published)
docker compose up -d

# Build & push to the private registry referenced by the compose files
docker build -t finanzmanager:latest .
docker tag finanzmanager:latest 192.168.178.30:5000/finanzmanager:latest
docker push 192.168.178.30:5000/finanzmanager:latest
```

The frontend has no module bundler: edited JS/CSS in `frontend/` is served live. In Docker, the image bakes in `frontend/` and `backend/`, so rebuild the image to see changes; only `./data` is a volume.

## Deployment (home server)

Production runs on a home server at **192.168.178.30**, which hosts both a private Docker registry and the live container:

- **Registry:** `192.168.178.30:5000` (insecure/HTTP — the daemon pushing to it needs this host in its `insecure-registries`). Web UI (joxit/docker-registry-ui) at `http://192.168.178.30:8080`.
- **Live app:** container `finanzmanager` from `192.168.178.30:5000/finanzmanager:latest`, published on `:8000`.

**The image is not built on the server.** After any backend/frontend/Dockerfile change that should ship, build and push so the server can pull it:

```powershell
docker build -t finanzmanager:latest .
docker tag finanzmanager:latest 192.168.178.30:5000/finanzmanager:latest
docker push 192.168.178.30:5000/finanzmanager:latest
# then on the server: docker compose pull && docker compose up -d
```

Don't push unless the user asks — code changes alone don't require a push, only shipping does.

## Architecture

**Single process, single file.** `backend/app/main.py` is the whole server: it mounts `frontend/` at `/static`, serves `index.html` for every non-API path (SPA catch-all with a realpath traversal guard), and exposes all routers under `/api/*`. SQLite at `data/finanzmanager.db` via SQLAlchemy ORM (`models.py`), no Alembic.

**Two-phase schema management — both run on startup (`startup_event` in main.py).** When changing the schema you usually must touch **both**:
1. `models.py` — the ORM model (`init_db()` calls `create_all`, which only helps fresh DBs).
2. `migrations.py` — a hand-written, idempotent block that `inspect()`s the live DB and runs guarded `ALTER`/`CREATE` so **existing** databases upgrade in place. Follow the numbered pattern already there (check `inspector.get_columns(...)` before adding). Skipping step 2 breaks every deployed DB.

**Auth (`auth.py` + `routers/auth.py`).** JWT in two HttpOnly cookies: `access_token` (30 min) and `refresh_token` (7 d, path-scoped to `/api/auth/refresh`). `get_current_user` / `get_current_admin` are the dependency guards. The **first** registered user auto-becomes admin and inherits all pre-auth "legacy" data (`_assign_legacy_data_to_user`); afterward `POST /api/auth/register` is locked and admins create users via `register-user`. `SECRET_KEY` comes from env, else is auto-generated once and persisted (file-locked) to `data/.secret_key` so tokens survive restarts.

**Frontend** (`frontend/js/*.js`) is plain `<script>` tags loaded in a fixed order in `index.html`, all sharing one global scope (no imports/modules). `api` is a singleton `ApiClient`; app state is module-level globals in `app.js` (`currentPage`, `categories`, `accounts`, `selectedAccountId`). Boot sequence: `auth.js` `DOMContentLoaded` → `checkAuth()` → `showApp()/showLogin()/showSetup()` → `init()`. `api.js`'s request wrapper auto-retries once via `/api/auth/refresh` on a 401, then forces the login screen.

## Conventions you can't infer from a single file

**1. Per-user data isolation is manual and load-bearing.** Transactions have **no** `user_id`; ownership is derived `Account.user_id → Transaction.account_id`. Every transaction-touching endpoint repeats this idiom:
```python
user_account_ids = [a.id for a in db.query(Account.id).filter(Account.user_id == current_user.id).all()]
query.filter(Transaction.account_id.in_(user_account_ids) if user_account_ids else Transaction.id == -1)
```
The `Transaction.id == -1` sentinel is deliberate: a user with zero accounts must match **nothing** (an empty `IN ()` would otherwise misbehave). Categories and rules isolate directly via their own `user_id` column. **Any new endpoint that reads transactions must reproduce this filter or it leaks across users.**

**2. The categorizer service is user-scoped — pass `user_id`.** `services/categorizer.py` (`apply_rules_to_uncategorized(db, user_id)`, `apply_rules_to_all(db, user_id)`, `categorize_transaction(db, tx, user_id)`) matches only the user's own active rules against only that user's own accounts' transactions. Callers pass `current_user.id` (routers `rules.py`/`imports.py`) or the connection's `user_id` (FinTS import). It runs from `POST /api/rules/apply` and from CSV/FinTS import auto-categorization. (Earlier versions ran globally across all users — that was a cross-user bug; keep the `user_id` scoping when adding callers.)

**3. CSP bans inline JavaScript.** `main.py` sets `script-src 'self'` (no `unsafe-inline`), so inline `onclick`/`onchange` will silently not fire. UI wires behavior through `event-handlers.js`: elements carry `data-action="fnName"` plus `data-id`/`data-value`/`data-arg2`, and one document-level delegated listener dispatches to a global function or the `CLICK_ACTIONS` map (`data-onchange` for selects). Add interactivity that way — never inline handlers.

**4. German number/date handling is a hard requirement.** CSV input is `DD.MM.YYYY` and `1.234,56`; parsing lives in `services/csv_parser.py`. All money is `Decimal` / `Numeric(10,2)` end to end — **never float**. Amount sign carries meaning: negative = expense, positive = income. Duplicate detection hashes `booking_date|amount|counterpart_iban|purpose[:50]` → `import_hash` (unique). To add a bank, extend `SUPPORTED_FORMATS`, add a `parse_<bank>_csv` + column map, and a branch in `detect_csv_format` (currently `volksbank` and `ing`).

**5. Categories: 2 levels max, with a denormalized path cache.** Nesting deeper than parent→child is rejected in `routers/categories.py`. `full_path` ("Parent:Child") is a cache — call `update_full_path()` after any name/parent change.

**6. Split transactions use a parent/child sentinel.** The original is flagged `is_split_parent=True`, its category cleared, and **every** transaction query excludes it via `is_split_parent == False`. Children carry `parent_transaction_id`; the parts must sum to `abs(original.amount)`. Deleting the last child un-splits the parent. Mirror the `is_split_parent == False` filter in any new aggregation.

**7. Shared / household expenses.** `is_shared` transactions feed household stats that aggregate across all members' accounts (`routers/stats.py` → `get_shared_summary`). The `since_salary` period auto-detects the last income via a category literally named `Gehalt`, then a keyword scan with an exclude list (`find_last_salary_date`). The legacy `Profile` model/`profile_id` columns predate real auth and are mostly vestigial — current ownership is `User`/`Account`.

**8. Rule matching supports regex with a ReDoS guard.** `categorizer.match_pattern` accepts plain-contains, `*`/`%` wildcards, and `/regex/i`. Regex runs in a thread pool with a 2 s timeout and 2000-char input cap — preserve that when editing.

**9. FinTS/HBCI online banking (`services/fints_service.py` + `routers/banking.py`).** Read-only retrieval of balances/transactions from German banks via `python-fints`, as an alternative to CSV import. Key constraints:
- **The banking PIN is never persisted.** It is supplied per sync and held only in an **in-memory** pending-TAN store (`_pending` dict, RAM only, ~300 s TTL) for the duration of the TAN round-trip. There is intentionally no PIN column and no crypto module. A server restart drops in-flight TAN flows (user retries) — acceptable.
- **TAN flow is stateless across requests** using python-fints' `pause_dialog()`/`deconstruct()`/`response.get_data()` → `from_data()`/`resume_dialog()`/`send_tan()`. SCA is handled at `get_sepa_accounts()`; after `send_tan`, the whole collect is re-run in the authenticated dialog. Decoupled (approve-in-app) TANs are polled. `BankConnection.fints_system_data` persists the serialized client state (system-id continuity, **no credentials**).
- **Ingestion reuses the CSV path**: `generate_import_hash()` + `ensure_account_exists()` (so FinTS dedupes against CSV and links accounts by IBAN) and `apply_rules_to_uncategorized()`. Connections are user-isolated by `user_id`.
- **`product_id` is mandatory in python-fints v4+** and goes into the HKVVB "Produktbezeichnung" field (must be exactly the 25-char registration ID). `_FALLBACK_PRODUCT_ID` now holds the **real DK product-registration number for "SimpleFinanceManager"** (ships with the product; public identifier, not a secret); `FINTS_PRODUCT_ID` (env) overrides it. Atruvia/Volksbank strictly **enforces** registration — an unregistered ID is rejected with bank code **9078** "not registered" (surfaced as a misleading "Could not find system_id" because `_bootstrap_mode` swallows the SCA/error); ING is lenient. New dependency: `fints` in `requirements.txt`.
- **Diagnostics:** `_attach_code_recorder()` wraps the client's `_process_response` to capture the bank's real return codes (incl. internal sends, which `add_response_callback` misses) — they're logged and surfaced in the user-facing error. Useful when a bank fails with an opaque error.
- **Status:** **Both ING and Volksbank/Atruvia are verified working end-to-end** (import → dedup → auto-categorize). The DK product-registration number for "SimpleFinanceManager" (category *Web-Server*) is shipped as the default `_FALLBACK_PRODUCT_ID`, which resolved Atruvia's 9078 rejection — no env config needed. Note: for the tested Volksbank account, read access returned `3076 "Starke Kundenauthentifizierung nicht notwendig"` (no TAN required); other banks/accounts may still require a TAN, which the existing flow handles.

**Env vars added for this feature:** `DATABASE_PATH` (override the SQLite path — used to run a dedicated dev DB without touching `finanzmanager.db`) and `FINTS_PRODUCT_ID`/`FINTS_PRODUCT_VERSION`. The `bank_connections` table is added by an **additive** migration (Migration 15) — no existing table is altered.

Security-relevant actions log JSON lines to `data/logs/audit.log` via `audit.py` (IBANs masked); call `log_auth_event` / `log_data_event` for new sensitive operations.

## Project status (Stand 2026-06-12)

**Done & committed (`main`, working tree clean as of `1b7cd0f`):**
- **FinTS/HBCI online banking** — fully working, **both ING and Volksbank/Atruvia verified end-to-end** with the real DK product-registration ID (shipped as default). Read-only, PIN never persisted, TAN/decoupled flow, dedup against CSV imports.
- **Security/quality pass** — XSS escaping (`escapeHtml`/`safeColor`), per-user categorizer scoping (was a cross-user bug), SSRF guard on `fints_url`, CSV formula-injection neutralization, banking rate limit, pinned deps.
- **Tests & CI** — 26 pytest tests (`backend/tests/`), ruff/bandit/pip-audit, GitHub Actions, SECURITY.md, CONTRIBUTING.md, PR/issue templates.
- **UI rework "Modern Fintech"** — emerald accent, Inter (self-hosted, `frontend/fonts/`), slate neutrals, system-follow theme, responsive mobile layout, redesigned banking cards. CSP relaxed only for style *attributes* (`style-src-attr 'unsafe-inline'`); scripts stay strict.

**In progress (user-side, just initiated):**
- New image **built & pushed** to the private registry (`192.168.178.30:5000/finanzmanager:latest`, digest `0007d9a6…`). User deploys on the server (`cd ~/SimpleFinanceManager && docker compose pull && docker compose up -d`) **against the existing production DB** (802 transactions, 376 categorized, 80 categories, 19 rules, 2 users, account "Giro Young" DE36…8800). Migration is additive (adds `bank_connections` only).
- **First FinTS sync on the server must use "Umsätze ab" = 2026-04-24** (day after the last manually imported transaction) to avoid overlap duplicates with the old Excel-imported data. FinTS links to the existing account by IBAN — no duplicate account. Backup exists at `~/SimpleFinanceManagerBACKUP` on the server; keep until verified.
- Open verification: deploy succeeded, login works, transaction count = 802 + new ones, no dupes.

**Next planned features (user request, not yet started):**
1. **Deeper category nesting** — currently hard-limited to 2 levels (convention #5). Wanted: more detailed, deeper hierarchies. Touches `routers/categories.py` (depth checks), `full_path` cache, stats roll-up of sub-trees, frontend dropdowns/indentation (`generateCategoryOptions`), budget aggregation.
2. **Rules UX & rule sets** — (a) active/inactive state is hard to see in the rules list → clear visual indicator (e.g. green/red dot); (b) selectable *rule sets*: user picks which group of rules to run instead of always all (schema addition, e.g. group/tag on `categorization_rules` + checkbox UI + `apply` endpoint parameter; keep per-user scoping & migration pattern).

## Roadmap & product direction (read before changing the hosting model)

This is intended to become an open-source product (GitHub) and may later ship as a packaged app and/or with optional paid licenses.

**The load-bearing architectural constraint: stay "user-hosted" (the software-vendor model).** FinTS must run somewhere; keeping it on the user's own device/server (today's Docker model, or a future desktop/LAN build) means each user accesses *their own* bank with *their own* credentials — so this stays a *software product* (like Lexware/StarMoney/Hibiscus), not a regulated service. **A central/SaaS backend that accesses or aggregates users' bank accounts on your infrastructure would likely make this an Account Information Service (AISP) under PSD2 → BaFin licensing + GDPR processor obligations + holding users' banking data.** Do **not** add a "hosted server" / multi-tenant-cloud mode as a casual feature — it's a separate, legal-review-gated decision.

Planned directions, all compatible with user-hosting:
- **Packaged desktop app** (e.g. pywebview/Tauri wrapping the local FastAPI server + SQLite) for users who don't want to run Docker. FinTS still runs in the bundled backend.
- **iOS/Android app as a LAN client** to the user-hosted backend — python-fints can't run on mobile, so the backend stays the FinTS engine; the app is just a UI talking to it over the local network.
- **Manual, LAN-only PC↔phone sync** (no central server).
- **Monetization:** donations or selling the software (license/lifetime) is fine and needs no AISP license; only hosting/aggregating accounts yourself does.

**Product registration:** one DK product registration covers the whole product. Its `FINTS_PRODUCT_ID` is a public identifier (not a secret) and should ship with the code so end users don't each have to register; the env var still allows power-user overrides.
