# CLAUDE.md — Berlin WBS flat hunter

Purpose: detect Berlin WBS-eligible flats within minutes, classify eligibility (SPEC.md §2), alert via Telegram. SPEC.md is the brief; deviations go in docs/DECISIONS.md.

## Commands
- Setup: `uv sync && sh scripts/install_hooks.sh && docker compose up -d` (Postgres on :5433)
- Test: `uv run pytest` · Lint: `uv run ruff check .` · Types: `uv run mypy`
- Migrate: `uv run alembic upgrade head`
- Run a collector once: `uv run python -m flathunter.ops.main run-once <source_id>`
- Live smoke (hits real sites): `uv run pytest -m live`

## Conventions
- Collectors implement `collectors/base.py`; raise `LayoutChangedError` on zero/invalid items, never return silently empty. Each has fixture tests from saved real responses in `tests/fixtures/<source>/`.
- Config in `config/*.yaml`; numbers (rent limits) and patterns (WBS) are data, not code.

## Guardrails
- Never commit secrets or personal data. `config/profile.yaml` and `.env` are git-ignored; read the profile at runtime only. Fixtures, tests and logs use fake data (the pre-commit hook blocks real profile values).
- Respect robots.txt/ToS, rate-limit, no CAPTCHA/anti-bot evasion (fall back to email alerts).
- Never apply on Arko's behalf without per-source opt-in. Fail loudly.
- Needing input from Arko → add to INPUTS_NEEDED.md and continue with unblocked work.
