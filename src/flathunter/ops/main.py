"""CLI: `python -m flathunter.ops.main run-once <source_id> [--max-pages N]`."""
from __future__ import annotations

import argparse
import asyncio
import sys

from flathunter.core.db import get_session_factory
from flathunter.ops.pipeline import COLLECTORS, run_collector


async def _run(source_id: str, max_pages: int | None) -> int:
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
    if summary.error:
        print(f"ERROR {summary.error}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="flathunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-once")
    r.add_argument("source_id")
    r.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args()
    sys.exit(asyncio.run(_run(args.source_id, args.max_pages)))


if __name__ == "__main__":
    main()
