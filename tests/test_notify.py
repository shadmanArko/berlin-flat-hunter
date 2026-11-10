from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flathunter.core.evaluate import evaluate
from flathunter.core.models import Notification
from flathunter.core.profile import Profile
from flathunter.core.schema import RawListing
from flathunter.core.store import ensure_source, upsert
from flathunter.notify.dispatch import dispatch_new
from flathunter.notify.render import render_alert

P = Profile()


class ConsoleSender:
    """Recording fake (not the real ConsoleSender, which deliberately persists nothing)."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str, buttons: object, *, loud: bool, silent: bool) -> str:
        self.sent.append(text)
        return f"fake:{len(self.sent)}"

    async def edit(self, message_id: str, text: str, buttons: object, *, loud: bool) -> None:
        pass


def flat(source: str, ext: str, **kw: object) -> RawListing:
    base: dict[str, object] = dict(
        source_id=source,
        external_id=ext,
        url=f"https://example.test/{source}/{ext}",
        title="2-Zimmer",
        street="Beispielstraße",
        house_no="12",
        postcode="10115",
        district="Lichtenberg",
        rooms=2.0,
        size_m2=54.0,
        rent_cold=450.0,
        operating_costs=120.0,
        heating_costs=90.0,
        rent_warm=660.0,
        floor=3,
        wbs_text="erforderlich",
        description="WBS 100/140 mit besonderem Wohnbedarf",
        features=["Aufzug"],
    )
    base.update(kw)
    return RawListing(**base)  # type: ignore[arg-type]


async def test_alert_once_then_edit_on_second_source(sessions: sessionmaker[Session]) -> None:
    sender = ConsoleSender()
    with sessions() as s:
        ensure_source(s, "a", "A", 1)
        ensure_source(s, "b", "B", 1)
        r = upsert(s, flat("a", "1"))
        evaluate(r.listing, P)
        s.commit()
        assert await dispatch_new(s, sender, P) == 1
        assert await dispatch_new(s, sender, P) == 0  # never twice
        r2 = upsert(s, flat("b", "9"))
        evaluate(r2.listing, P)
        s.commit()
        assert await dispatch_new(s, sender, P) == 0  # same flat: edit, not a new alert
        kinds = [n.kind for n in s.scalars(select(Notification).order_by(Notification.id))]
        assert kinds == ["instant", "source_added"]
    text = sender.sent[0]
    assert "P0" in text and "Bruttokalt 570,00 €" in text and "Limit 736,00 €" in text and "example.test/a/1" in text


async def test_ineligible_and_free_market_not_alerted(sessions: sessionmaker[Session]) -> None:
    sender = ConsoleSender()
    with sessions() as s:
        ensure_source(s, "a", "A", 1)
        for i, kw in enumerate(
            [
                dict(rent_cold=900.0),  # over limit
                dict(wbs_text="nicht erforderlich", description="ohne WBS", street="Andere Str."),  # free market
            ]
        ):
            evaluate(upsert(s, flat("a", str(i), **kw)).listing, P)
        s.commit()
        assert await dispatch_new(s, sender, P) == 0
        assert await dispatch_new(s, sender, Profile(include_free_market="instant")) == 1


def test_render_has_buttons_and_escapes(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        ensure_source(s, "a", "A", 1)
        r = upsert(s, flat("a", "1", street="A<b>&Co"))
        evaluate(r.listing, P)
        text, buttons = render_alert(r.listing, P)
        assert "<b>&Co" not in text and "&lt;b&gt;" in text
        assert [b["callback_data"].split(":")[2] for b in buttons[0]] == ["applied", "not_interested", "letter"]
