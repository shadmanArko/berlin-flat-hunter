"""Scoring (docs/SCORING.md). Orders listings within an eligibility class."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from flathunter.core.profile import Profile

ROOT = Path(__file__).resolve().parents[3]
CLASS_ORDER = {"P0_special_need": 0, "P1_wbs": 1, "P2_free_market": 2, "needs_review": 3, "ineligible": 4}


@lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())  # type: ignore[no-any-return]


def score(f: dict[str, Any], headroom: float | None, profile: Profile) -> tuple[float, list[str]]:
    c = _cfg()
    w = c["weights"]
    parts: dict[str, tuple[float, str]] = {}
    rooms = f.get("rooms")
    rp = c["rooms_points"]
    pts = rp.get(rooms, rp.get(int(rooms), 0)) if rooms else 0
    parts["rooms"] = (pts, f"{rooms:g} Zimmer" if rooms else "Zimmer unbekannt")
    size = f.get("size_m2") or 0
    parts["size"] = (min(size / c["size_cap_m2"], 1) * 100, f"{size:g} m²")
    if headroom is not None:
        parts["headroom"] = (max(0, min(headroom / c["headroom_cap_eur"], 1)) * 100, f"{headroom:+.0f} € zum Limit")
    else:
        parts["headroom"] = (30, "Miete unvollständig")
    feats = " ".join(f.get("features") or []).lower() + " " + (f.get("text") or "").lower()
    fw = c["facilities"]
    got = {
        "elevator": "aufzug" in feats or "fahrstuhl" in feats,
        "balcony": "balkon" in feats or "loggia" in feats or "terrasse" in feats,
        "fitted_kitchen": "einbauküche" in feats or "einbaukueche" in feats,
        "bath_window": "bad mit fenster" in feats or "tageslichtbad" in feats,
        "modern_heating": "fernwärme" in feats or "fernwaerme" in feats or "fußbodenheizung" in feats,
    }
    total = sum(fw.values())
    have = [k for k, v in got.items() if v]
    parts["facilities"] = (sum(fw[k] for k in have) / total * 100, ", ".join(have) or "keine Extras erkannt")
    district = (f.get("district") or "").lower()
    pref = [d.lower() for d in profile.districts_preferred]
    parts["location"] = (100 if district and district in pref else 50 if not pref else 0, f.get("district") or "")
    parts["availability"] = (100, "frei")
    total_w = sum(w.values())
    s = sum(parts[k][0] * w[k] for k in w) / total_w
    top = sorted(w, key=lambda k: parts[k][0] * w[k], reverse=True)[:3]
    return round(s, 1), [parts[k][1] for k in top if parts[k][1]]
