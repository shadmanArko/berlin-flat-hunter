"""Household profile (private, config/profile.yaml). Loaded at runtime; never logged."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]


class Profile(BaseModel):
    household_size: int = 3
    wbs_level: int = 100
    special_need: bool = True
    berechtigungsgruppe: str = "J"
    max_rooms: float = 3
    valid_until: date | None = None
    rent_limit_override: float | None = None
    include_free_market: str = "digest_only"  # instant | digest_only | off
    districts_preferred: list[str] = Field(default_factory=list)
    districts_excluded: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    alert_min_rooms: float = 2
    alert_min_size_m2: float = 45
    move_in_earliest: date | None = None
    move_in_latest: date | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    documents_folder: str | None = None


def _s(v: object) -> str | None:
    t = str(v).strip() if v is not None else ""
    return None if not t or t.upper() == "TODO" else t


def _d(v: object) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None  # e.g. "TODO"


def load_profile(path: Path | None = None) -> Profile:
    p = path or ROOT / "config" / "profile.yaml"
    if not p.exists():
        p = ROOT / "config" / "profile.example.yaml"
    raw = yaml.safe_load(p.read_text()) or {}
    wbs, search = raw.get("wbs", {}), raw.get("search", {})
    fm = search.get("include_free_market", "digest_only")
    return Profile(
        household_size=raw.get("household", {}).get("size", 3),
        wbs_level=wbs.get("level", 100),
        special_need=bool(wbs.get("special_need", False)),
        berechtigungsgruppe=str(wbs.get("berechtigungsgruppe", "")),
        max_rooms=wbs.get("max_rooms", 3),
        valid_until=_d(wbs.get("valid_until")),
        rent_limit_override=raw.get("rent_limit_override"),
        include_free_market=fm if fm in ("instant", "digest_only", "off") else "digest_only",
        districts_preferred=search.get("districts_preferred") or [],
        districts_excluded=search.get("districts_excluded") or [],
        must_have=search.get("must_have") or [],
        alert_min_rooms=search.get("alert_min_rooms", 2),
        alert_min_size_m2=search.get("alert_min_size_m2", 45),
        contact_name=_s(raw.get("household", {}).get("contact", {}).get("name")),
        contact_email=_s(raw.get("household", {}).get("contact", {}).get("email")),
        contact_phone=_s(raw.get("household", {}).get("contact", {}).get("phone")),
        documents_folder=_s(raw.get("documents_folder")),
        move_in_earliest=_d(search.get("move_in_earliest")),
        move_in_latest=_d(search.get("move_in_latest")),
    )
