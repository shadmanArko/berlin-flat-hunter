import random
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from flathunter.collectors.base import Collector
from flathunter.core.profile import Profile
from flathunter.core.schema import FetchError, RawListing
from flathunter.ops.scheduler import BERLIN, FailureTracker, Schedule, interval_seconds, source_loop

SCHED = Schedule.load()


def test_interval_day_vs_night_with_jitter() -> None:
    noon = datetime(2026, 11, 10, 12, 0, tzinfo=BERLIN)
    night = datetime(2026, 11, 10, 2, 0, tzinfo=BERLIN)
    rng = random.Random(1)
    for _ in range(50):
        assert 240 <= interval_seconds(5, SCHED, noon, rng) <= 360  # 5 min ±20 %
        assert 720 <= interval_seconds(5, SCHED, night, rng) <= 1080  # 15 min ±20 %


def test_failure_tracker_alerts_once_then_recovers() -> None:
    t = FailureTracker(3)
    assert [t.record("x"), t.record("x"), t.record("x"), t.record("x")] == [None, None, "failing", None]
    assert t.record(None) == "recovered" and t.record(None) is None


class Recorder:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str, buttons: object, *, loud: bool, silent: bool) -> str:
        self.sent.append(text)
        return f"r:{len(self.sent)}"

    async def edit(self, message_id: str, text: str, buttons: object, *, loud: bool) -> None:
        pass


class Good(Collector):
    source_id = "good"
    name = "good"

    async def fetch(self, known_ids: Any = ()) -> list[RawListing]:
        return [
            RawListing(
                source_id="good",
                external_id="1",
                url="https://x.test/1",
                title="2 Zimmer",
                street="Teststr.",
                house_no="1",
                rooms=2.0,
                size_m2=55.0,
                rent_cold=400.0,
                operating_costs=100.0,
                floor=1,
                wbs_text="erforderlich",
                description="WBS 100 mit besonderem Wohnbedarf",
            )
        ]


class Bad(Collector):
    source_id = "bad"
    name = "bad"

    async def fetch(self, known_ids: Any = ()) -> list[RawListing]:
        raise FetchError("boom")


async def test_loop_stores_alerts_and_survives_failures(sessions: sessionmaker[Session], tmp_path: Any) -> None:
    rec, health = Recorder(), {}
    sched = Schedule.load()
    await source_loop("good", {}, sessions, Profile(), rec, sched, health, 0, collector_cls=Good, once=True)
    assert health["good"]["ok"] and len(rec.sent) == 1 and "P0" in rec.sent[0]
    await source_loop("good", {}, sessions, Profile(), rec, sched, health, 0, collector_cls=Good, once=True)
    assert len(rec.sent) == 1  # no duplicate alert
    tracker = FailureTracker(3)
    for _ in range(3):
        await source_loop(
            "bad", {}, sessions, Profile(), rec, sched, health, 0, collector_cls=Bad, once=True, tracker=tracker
        )
    assert not health["bad"]["ok"]
    assert any("fehlgeschlagen" in m and "bad" in m for m in rec.sent)
