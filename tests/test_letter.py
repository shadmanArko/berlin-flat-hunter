from datetime import date

from flathunter.apply.letter import render_checklist, render_letter
from flathunter.core.models import Listing
from flathunter.core.profile import Profile

P = Profile(
    household_size=3,
    wbs_level=100,
    special_need=True,
    berechtigungsgruppe="J",
    max_rooms=3,
    valid_until=date(2027, 11, 30),
    contact_name="Erika Mustermann",
    contact_phone="+49 30 1",
    contact_email="e@example.com",
)


def li(**kw: object) -> Listing:
    base: dict[str, object] = dict(
        title="3-Zimmer-Wohnung",
        street="Beispielstraße",
        house_no="1",
        district="Lichtenberg",
        rooms=3.0,
        size_m2=70.0,
        wbs_required=True,
        available_from=date(2027, 1, 1),
        available_now=False,
        eligibility_class="P0_special_need",
    )
    base.update(kw)
    return Listing(**base)


def test_letter_contains_required_facts_and_no_income() -> None:
    t = render_letter(li(), P)
    for must in [
        "3-Zimmer-Wohnung (70 m²)",
        "zu 3 Räumen",
        "Beispielstraße 1",
        "Lichtenberg",
        "3 Personen",
        "WBS 100",
        "besonderem Wohnbedarf",
        "Berechtigungsgruppe J",
        "30. November 2027",
        "3 Räume",
        "1. Januar 2027",
        "Überlassungsmitteilung",
        "Erika Mustermann",
        "e@example.com",
    ]:
        assert must in t, must
    assert "Einkommen" not in t and "€" not in t


def test_free_market_flat_omits_wbs_paragraph_and_missing_contact_is_skipped() -> None:
    t = render_letter(li(wbs_required=False), Profile(contact_name="A B"))
    assert "Wohnberechtigungsschein (WBS" not in t and t.rstrip().endswith("A B")


def test_move_in_window_overrides_earlier_availability() -> None:
    t = render_letter(
        li(available_from=date(2026, 11, 1)), Profile(move_in_earliest=date(2027, 2, 1), contact_name="A")
    )
    assert "ab dem 1. Februar 2027" in t


def test_checklist_flags() -> None:
    c = render_checklist(li(rent_check="rent_borderline"), Profile())
    assert "Überlassungsmitteilung" in c and "Jobcenter" in c and "profile.yaml" in c


async def test_letter_button_replies_with_letter_and_checklist(sessions) -> None:  # type: ignore[no-untyped-def]
    from flathunter.core.schema import RawListing
    from flathunter.core.store import ensure_source, upsert
    from flathunter.notify.dispatch import handle_callbacks

    class FakeTg:
        chat_id, p0_chat_id = "5", None
        all_chat_ids = {"5"}

        def __init__(self) -> None:
            self.replies: list[str] = []
            self.toasts: list[str] = []

        async def get_updates(self, offset: int, timeout: int = 25) -> list[dict]:  # type: ignore[type-arg]
            return [
                {
                    "update_id": 1,
                    "callback_query": {"id": "c", "data": f"act:{lid}:letter", "message": {"chat": {"id": 5}}},
                }
            ]

        async def answer_callback(self, cb_id: str, text: str) -> None:
            self.toasts.append(text)

        async def reply(self, chat_id: str, text: str) -> None:
            self.replies.append(text)

    with sessions() as s:
        ensure_source(s, "a", "A", 1)
        r = upsert(
            s,
            RawListing(
                source_id="a",
                external_id="1",
                url="u",
                title="2 Zimmer",
                street="Teststr.",
                house_no="2",
                rooms=2.0,
                size_m2=55.0,
                wbs_text="erforderlich",
                description="WBS 100",
            ),
        )
        s.commit()
        lid = r.listing.id
        tg = FakeTg()
        await handle_callbacks(s, tg, P)  # type: ignore[arg-type]
    assert (
        len(tg.replies) == 2
        and "<pre>" in tg.replies[0]
        and "Teststr. 2" in tg.replies[0]
        and "Unterlagen" in tg.replies[1]
    )
