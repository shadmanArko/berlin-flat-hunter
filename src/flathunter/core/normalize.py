"""German-format parsing helpers and address normalisation."""
from __future__ import annotations

import html
import re
from datetime import date

_NUM_RE = re.compile(r"-?\d[\d.]*(?:,\d+)?|-?\d+(?:\.\d+)?")


def parse_de_number(value: object) -> float | None:
    """'1.234,56 €' -> 1234.56; '61,50' -> 61.5; 721.85 -> 721.85; 'unbekannt' -> None."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = html.unescape(str(value)).replace("\xa0", " ").strip()
    m = _NUM_RE.search(text)
    if not m:
        return None
    tok = m.group(0)
    if "," in tok:
        tok = tok.replace(".", "").replace(",", ".")
    elif tok.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", tok):
        tok = tok.replace(".", "")  # thousands separators only
    try:
        return float(tok)
    except ValueError:
        return None


def parse_rooms(value: object) -> float | None:
    n = parse_de_number(value)
    if n is None or n <= 0 or n > 12:
        return None
    return n


def parse_date(value: object, today: date | None = None) -> date | None:
    """'01.12.2026' -> date; 'sofort'/'ab sofort' -> None (caller sets available_now)."""
    if value is None:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", str(value))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def is_now(value: object) -> bool:
    return bool(value) and bool(re.search(r"sofort", str(value), re.I))


def parse_floor(value: object) -> tuple[int | None, int | None]:
    """'2 von 5' -> (2, 5); '4 von (insg. 4)' -> (4, 4); 'EG' -> (0, None)."""
    if value is None:
        return None, None
    text = str(value)
    if re.search(r"\bEG\b|Erdgeschoss", text, re.I):
        return 0, None
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if not nums:
        return None, None
    return nums[0], nums[1] if len(nums) > 1 else None


def split_street(address: str) -> tuple[str | None, str | None]:
    """'Wittenberger Straße 21' -> ('Wittenberger Straße', '21'); '12a', '3-5' kept in house_no."""
    m = re.match(r"^\s*(.+?)\s+(\d+\s*[a-zA-Z]?(?:\s*[-/]\s*\d+\s*[a-zA-Z]?)?)\s*$", address)
    if not m:
        return (address.strip() or None), None
    return m.group(1).strip(), re.sub(r"\s+", "", m.group(2))


def norm_street(street: str | None) -> str:
    if not street:
        return ""
    s = street.lower().replace("ß", "ss")
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = re.sub(r"str\b\.?", "strasse", s)
    s = re.sub(r"strasse\b", "strasse", s)
    return re.sub(r"[^a-z0-9]", "", s)


def norm_house_no(no: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (no or "").lower())


def gross_cold(rent_cold: float | None, operating: float | None) -> float | None:
    """Bruttokaltmiete = Nettokalt + Betriebskosten excl. heating (SPEC §2.6)."""
    if rent_cold is None or operating is None:
        return None
    return round(rent_cold + operating, 2)
