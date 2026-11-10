from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from flathunter.core.evaluate import evaluate
from flathunter.core.models import UserAction
from flathunter.core.profile import Profile
from flathunter.core.schema import RawListing
from flathunter.core.store import ensure_source, upsert
from flathunter.notify.digest import build_digest, send_digest
from flathunter.ops.scheduler import BERLIN, due_digests

P = Profile()
DIGESTS = [{"time": "07:00", "kind": "morning"}, {"time": "12:30", "kind": "summary"}]


def flat(ext: str, **kw: object) -> RawListing:
    base: dict[str, object] = dict(
        source_id="a",
        external_id=ext,
        url=f"https://x.test/{ext}",
        title="Wohnung",
        street=f"Str{ext}",
        house_no="1",
        district="Lichtenberg",
        rooms=3.0,
        size_m2=65.0,
        rent_cold=450.0,
        operating_costs=120.0,
        floor=1,
        wbs_text="erforderlich",
        description="WBS 140 mit besonderem Wohnbedarf",
    )
    base.update(kw)
    return RawListing(**base)  # type: ignore[arg-type]


class Rec:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    async def send(self, text: str, buttons: object, *, loud: bool, silent: bool) -> str:
        self.sent.append((text, silent))
        return "m:1"


def test_due_digests_window_and_dedup() -> None:
    at = lambda h, m: datetime(2026, 11, 10, h, m, tzinfo=BERLIN)  # noqa: E731
    assert due_digests(DIGESTS, at(6, 59), set(), 3) == []
    assert due_digests(DIGESTS, at(7, 0), set(), 3) == [("2026-11-10-07:00", "morning")]
    assert due_digests(DIGESTS, at(9, 59), set(), 3) == [("2026-11-10-07:00", "morning")]  # woke up late: catch-up
    assert due_digests(DIGESTS, at(10, 1), set(), 3) == []  # too late, skipped
    assert due_digests(DIGESTS, at(7, 5), {"2026-11-10-07:00"}, 3) == []


async def test_morning_digest_sections_health_and_summary_silence(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        ensure_source(s, "a", "A", 1)
        for ext, kw in [
            ("1", {}),
            ("2", dict(wbs_text="erforderlich", description="WBS 140")),
            ("3", dict(rooms=1.0, size_m2=30.0)),
            ("4", dict(rent_cold=900.0)),
        ]:
            evaluate(upsert(s, flat(ext, **kw)).listing, P)
        s.commit()
        morning = build_digest(s, P, "morning", now=datetime.now(UTC))
        assert morning is not None
        for must in [
            "Guten Morgen",
            "P0",
            "P1",
            "zu klein",
            "Bewerbungen diese Woche: 0",
            "System",
            "Miete über AV-Wohnen-Limit",
        ]:
            assert must in morning, must
        rec = Rec()
        assert await send_digest(s, rec, P, "morning") is True and rec.sent[0][1] is False  # morning is not silent
        assert await send_digest(s, rec, P, "summary") is False  # nothing new → no message
        s.add(UserAction(listing_id=1, action="applied"))
        s.commit()
        assert "Bewerbungen diese Woche: 1" in (build_digest(s, P, "morning") or "")
