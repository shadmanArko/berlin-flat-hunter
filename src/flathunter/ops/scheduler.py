"""Local watcher: one asyncio loop per source, staggered, jittered, never dies.
Runs free on the owner's machine; no LLM involved in polling."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy.orm import Session, sessionmaker

from flathunter.collectors.base import Collector
from flathunter.core.profile import Profile, load_profile
from flathunter.notify.dispatch import dispatch_new, handle_callbacks
from flathunter.notify.telegram import Sender, TelegramSender
from flathunter.ops.pipeline import COLLECTORS, run_collector

ROOT = Path(__file__).resolve().parents[3]
BERLIN = ZoneInfo("Europe/Berlin")
log = logging.getLogger("flathunter")


@dataclass
class Schedule:
    day_start: time
    night_start: time
    jitter: float
    night_interval_minutes: float
    run_timeout_seconds: float
    failure_alert_after: int

    @classmethod
    def load(cls, path: Path | None = None) -> Schedule:
        raw = yaml.safe_load((path or ROOT / "config" / "schedule.yaml").read_text())
        return cls(
            day_start=time.fromisoformat(raw["day_start"]),
            night_start=time.fromisoformat(raw["night_start"]),
            jitter=float(raw["jitter"]),
            night_interval_minutes=float(raw["night_interval_minutes"]),
            run_timeout_seconds=float(raw["run_timeout_seconds"]),
            failure_alert_after=int(raw["failure_alert_after"]),
        )


def interval_seconds(
    day_minutes: float, sched: Schedule, now: datetime | None = None, rng: random.Random | None = None
) -> float:
    now = (now or datetime.now(BERLIN)).astimezone(BERLIN)
    is_day = sched.day_start <= now.time() < sched.night_start
    base = (day_minutes if is_day else max(day_minutes, sched.night_interval_minutes)) * 60
    r = (rng or random).uniform(1 - sched.jitter, 1 + sched.jitter)
    return base * r


def load_sources() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())
    return {s["id"]: s for s in raw["sources"] if s.get("enabled", True) and s["id"] in COLLECTORS}


class FailureTracker:
    """Warn once after N consecutive failures; announce recovery once."""

    def __init__(self, threshold: int) -> None:
        self.threshold, self.count, self.alerted = threshold, 0, False

    def record(self, error: str | None) -> str | None:
        if error is None:
            was = self.alerted
            self.count, self.alerted = 0, False
            return "recovered" if was else None
        self.count += 1
        if self.count >= self.threshold and not self.alerted:
            self.alerted = True
            return "failing"
        return None


async def _notice(sender: Sender, text: str) -> None:
    try:
        await sender.send(text, [], loud=False, silent=False)
    except Exception:  # a failed warning must never kill the loop
        log.exception("could not send notice")


def _write_health(state: dict[str, Any]) -> None:
    p = ROOT / "logs"
    p.mkdir(exist_ok=True)
    (p / "health.json").write_text(json.dumps(state, indent=2, default=str))


async def source_loop(
    source_id: str,
    cfg: dict[str, Any],
    sessions: sessionmaker[Session],
    profile: Profile,
    sender: Sender,
    sched: Schedule,
    health: dict[str, Any],
    stagger_s: float,
    collector_cls: type[Collector] | None = None,
    once: bool = False,
    tracker: FailureTracker | None = None,
) -> None:
    cls = collector_cls or COLLECTORS[source_id]
    tracker = tracker or FailureTracker(sched.failure_alert_after)
    await asyncio.sleep(stagger_s)
    while True:
        error: str | None = None
        collector = cls(max_pages=cfg.get("max_pages"))
        try:
            summary = await asyncio.wait_for(run_collector(collector, sessions, profile), sched.run_timeout_seconds)
            error = summary.error
            if error is None:
                with sessions() as s:
                    sent = await dispatch_new(s, sender, profile)
                log.info(json.dumps({"source": source_id, "seen": summary.seen, "new": summary.new, "alerts": sent}))
        except TimeoutError:
            error = f"timeout after {sched.run_timeout_seconds:.0f}s"
        except Exception as e:  # keep the loop alive whatever happens
            error = f"{type(e).__name__}: {e}"
            log.exception("run failed")
        finally:
            await collector.aclose()
        if error:
            log.warning(json.dumps({"source": source_id, "error": error}))
        verdict = tracker.record(error)
        if verdict == "failing":
            await _notice(
                sender, f"⚠️ Quelle <b>{source_id}</b> ist {tracker.count}× hintereinander fehlgeschlagen:\n{error}"
            )
        elif verdict == "recovered":
            await _notice(sender, f"✅ Quelle <b>{source_id}</b> läuft wieder.")
        health[source_id] = {
            "last_run": datetime.now(BERLIN).isoformat(timespec="seconds"),
            "ok": error is None,
            "consecutive_failures": tracker.count,
            "error": error,
        }
        _write_health(health)
        if once:
            return
        await asyncio.sleep(interval_seconds(float(cfg.get("interval_minutes", 5)), sched))


def due_digests(
    digests: list[dict[str, str]], now: datetime, sent: set[str], catchup_hours: float
) -> list[tuple[str, str]]:
    """Slots (key, kind) that passed today, within the catch-up window, and were not sent yet."""
    now = now.astimezone(BERLIN)
    out = []
    for d in digests:
        slot = datetime.combine(now.date(), time.fromisoformat(d["time"]), tzinfo=BERLIN)
        key = f"{now.date()}-{d['time']}"
        if slot <= now <= slot + timedelta(hours=catchup_hours) and key not in sent:
            out.append((key, d["kind"]))
    return out


async def digest_loop(sessions: sessionmaker[Session], sender: Sender, profile: Profile) -> None:
    from flathunter.notify.digest import _get, _set, send_digest

    raw = yaml.safe_load((ROOT / "config" / "schedule.yaml").read_text())
    while True:
        try:
            with sessions() as s:
                sent = set((_get(s, "digests_sent") or "").split(","))
                for key, kind in due_digests(raw["digests"], datetime.now(BERLIN), sent, raw["digest_catchup_hours"]):
                    await send_digest(s, sender, profile, kind, raw["digest_max_per_section"])
                    sent = {x for x in sent if x[:10] == key[:10]} | {key}
                    _set(s, "digests_sent", ",".join(sorted(sent)))
                    s.commit()
        except Exception:
            log.exception("digest failed")
        await asyncio.sleep(60)


async def bot_loop(sessions: sessionmaker[Session], tg: TelegramSender) -> None:
    backoff = 1.0
    while True:
        try:
            with sessions() as s:
                await handle_callbacks(s, tg)
            backoff = 1.0
        except Exception:
            log.exception("callback polling failed")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def run_watcher(sessions: sessionmaker[Session], sender: Sender, tg: TelegramSender | None) -> None:
    sched, sources, profile = Schedule.load(), load_sources(), load_profile()
    health: dict[str, Any] = {}
    tasks = [
        asyncio.create_task(source_loop(sid, cfg, sessions, profile, sender, sched, health, stagger_s=i * 20.0))
        for i, (sid, cfg) in enumerate(sources.items())
    ]
    tasks.append(asyncio.create_task(digest_loop(sessions, sender, profile)))
    if tg is not None:
        tasks.append(asyncio.create_task(bot_loop(sessions, tg)))
    log.info("watcher started: %s", ", ".join(sources))
    await asyncio.gather(*tasks)
