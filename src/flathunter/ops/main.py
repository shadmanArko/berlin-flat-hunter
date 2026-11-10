"""CLI: `python -m flathunter.ops.main run-once <source_id> [--max-pages N]`."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

from flathunter.core.db import get_session_factory
from flathunter.core.profile import load_profile
from flathunter.notify.dispatch import dispatch_new, handle_callbacks
from flathunter.notify.telegram import ConsoleSender, TelegramSender
from flathunter.ops.pipeline import COLLECTORS, run_collector


async def _run(source_id: str, max_pages: int | None, notify: bool) -> int:
    if source_id not in COLLECTORS:
        print(f"unknown source {source_id!r}; known: {', '.join(COLLECTORS)}", file=sys.stderr)
        return 2
    collector = COLLECTORS[source_id](max_pages=max_pages)
    try:
        summary = await run_collector(collector, get_session_factory())
    finally:
        await collector.aclose()
    print(
        f"{source_id}: seen={summary.seen} new={summary.new} "
        f"merged_into_existing={summary.source_added} gone={summary.gone}"
    )
    if notify:
        sender = TelegramSender.from_env() or ConsoleSender()
        with get_session_factory()() as s:
            n = await dispatch_new(s, sender, load_profile())
        print(
            f"alerts sent: {n}"
            + (" (console dry-run; no Telegram credentials)" if isinstance(sender, ConsoleSender) else "")
        )
    if summary.error:
        print(f"ERROR {summary.error}", file=sys.stderr)
        return 1
    return 0


async def _bot() -> int:
    tg = TelegramSender.from_env()
    if tg is None:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in .env", file=sys.stderr)
        return 2
    sessions = get_session_factory()
    while True:
        with sessions() as s:
            await handle_callbacks(s, tg)


def _reevaluate() -> None:
    from sqlalchemy import select

    from flathunter.core.evaluate import evaluate
    from flathunter.core.models import Listing

    profile = load_profile()
    with get_session_factory()() as s:
        rows = s.scalars(select(Listing)).all()
        for li in rows:
            evaluate(li, profile)
        s.commit()
        print(f"re-evaluated {len(rows)} listings")


def main() -> None:
    ap = argparse.ArgumentParser(prog="flathunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-once")
    r.add_argument("source_id")
    r.add_argument("--max-pages", type=int, default=None)
    r.add_argument("--notify", action="store_true", help="send alerts (Telegram, or console if no token)")
    sub.add_parser("reevaluate", help="re-run eligibility + scoring on all stored listings")
    sub.add_parser("watch", help="run all enabled sources on schedule, forever")
    sub.add_parser("bot", help="poll Telegram button callbacks")
    args = ap.parse_args()
    load_dotenv()
    if args.cmd == "reevaluate":
        _reevaluate()
        return
    if args.cmd == "watch":
        import logging

        from flathunter.ops.scheduler import run_watcher

        Path("logs").mkdir(exist_ok=True)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        # httpx logs full URLs and Telegram's contain the bot token: never let that reach a log.
        for noisy in ("httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
        tg = TelegramSender.from_env()
        asyncio.run(run_watcher(get_session_factory(), tg or ConsoleSender(), tg))
        return
    if args.cmd == "bot":
        sys.exit(asyncio.run(_bot()))
    sys.exit(asyncio.run(_run(args.source_id, args.max_pages, args.notify)))


if __name__ == "__main__":
    main()
