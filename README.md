# berlin-flat-hunter
Private tool: finds Berlin WBS flats and alerts quickly. See SPEC.md, CLAUDE.md, docs/.

```bash
uv sync && sh scripts/install_hooks.sh && docker compose up -d
uv run alembic upgrade head
uv run python -m flathunter.ops.main run-once inberlinwohnen
uv run python -m flathunter.ops.main run-once degewo
uv run pytest
```
