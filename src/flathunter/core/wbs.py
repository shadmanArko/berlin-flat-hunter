"""WBS requirement parser. Patterns live in config/wbs_patterns.yaml."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from flathunter.core.schema import WbsInfo

CONFIG = Path(__file__).resolve().parents[3] / "config" / "wbs_patterns.yaml"


@lru_cache(maxsize=1)
def _patterns() -> dict[str, object]:
    return yaml.safe_load(CONFIG.read_text())  # type: ignore[no-any-return]


def _any(key: str, text: str) -> list[str]:
    pats = _patterns()[key]
    assert isinstance(pats, list)
    return [p for p in pats if re.search(p, text, re.I)]


_LEVEL_RE = re.compile(r"\b(100|140|160|180|220)\b")
_WBS_LEVEL_CTX = re.compile(
    r"(?:wbs|wohnberechtigungsschein)[^.;\n]{0,40}?((?:\b(?:100|140|160|180|220)\b[\s/,\-–bisoderund]*)+)",
    re.I,
)


def _levels(text: str) -> list[int]:
    found: set[int] = set()
    for m in _WBS_LEVEL_CTX.finditer(text):
        seg = m.group(1)
        nums = [int(x) for x in _LEVEL_RE.findall(seg)]
        found.update(nums)
        # ranges "WBS 160 bis 220" / "WBS 140-220" cover the levels in between
        if len(nums) >= 2 and re.search(r"bis|[-–]", seg):
            lo, hi = min(nums), max(nums)
            found.update(lv for lv in (100, 140, 160, 180, 220) if lo <= lv <= hi)
    for m in re.finditer(r"wbs\s*bis\s*(100|140|160|180|220)", text, re.I):
        hi = int(m.group(1))
        found.update(lv for lv in (100, 140, 160, 180, 220) if lv <= hi)
    return sorted(found)


def parse_wbs(*texts: str | None, structured: str | None = None) -> WbsInfo:
    """Combine title/description/structured field. `structured` is the source's own WBS field."""
    text = " \n".join(t for t in texts if t)
    info = WbsInfo()
    s = (structured or "").lower()

    text_no = _any("no_wbs", text)
    text_req = _any("wbs_required", text)
    s_no = bool(re.search(r"nicht\s+erforderlich|\bnein\b|entfällt|nicht\s+notwendig", s))
    s_req = bool(structured) and not s_no and bool(re.search(r"erforderlich|pflicht|\bja\b|mit wbs", s))
    levels_in_text = bool(_levels(text))

    if s_req and not text_no:
        info.wbs_required, info.matched = True, ["structured:required"] + text_req
    elif s_req and text_no:
        info.wbs_required, info.matched = None, ["conflict:structured_required_vs_text_no_wbs"]
    elif s_no and levels_in_text and not text_no:
        info.wbs_required, info.matched = None, ["conflict:structured_not_required_vs_text_level"]
    elif s_no or text_no:
        info.wbs_required = False
        info.matched = text_no + (["structured:not_required"] if s_no else [])
    elif text_req:
        info.wbs_required, info.matched = True, text_req
    else:
        info.wbs_required = None

    if info.wbs_required:
        info.wbs_levels = _levels(text)
        sn = _any("special_need", text)
        if sn:
            info.special_need_required = True
            info.matched += sn
        else:
            info.special_need_required = False
        for pat in _patterns()["required_rooms"]:  # type: ignore[attr-defined]
            m = re.search(pat, text, re.I)
            if m:
                info.required_rooms = int(m.group(1))
                break
    return info
