# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Self-hosted personal-finance web app ("Finanzmanager"). German users import bank CSV exports, categorize transactions, and view stats. FastAPI backend serves a no-build vanilla-JS SPA from the same origin; data lives in a single SQLite file. UI strings, comments, and commit messages are in German.

## Commands

There is **no test suite, no linter, and no build step** — don't look for `pytest`/`ruff`/`npm`. Verify changes by running the app.

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

**2. The categorizer service is the exception — it is global, not user-scoped.** `services/categorizer.py` (`apply_rules_to_uncategorized`, `apply_rules_to_all`, `categorize_transaction`) queries **all** active rules against **all** transactions, ignoring user boundaries. It runs from `POST /api/rules/apply` and from CSV-import auto-categorization. Keep this in mind before assuming isolation holds everywhere.

**3. CSP bans inline JavaScript.** `main.py` sets `script-src 'self'` (no `unsafe-inline`), so inline `onclick`/`onchange` will silently not fire. UI wires behavior through `event-handlers.js`: elements carry `data-action="fnName"` plus `data-id`/`data-value`/`data-arg2`, and one document-level delegated listener dispatches to a global function or the `CLICK_ACTIONS` map (`data-onchange` for selects). Add interactivity that way — never inline handlers.

**4. German number/date handling is a hard requirement.** CSV input is `DD.MM.YYYY` and `1.234,56`; parsing lives in `services/csv_parser.py`. All money is `Decimal` / `Numeric(10,2)` end to end — **never float**. Amount sign carries meaning: negative = expense, positive = income. Duplicate detection hashes `booking_date|amount|counterpart_iban|purpose[:50]` → `import_hash` (unique). To add a bank, extend `SUPPORTED_FORMATS`, add a `parse_<bank>_csv` + column map, and a branch in `detect_csv_format` (currently `volksbank` and `ing`).

**5. Categories: 2 levels max, with a denormalized path cache.** Nesting deeper than parent→child is rejected in `routers/categories.py`. `full_path` ("Parent:Child") is a cache — call `update_full_path()` after any name/parent change.

**6. Split transactions use a parent/child sentinel.** The original is flagged `is_split_parent=True`, its category cleared, and **every** transaction query excludes it via `is_split_parent == False`. Children carry `parent_transaction_id`; the parts must sum to `abs(original.amount)`. Deleting the last child un-splits the parent. Mirror the `is_split_parent == False` filter in any new aggregation.

**7. Shared / household expenses.** `is_shared` transactions feed household stats that aggregate across all members' accounts (`routers/stats.py` → `get_shared_summary`). The `since_salary` period auto-detects the last income via a category literally named `Gehalt`, then a keyword scan with an exclude list (`find_last_salary_date`). The legacy `Profile` model/`profile_id` columns predate real auth and are mostly vestigial — current ownership is `User`/`Account`.

**8. Rule matching supports regex with a ReDoS guard.** `categorizer.match_pattern` accepts plain-contains, `*`/`%` wildcards, and `/regex/i`. Regex runs in a thread pool with a 2 s timeout and 2000-char input cap — preserve that when editing.

Security-relevant actions log JSON lines to `data/logs/audit.log` via `audit.py` (IBANs masked); call `log_auth_event` / `log_data_event` for new sensitive operations.
