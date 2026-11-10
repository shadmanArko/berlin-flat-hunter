"""One collector run: fetch → persist (dedup) → record run → gone-check."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flathunter.collectors.base import Collector
from flathunter.collectors.degewo import DegewoCollector
from flathunter.collectors.inberlinwohnen import InBerlinWohnenCollector
from flathunter.core.evaluate import evaluate
from flathunter.core.models import Listing, ListingSource
from flathunter.core.profile import Profile, load_profile
from flathunter.core.schema import CollectorError
from flathunter.core.store import UpsertResult, ensure_source, mark_missing, record_run, upsert

COLLECTORS: dict[str, type[Collector]] = {
    InBerlinWohnenCollector.source_id: InBerlinWohnenCollector,
    DegewoCollector.source_id: DegewoCollector,
}


@dataclass
class RunSummary:
    source_id: str
    seen: int = 0
    new: int = 0
    source_added: int = 0
    gone: int = 0
    error: str | None = None
    new_listings: list[Listing] = field(default_factory=list)


async def run_collector(
    collector: Collector, sessions: sessionmaker[Session], profile: Profile | None = None
) -> RunSummary:
    profile = profile or load_profile()
    sid = collector.source_id
    started = datetime.now(UTC)
    t0 = time.monotonic()
    summary = RunSummary(sid)
    with sessions() as s:
        ensure_source(s, sid, collector.name, collector.tier)
        known = set(s.scalars(select(ListingSource.external_id).where(ListingSource.source_id == sid)))
        s.commit()
    try:
        items = await collector.fetch(known)
    except CollectorError as e:
        summary.error = f"{type(e).__name__}: {e}"
        items = []
    with sessions() as s:
        results: list[UpsertResult] = [upsert(s, r) for r in items]
        for r in results:
            evaluate(r.listing, profile)
        summary.seen = len(items)
        summary.new = sum(r.is_new for r in results)
        summary.source_added = sum(r.source_added for r in results)
        summary.new_listings = [r.listing for r in results if r.is_new]
        if summary.error is None and collector.complete_crawl:
            summary.gone = mark_missing(s, sid, started)
        record_run(
            s,
            sid,
            duration_ms=int((time.monotonic() - t0) * 1000),
            seen=summary.seen,
            new=summary.new,
            error=summary.error,
            http_status=collector.http_status,
        )
        s.commit()
    return summary
