"""SQLAlchemy 2 schema (SPEC §6). M1 subset: sources, runs, listings, listing_sources, events."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(40), unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    missed_runs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | gone
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(Text, default="")
    landlord: Mapped[str | None] = mapped_column(String(100))
    street: Mapped[str | None] = mapped_column(String(200))
    house_no: Mapped[str | None] = mapped_column(String(20))
    postcode: Mapped[str | None] = mapped_column(String(10))
    district: Mapped[str | None] = mapped_column(String(100))
    ortsteil: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float)
    size_m2: Mapped[float | None] = mapped_column(Float)
    rent_cold: Mapped[float | None] = mapped_column(Float)
    operating_costs: Mapped[float | None] = mapped_column(Float)
    heating_costs: Mapped[float | None] = mapped_column(Float)
    rent_gross_cold: Mapped[float | None] = mapped_column(Float)
    rent_warm: Mapped[float | None] = mapped_column(Float)
    energy_carrier: Mapped[str | None] = mapped_column(String(100))
    building_floor_area: Mapped[float | None] = mapped_column(Float)
    rent_check: Mapped[str | None] = mapped_column(String(20))
    rent_limit_used: Mapped[float | None] = mapped_column(Float)
    construction_year: Mapped[int | None] = mapped_column(Integer)
    available_from: Mapped[date | None] = mapped_column(Date)
    available_now: Mapped[bool] = mapped_column(Boolean, default=False)
    floor: Mapped[int | None] = mapped_column(Integer)
    floors_total: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    wbs_required: Mapped[bool | None] = mapped_column(Boolean)
    wbs_levels: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    special_need_required: Mapped[bool | None] = mapped_column(Boolean)
    wbs_required_rooms: Mapped[int | None] = mapped_column(Integer)
    wbs_matched: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    eligibility_class: Mapped[str | None] = mapped_column(String(24))
    eligibility_reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    raw_text: Mapped[str] = mapped_column(Text, default="")

    sources: Mapped[list[ListingSource]] = relationship(back_populates="listing")


class ListingSource(Base):
    __tablename__ = "listing_sources"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    listing: Mapped[Listing] = relationship(back_populates="sources")


class ListingEvent(Base):
    __tablename__ = "listing_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(24))  # created | price_change | relisted | gone | source_added
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(24))  # instant | digest | needs_review | source_added
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    message_id: Mapped[str | None] = mapped_column(String(255))


class UserAction(Base):
    __tablename__ = "user_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    action: Mapped[str] = mapped_column(String(24))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)


class KeyValue(Base):
    """Small runtime state, e.g. Telegram getUpdates offset."""

    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
