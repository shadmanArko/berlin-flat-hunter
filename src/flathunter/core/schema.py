"""Pydantic models passed between pipeline stages."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class RawListing(BaseModel):
    """What a collector extracts, already typed but not yet deduplicated or classified."""

    source_id: str
    external_id: str
    url: str
    title: str = ""
    street: str | None = None
    house_no: str | None = None
    postcode: str | None = None
    district: str | None = None
    ortsteil: str | None = None
    lat: float | None = None
    lon: float | None = None
    rooms: float | None = None
    size_m2: float | None = None
    rent_cold: float | None = None
    operating_costs: float | None = None  # Betriebskosten excl. heating
    heating_costs: float | None = None
    rent_warm: float | None = None
    energy_carrier: str | None = None
    floor: int | None = None
    floors_total: int | None = None
    construction_year: int | None = None
    available_from: date | None = None
    available_now: bool = False
    published_at: datetime | None = None
    landlord: str | None = None
    wbs_text: str | None = None  # structured WBS field as shown by the source
    features: list[str] = Field(default_factory=list)
    description: str = ""
    raw_text: str = ""
    #: True when only list-page data was available (no detail page): skip WBS re-parse.
    partial: bool = False


class WbsInfo(BaseModel):
    wbs_required: bool | None = None
    wbs_levels: list[int] = Field(default_factory=list)
    special_need_required: bool | None = None
    required_rooms: int | None = None
    matched: list[str] = Field(default_factory=list)


class CollectorError(Exception):
    """Base for typed collector failures."""


class LayoutChangedError(CollectorError):
    """Page structure no longer matches what the parser expects."""


class FetchError(CollectorError):
    """Network / HTTP failure."""
