from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flathunter.core.models import Listing, ListingEvent, ListingSource
from flathunter.core.schema import RawListing
from flathunter.core.store import ensure_source, mark_missing, upsert


def flat(source: str, ext: str, **kw: object) -> RawListing:
    base: dict[str, object] = dict(
        source_id=source,
        external_id=ext,
        url=f"https://example.test/{ext}",
        title="3-Zimmer",
        street="Beispielstraße",
        house_no="12",
        postcode="10115",
        rooms=3.0,
        size_m2=68.13,
        rent_cold=441.42,
        operating_costs=158.29,
        heating_costs=100.0,
        floor=1,
        wbs_text="erforderlich",
        description="nur mit WBS 140 mit besonderem Wohnbedarf",
    )
    base.update(kw)
    return RawListing(**base)  # type: ignore[arg-type]


def setup(s: Session) -> None:
    ensure_source(s, "a", "A", 1)
    ensure_source(s, "b", "B", 1)


def test_create_computes_gross_cold_and_wbs(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        r = upsert(s, flat("a", "1"))
        s.commit()
        li = r.listing
        assert r.is_new and li.rent_gross_cold == 599.71
        assert li.wbs_required and li.special_need_required and li.wbs_levels == [140]


def test_same_flat_from_two_sources_is_one_listing(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        first = upsert(s, flat("a", "1"))
        second = upsert(s, flat("b", "xyz", street="Beispielstr.", size_m2=68.4))
        s.commit()
        assert first.is_new and not second.is_new and second.source_added
        assert second.listing.id == first.listing.id
        assert len(s.scalars(select(ListingSource)).all()) == 2
        assert len(s.scalars(select(Listing)).all()) == 1


def test_identical_stacked_flats_on_different_floors_stay_separate(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        upsert(s, flat("a", "1", floor=1))
        r = upsert(s, flat("a", "2", floor=2))
        assert r.is_new


def test_partial_update_keeps_wbs_and_details(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        upsert(s, flat("a", "1"))
        r = upsert(
            s,
            flat(
                "a",
                "1",
                partial=True,
                wbs_text=None,
                description="",
                rent_cold=None,
                operating_costs=None,
                heating_costs=None,
            ),
        )
        assert r.listing.special_need_required is True and r.listing.rent_gross_cold == 599.71


def test_price_change_event(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        upsert(s, flat("a", "1"))
        upsert(s, flat("a", "1", rent_cold=460.0))
        s.commit()
        kinds = [e.kind for e in s.scalars(select(ListingEvent).order_by(ListingEvent.id))]
        assert kinds == ["created", "price_change"]


def test_gone_after_three_missed_runs_and_relist(sessions: sessionmaker[Session]) -> None:
    with sessions() as s:
        setup(s)
        t0 = datetime.now(UTC) - timedelta(hours=1)
        r = upsert(s, flat("a", "1"), now=t0)
        s.commit()
        run = datetime.now(UTC)
        for i in range(3):
            assert mark_missing(s, "a", run + timedelta(minutes=i)) == (1 if i == 2 else 0)
        assert r.listing.status == "gone"
        again = upsert(s, flat("a", "1"))
        assert again.relisted and again.listing.status == "active" and again.listing.missed_runs == 0
