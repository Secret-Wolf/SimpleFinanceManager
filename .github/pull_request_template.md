<!-- Thanks for contributing! Keep PRs focused. -->

## What & why

<!-- What does this change and why? Link any related issue. -->

## Checklist

- [ ] `ruff check backend` passes
- [ ] `pytest` passes (added/updated tests for behavior changes)
- [ ] `bandit -r backend/app` and `pip-audit` clean
- [ ] Schema change? Updated **both** `models.py` and an additive block in `migrations.py`
- [ ] New transaction-reading endpoint? Reproduced the per-user isolation filter
- [ ] No inline JS; user/imported text is `escapeHtml()`-ed
