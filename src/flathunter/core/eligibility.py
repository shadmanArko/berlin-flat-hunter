"""Deterministic eligibility (SPEC §2). Pure function of listing facts + profile + config."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from flathunter.core.profile import Profile

ROOT = Path(__file__).resolve().parents[3]

SENIOR = re.compile(r"senioren|ab\s*(?:55|60|65)\s*(?:jahren|\+)|\b(?:55|60|65)\s*(?:plus|\+)", re.I)
STUDENT = re.compile(r"nur\s+f(?:ü|ue)r\s+(?:studierende|azubi|auszubildende)|f(?:ü|ue)r\s+studierende", re.I)
SWAP = re.compile(r"nur\s+f(?:ü|ue)r\s+wohnungstausch|wohnungstausch\s+(?:erforderlich|only)|tauschwohnung", re.I)
WHEELCHAIR = re.compile(r"rollstuhl\w*[^.]{0,60}\bnur\b|nur\s+f(?:ü|ue)r\s+rollstuhl", re.I)
COOP = re.compile(r"genossenschaftsmitgli|mitgliedschaft\s+(?:in\s+der\s+genossenschaft\s+)?erforderlich", re.I)
WOHNKUECHE = re.compile(r"wohnk(?:ü|ue)che|k(?:ü|ue)che\s+als\s+zimmer", re.I)
NOT_A_FLAT = re.compile(
    r"stellplatz|stellplätze|stellplaetze|tiefgarage|garage|pkw-|gewerbe|lagerraum|kellerraum|büro", re.I
)
GROUP = re.compile(r"berechtigungsgruppe[n]?\s+((?:[A-Z]\b[\s,/und&]*)+)", re.I)


@lru_cache(maxsize=1)
def rent_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "rent_limits.yaml").read_text())  # type: ignore[no-any-return]


@dataclass
class RentResult:
    status: str  # rent_ok | rent_borderline | rent_over | rent_unknown
    limit: float | None
    gross_cold: float | None
    headroom: float | None
    heating: str = "unknown"


@dataclass
class Verdict:
    eligibility_class: str
    reason: str
    rent: RentResult
    notes: list[str] = field(default_factory=list)


def check_rent(
    rent_cold: float | None,
    operating: float | None,
    wbs_bound: bool,
    profile: Profile,
    cfg: dict[str, Any] | None = None,
) -> RentResult:
    cfg = cfg or rent_config()
    table = cfg["bruttokalt"].get(profile.household_size) or cfg["bruttokalt"][max(cfg["bruttokalt"])]
    limit = profile.rent_limit_override or table["social_housing" if wbs_bound else "general"]
    if rent_cold is None or operating is None:
        return RentResult("rent_unknown", limit, None, None)
    gross = round(rent_cold + operating, 2)
    headroom = round(limit - gross, 2)
    if gross <= limit:
        status = "rent_ok"
    elif gross <= limit * cfg["borderline_factor"]:
        status = "rent_borderline"
    else:
        status = "rent_over"
    return RentResult(status, limit, gross, headroom)


def classify(f: dict[str, Any], profile: Profile, cfg: dict[str, Any] | None = None) -> Verdict:
    """`f` keys: rooms, rent_cold, operating_costs, wbs_required, special_need_required,
    wbs_required_rooms, text (title+description+raw), district, wbs_matched."""
    text = f.get("text") or ""
    wbs = f.get("wbs_required")
    rent = check_rent(f.get("rent_cold"), f.get("operating_costs"), bool(wbs), profile, cfg)
    notes: list[str] = []

    def out(cls: str, reason: str) -> Verdict:
        return Verdict(cls, reason, rent, notes)

    no_size = f.get("rooms") is None and f.get("size_m2") is None
    if NOT_A_FLAT.search(f.get("title") or text[:120]) or (no_size and (f.get("rent_cold") or 0) < 300):
        return out("ineligible", "not_an_apartment")
    if SWAP.search(text):
        return out("ineligible", "only_for_wohnungstausch")
    if STUDENT.search(text):
        return out("ineligible", "students_or_trainees_only")
    if SENIOR.search(text):
        return out("ineligible", "senior_only")
    if WHEELCHAIR.search(text):
        return out("ineligible", "wheelchair_only")
    if f.get("district") and f["district"].lower() in [d.lower() for d in profile.districts_excluded]:
        return out("ineligible", "excluded_district")
    if COOP.search(text):
        notes.append("Genossenschaftsmitgliedschaft erforderlich")

    rooms = f.get("rooms")
    if wbs is None:
        # Unknown WBS status: even the more generous social-housing limit must hold, otherwise it is moot.
        lenient = check_rent(f.get("rent_cold"), f.get("operating_costs"), True, profile, cfg)
        if lenient.status == "rent_over":
            return Verdict("ineligible", "rent_over_av_wohnen", lenient, notes)
        return out("needs_review", "wbs_status_unclear")
    if wbs:
        if f.get("special_need_required") and not profile.special_need:
            return out("ineligible", "special_need_required_but_not_granted")
        req = f.get("wbs_required_rooms")
        if req is not None and req > profile.max_rooms:
            return out("ineligible", f"wbs_requires_{req}_rooms")
        m = GROUP.search(text)
        if m:
            groups = set(re.findall(r"\b[A-Z]\b", m.group(1).upper()))
            if groups and profile.berechtigungsgruppe.upper() not in groups:
                return out("ineligible", "berechtigungsgruppe_not_listed")
        if rooms is not None and rooms > profile.max_rooms + 0.5:
            return out("ineligible", "too_many_rooms_for_wbs")
        if rooms is not None and rooms > profile.max_rooms:
            notes.append("ask the landlord whether a WBS for 3 Räume is enough")
            return out("needs_review", "half_room_above_entitlement")
        if rooms is None:
            return out("needs_review", "rooms_unknown")
    if rent.status == "rent_over":
        return out("ineligible", "rent_over_av_wohnen")
    if WOHNKUECHE.search(text):
        notes.append("Wohnküche: check whether the kitchen counts as a room")
        if wbs and rooms is not None and rooms >= profile.max_rooms:  # could push the count over the entitlement
            return out("needs_review", "wohnkueche_room_count")

    if rent.status == "rent_borderline":
        notes.append("ask Jobcenter before applying")
        return out("needs_review", "rent_borderline")
    if rent.status == "rent_unknown":
        notes.append("rent components missing")
    if wbs:
        if f.get("special_need_required"):
            return out("P0_special_need", "wbs_with_special_need")
        return out("P1_wbs", "wbs")
    return out("P2_free_market", "no_wbs_required")
