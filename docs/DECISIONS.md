# Decisions

## 2026-11-10 — Postgres via Docker Compose on port 5433
Local Postgres 16 in docker-compose (host port 5433 to avoid clashing with a local Postgres). Same image in CI.

## 2026-11-10 — Local personal-data guard instead of gitleaks only
gitleaks is not installed locally and doesn't know the household's names. `scripts/check_no_personal_data.py` (git pre-commit hook) blocks any staged file containing a value from `config/profile.yaml` or a token-shaped string. gitleaks still runs in CI.

## 2026-11-10 — Repo remote not created automatically
Creating a GitHub repo publishes code; asked in INPUTS_NEEDED.md #1. Development continues locally, CI workflow is committed.
