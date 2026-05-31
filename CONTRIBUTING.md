# Contributing

Thanks for your interest! This is a self-hosted personal-finance app (German UI):
FastAPI backend + a no-build vanilla-JS frontend + SQLite.

## Dev setup

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate   |   Linux/macOS: source venv/bin/activate
pip install -r requirements-dev.txt        # runtime + test/lint/security tools

# Run against a throwaway DB so you never touch real data:
DATABASE_PATH=../data/dev.db DEBUG=true python run.py   # http://localhost:8000
```

Frontend has **no build step** — edit files in `frontend/` and reload the browser.

## Checks (all must pass; CI runs them on every PR)

Run from the repo root:

```bash
ruff check backend            # lint   (ruff format backend  to auto-format)
pytest                        # tests  (config in pyproject.toml)
bandit -r backend/app         # security static analysis
pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-87   # dependency CVEs
```

Add tests for new endpoints under `backend/tests/` (FastAPI `TestClient`; the harness gives
each test an isolated temp DB).

## Conventions you must follow

These are easy to get wrong — see `CLAUDE.md` for the full picture:

1. **Schema changes touch two files.** Update the ORM model in `models.py` **and** add a
   guarded, additive block in `migrations.py` (check the inspector before `ALTER`/`CREATE`)
   so existing databases upgrade in place. Never alter/drop existing columns destructively.
2. **Per-user isolation is manual and load-bearing.** Any endpoint reading transactions must
   scope to the user's own accounts (`Account.user_id → Transaction.account_id`, with the
   `id == -1` empty-set sentinel). Categories/rules scope by their `user_id`. Add a test.
3. **No inline JavaScript** (CSP `script-src 'self'`). Wire UI via `data-action` attributes +
   the delegated listeners in `event-handlers.js`. Always `escapeHtml()` user/imported text
   rendered into `innerHTML`, and `safeColor()` colors injected into `style="..."`.
4. **Money is `Decimal` / `Numeric(10,2)` end to end — never `float`.** Amount sign matters
   (negative = expense). German formats: dates `DD.MM.YYYY`, numbers `1.234,56`.
5. **Keep the UI/commit messages German**; backend code/comments are English.

## Pull requests

- Keep changes focused; describe what and why.
- Make sure CI is green (the four checks above).
- For new bank CSV formats or FinTS behavior, include a small sample/fixture and a test.
