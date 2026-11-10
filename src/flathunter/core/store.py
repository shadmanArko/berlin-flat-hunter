"""Persist RawListings: dedup into `listings`, link sources, record events and runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from flathunter.core.dedup import fallback_key, fingerprint, is_fuzzy_match
from flathunter.core.models import Listing, ListingEvent, ListingSource, Run, Source
from flathunter.core.normalize import gross_cold
from flathunter.core.schema import RawListing, WbsInfo
from flathunter.core.wbs import parse_wbs


@dataclass
class UpsertResult:
    listing: Listing
    is_new: bool
    source_added: bool = False
    relisted: bool = False


def ensure_source(s: Session, source_id: str, name: str, tier: int) -> Source:
    src = s.get(Source, source_id)
    if src is None:
        src = Source(id=source_id, name=name, tier=tier)
        s.add(src)
        s.flush()
    return src


def _raw_as_listing_view(li: Listing) -> RawListing:
    return RawListing(
        source_id="",
        external_id="",
        url="",
        street=li.street,
        house_no=li.house_no,
        rooms=li.rooms,
        size_m2=li.size_m2,
        rent_cold=li.rent_cold,
        floor=li.floor,
    )


def _fill(li: Listing, r: RawListing) -> None:
    """Fill/refresh fields; never overwrite a known value with None."""
    wbs = parse_wbs(r.title, r.description, r.wbs_text, structured=r.wbs_text)
    if r.partial:
        wbs = WbsInfo()  # list-only data must not overwrite a detail-based WBS parse
    vals: dict[str, object] = {
        "title": r.title,
        "landlord": r.landlord,
        "street": r.street,
        "house_no": r.house_no,
        "postcode": r.postcode,
        "district": r.district,
        "ortsteil": r.ortsteil,
        "lat": r.lat,
        "lon": r.lon,
        "rooms": r.rooms,
        "size_m2": r.size_m2,
        "rent_cold": r.rent_cold,
        "operating_costs": r.operating_costs,
        "heating_costs": r.heating_costs,
        "rent_warm": r.rent_warm,
        "energy_carrier": r.energy_carrier,
        "construction_year": r.construction_year,
        "available_from": r.available_from,
        "floor": r.floor,
        "floors_total": r.floors_total,
        "published_at": r.published_at,
        "wbs_required": wbs.wbs_required,
        "special_need_required": wbs.special_need_required,
        "wbs_required_rooms": wbs.required_rooms,
    }
    for k, v in vals.items():
        if v is not None and v != "":
            setattr(li, k, v)
    if r.available_now:
        li.available_now = True
    if r.features:
        li.features = sorted(set(li.features or []) | set(r.features))
    if wbs.wbs_levels:
        li.wbs_levels = wbs.wbs_levels
    if wbs.matched:
        li.wbs_matched = wbs.matched
    if len(r.raw_text) > len(li.raw_text or ""):
        li.raw_text = r.raw_text
    li.rent_gross_cold = gross_cold(li.rent_cold, li.operating_costs)


def upsert(s: Session, r: RawListing, now: datetime | None = None) -> UpsertResult:
    now = now or datetime.now(UTC)
    # 1. same source+external id → same listing
    ls = s.scalar(
        select(ListingSource).where(ListingSource.source_id == r.source_id, ListingSource.external_id == r.external_id)
    )
    if ls is not None:
        cur = ls.listing
        ls.last_seen_at = now
        relisted = cur.status == "gone"
        if relisted:
            cur.status = "active"
            s.add(ListingEvent(listing_id=cur.id, kind="relisted", data={"source": r.source_id}))
        old_rent = cur.rent_cold
        _fill(cur, r)
        cur.last_seen_at, cur.missed_runs = now, 0
        if old_rent and cur.rent_cold and abs(old_rent - cur.rent_cold) > 0.005:
            s.add(
                ListingEvent(
                    listing_id=cur.id,
                    kind="price_change",
                    data={"old": old_rent, "new": cur.rent_cold},
                )
            )
        return UpsertResult(cur, False, relisted=relisted)

    # 2. cross-source: exact fingerprint, then fuzzy
    fp = fingerprint(r) or fallback_key(r)
    li: Listing | None = s.scalar(select(Listing).where(Listing.fingerprint == fp))
    if li is None and r.street and r.house_no:
        for cand in s.scalars(select(Listing).where(Listing.street.is_not(None), Listing.status == "active")):
            if is_fuzzy_match(_raw_as_listing_view(cand), r):
                li = cand
                break
    if li is not None:
        s.add(ListingSource(listing_id=li.id, source_id=r.source_id, external_id=r.external_id, url=r.url))
        s.add(ListingEvent(listing_id=li.id, kind="source_added", data={"source": r.source_id}))
        _fill(li, r)
        li.last_seen_at, li.missed_runs = now, 0
        s.flush()
        return UpsertResult(li, False, source_added=True)

    li = Listing(fingerprint=fp, first_seen_at=now, last_seen_at=now)
    _fill(li, r)
    s.add(li)
    s.flush()
    s.add(ListingSource(listing_id=li.id, source_id=r.source_id, external_id=r.external_id, url=r.url))
    s.add(ListingEvent(listing_id=li.id, kind="created", data={"source": r.source_id}))
    s.flush()
    return UpsertResult(li, True)


def record_run(
    s: Session,
    source_id: str,
    *,
    duration_ms: int,
    seen: int,
    new: int,
    error: str | None = None,
    http_status: int | None = None,
) -> None:
    s.add(
        Run(
            source_id=source_id,
            duration_ms=duration_ms,
            items_seen=seen,
            items_new=new,
            error=error,
            http_status=http_status,
        )
    )
    src = s.get(Source, source_id)
    if src is not None:
        if error:
            src.consecutive_failures += 1
        else:
            src.consecutive_failures = 0
            src.last_success_at = datetime.now(UTC)


GONE_AFTER_MISSES = 3


def mark_missing(s: Session, source_id: str, run_started: datetime) -> int:
    """After a COMPLETE crawl of a source: listings that only this source carries and that
    were not seen in the run count a miss; 3 consecutive misses → gone (SPEC §7)."""
    gone = 0
    ids = s.scalars(
        select(ListingSource.listing_id).where(
            ListingSource.source_id == source_id, ListingSource.last_seen_at < run_started
        )
    ).all()
    for lid in set(ids):
        li = s.get(Listing, lid)
        if li is None or li.status != "active" or li.last_seen_at >= run_started:
            continue
        li.missed_runs += 1
        if li.missed_runs >= GONE_AFTER_MISSES:
            li.status = "gone"
            s.add(ListingEvent(listing_id=li.id, kind="gone", data={"source": source_id}))
            gone += 1
    return gone
