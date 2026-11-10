from datetime import date

import pytest

from flathunter.core.normalize import (
    gross_cold,
    norm_street,
    parse_date,
    parse_de_number,
    parse_floor,
    parse_rooms,
    split_street,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.234,56 €", 1234.56), ("61,50", 61.5), (721.85, 721.85), ("498,90 €", 498.9),
     ("1.339,79", 1339.79), ("unbekannt", None), (None, None), ("2.500", 2500.0), ("&euro; 12,5", 12.5)],
)
def test_parse_de_number(raw: object, expected: float | None) -> None:
    assert parse_de_number(raw) == expected


def test_rooms_bounds() -> None:
    assert parse_rooms("3,0") == 3.0
    assert parse_rooms("2,5") == 2.5
    assert parse_rooms("0") is None
    assert parse_rooms("99") is None


def test_dates_and_floor() -> None:
    assert parse_date("ab 01.12.2026") == date(2026, 12, 1)
    assert parse_date("sofort") is None
    assert parse_floor("2 von 5") == (2, 5)
    assert parse_floor("4 von (insg. 4)") == (4, 4)
    assert parse_floor("EG") == (0, None)
    assert parse_floor(None) == (None, None)


def test_street_normalisation_is_stable_across_spellings() -> None:
    assert split_street("Wittenberger Straße 21") == ("Wittenberger Straße", "21")
    assert split_street("Karl-Holtz-Str. 4a") == ("Karl-Holtz-Str.", "4a")
    assert norm_street("Wittenberger Straße") == norm_street("Wittenberger Str.") == "wittenbergerstrasse"
    assert norm_street("Müggelschlößchenweg") == "mueggelschloesschenweg"


def test_gross_cold_excludes_heating() -> None:
    assert gross_cold(596.67, 125.18) == 721.85
    assert gross_cold(596.67, None) is None
