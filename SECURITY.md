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
  Changing a password bumps the user's `token_version`, invalidating all previously
  issued tokens (other devices/stolen refresh tokens). Login timing is equalized
  (dummy bcrypt compare) so response time doesn't reveal whether an email exists.
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
- **Request-body limits:** JSON endpoints reject bodies > 2 MB; uploads are read in
  chunks and aborted at their per-endpoint limit instead of buffering in RAM.

## Deployment hardening checklist

- Set a strong **`SECRET_KEY`** ≥ 32 chars (or let it auto-generate to `data/.secret_key` and keep that file private).
- Run with **`DEBUG=false`** in production (disables API docs + reload).
- Behind HTTPS, set **`COOKIE_SECURE=true`** (otherwise auth cookies are dropped — and are sent in clear without TLS). The production compose files set this.
- Terminate **TLS** at a reverse proxy — either the bundled Traefik (`docker-compose.yml`)
  or your own nginx (`docker-compose.nginx.yml` + `docs/nginx-finanzmanager.conf.example`).
- **Behind a reverse proxy, set `FORWARDED_ALLOW_IPS`** (e.g. `*` when the app is only
  reachable through the proxy). Without it, rate limits and the audit log see the proxy's
  IP for every client — one shared rate-limit bucket means any visitor can starve everyone.
  Never set it when the app port is directly reachable (the header would be spoofable).
- **Finish first-user setup before exposing the instance.** While the user table is empty,
  `POST /api/auth/register` is open and whoever registers first becomes admin.
- Keep the **`data/`** directory private (it holds the SQLite DB, secret key, and audit log).
- Set **`ALLOWED_ORIGINS`** only if you serve the API cross-origin; leave empty for same-origin.
- **For internet exposure, add a second factor in front:** the app has no built-in 2FA.
  A VPN (WireGuard/Tailscale) is the recommended remote-access path; alternatively put a
  forward-auth gate (e.g. Authelia/Authentik with TOTP) on the reverse proxy.
- Optional: **fail2ban/CrowdSec** on `data/logs/audit.log` (`login_failed` events carry the
  client IP once `FORWARDED_ALLOW_IPS` is configured) or on the proxy access log.

## Known issues being tracked

- **`PYSEC-2026-87` (lxml):** pulled in transitively by `python-fints` (which pins
  `lxml~=6.0.2`, so the patched 6.1.0 can't be selected yet). `lxml` here only parses
  responses from the bank over HTTPS, not arbitrary user input. CI runs `pip-audit` with
  this single advisory ignored; it will be removed once `python-fints` loosens its pin.
