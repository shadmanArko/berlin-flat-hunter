"""Fingerprinting and fuzzy matching so one flat is one listing across sources."""

from __future__ import annotations

import hashlib

from flathunter.core.normalize import norm_house_no, norm_street
from flathunter.core.schema import RawListing


def fingerprint(r: RawListing) -> str | None:
    """street + house no + rooms + round(m²) + floor. Postcode is excluded on purpose:
    sources differ on whether they give it. Floor is included because social housing has
    many identical stacked flats. Returns None if the address is unusable."""
    street, no = norm_street(r.street), norm_house_no(r.house_no)
    if not street or not no or r.rooms is None or r.size_m2 is None:
        return None
    key = f"{street}|{no}|{r.rooms:g}|{round(r.size_m2)}|{'' if r.floor is None else r.floor}"
    return hashlib.sha1(key.encode()).hexdigest()[:20]


def fallback_key(r: RawListing) -> str:
    """Used when no address is available: source-scoped, never merged across sources."""
    return hashlib.sha1(f"{r.source_id}|{r.external_id}".encode()).hexdigest()[:20]


def is_fuzzy_match(a: RawListing, b: RawListing) -> bool:
    """Same building + rooms, size within 2 m², rent within 3 %, floor equal if both known."""
    if not (a.street and b.street and a.house_no and b.house_no):
        return False
    if norm_street(a.street) != norm_street(b.street):
        return False
    if norm_house_no(a.house_no) != norm_house_no(b.house_no):
        return False
    if a.rooms != b.rooms or a.size_m2 is None or b.size_m2 is None:
        return False
    if abs(a.size_m2 - b.size_m2) > 2:
        return False
    if a.floor is not None and b.floor is not None and a.floor != b.floor:
        return False
    if a.rent_cold and b.rent_cold and abs(a.rent_cold - b.rent_cold) / a.rent_cold > 0.03:
        return False
    return True
