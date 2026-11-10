# Runbook (local Mac mode, no cost)

The watcher is a normal Python process; polling uses no Claude tokens and no paid services.

| Task | Command |
|---|---|
| Start now (foreground) | `uv run python -m flathunter.ops.main watch` |
| Start at every login + auto-restart | `sh scripts/launchd/install.sh` |
| Stop and remove autostart | `sh scripts/launchd/uninstall.sh` |
| Watch logs | `tail -f logs/watcher.log` |
| Per-source status | `cat logs/health.json` |
| One manual poll | `uv run python -m flathunter.ops.main run-once <source> --notify` |

## Requirements while it runs
- Mac awake and online. `caffeinate -i` stops idle sleep; closing the lid or manual sleep pauses polling.
- Docker Desktop running (Postgres container `postgres` has `restart: unless-stopped`). Enable Docker Desktop → Settings → "Start Docker Desktop when you sign in".
- `.env` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## After the Mac was off or asleep
The first poll after waking sends alerts for every still-open flat that was never alerted, so nothing is lost except speed.

## Alerts about the system itself
A source failing 3 polls in a row sends a Telegram warning, and another message when it recovers.
