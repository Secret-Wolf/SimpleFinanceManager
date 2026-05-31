# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead use GitHub's
private vulnerability reporting (the repository's **Security → Report a vulnerability**
tab). Include steps to reproduce and the affected version/commit. You'll get a response
as soon as possible.

## Security model

Finanzmanager is **self-hosted software**: each user runs their own instance and accesses
**their own** bank account with **their own** credentials. The maintainers never operate a
server that touches user data. This keeps the project a software product (not a hosted
account-information service). Do not turn it into a central/multi-tenant SaaS without
understanding the regulatory consequences (PSD2/AISP, GDPR data-processor duties).

The realistic threat model is a small number of trusted users (a person/household) on a
private network or behind an authenticating reverse proxy — not an anonymous public service.

## Built-in protections

- **Auth:** JWT in HttpOnly, `SameSite=Strict` cookies; passwords hashed with bcrypt; a
  password policy (≥12 chars, upper/lower/digit); login + registration rate-limited.
- **Per-user isolation:** every data read is scoped to the user's own accounts/categories/
  rules (see `CLAUDE.md` for the load-bearing idiom). Covered by automated tests.
- **Headers:** strict Content-Security-Policy (`script-src 'self'`, no inline JS),
  `X-Frame-Options: DENY`, `nosniff`, HSTS (when not in debug).
- **FinTS/online banking:** the banking **PIN is never persisted** (held in memory only for
  the TAN round-trip); the user-supplied FinTS URL is checked against internal/loopback
  targets (SSRF guard); the sync endpoint is rate-limited.
- **Output handling:** user/imported text is HTML-escaped on render; CSV exports neutralize
  spreadsheet formula injection.
- **Audit log:** security-relevant events are written to `data/logs/audit.log` (IBANs masked).

## Deployment hardening checklist

- Set a strong **`SECRET_KEY`** (or let it auto-generate to `data/.secret_key` and keep that file private).
- Run with **`DEBUG=false`** in production (disables API docs + reload).
- Behind HTTPS, set **`COOKIE_SECURE=true`** (otherwise auth cookies are dropped — and are sent in clear without TLS).
- Terminate **TLS** at a reverse proxy (the production compose uses Traefik + Let's Encrypt).
- Keep the **`data/`** directory private (it holds the SQLite DB, secret key, and audit log).
- Set **`ALLOWED_ORIGINS`** only if you serve the API cross-origin; leave empty for same-origin.

## Known issues being tracked

- **`PYSEC-2026-87` (lxml):** pulled in transitively by `python-fints` (which pins
  `lxml~=6.0.2`, so the patched 6.1.0 can't be selected yet). `lxml` here only parses
  responses from the bank over HTTPS, not arbitrary user input. CI runs `pip-audit` with
  this single advisory ignored; it will be removed once `python-fints` loosens its pin.
