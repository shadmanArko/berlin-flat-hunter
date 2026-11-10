import pytest

from flathunter.core.wbs import parse_wbs


def test_degewo_special_need_sentence() -> None:
    t = ("Für die Anmietung dieser Wohnung ist ein Wohnberechtigungsschein 100 oder 140 "
         "mit besonderem Wohnbedarf erforderlich.")
    w = parse_wbs(t)
    assert w.wbs_required is True
    assert w.special_need_required is True
    assert w.wbs_levels == [100, 140]


@pytest.mark.parametrize("text", ["kein WBS erforderlich", "Ohne WBS", "WBS nicht erforderlich",
                                  "Für die Anmietung der Wohnung ist kein WBS erforderlich"])
def test_no_wbs_phrases_are_not_wbs(text: str) -> None:
    w = parse_wbs(text)
    assert w.wbs_required is False
    assert w.special_need_required is None


def test_levels_and_ranges() -> None:
    assert parse_wbs("Vermietung mit WBS 160 -220 oder Einkommensprüfung").wbs_levels == [160, 180, 220]
    assert parse_wbs("WBS bis 140").wbs_levels == [100, 140]
    assert parse_wbs("WBS 100/140 bW").special_need_required is True
    assert parse_wbs("Klein, aber fein! Erdgeschosswohnung mit WBS 140!").wbs_levels == [140]


def test_bw_shorthand_and_dringlichkeit() -> None:
    assert parse_wbs("zur Anmietung WBS 100 bW erforderlich").special_need_required is True
    assert parse_wbs("WBS mit Dringlichkeit").special_need_required is True


def test_wbs_without_special_need() -> None:
    w = parse_wbs("nur mit WBS 140")
    assert w.wbs_required is True and w.special_need_required is False


def test_required_rooms() -> None:
    assert parse_wbs("WBS für 3 Räume").required_rooms == 3
    assert parse_wbs("WBS 140 für 2 Zimmer").required_rooms == 2


def test_structured_field_wins_and_conflicts_are_flagged() -> None:
    assert parse_wbs("Schöne Wohnung", structured="nicht erforderlich").wbs_required is False
    assert parse_wbs("Schöne Wohnung", structured="erforderlich").wbs_required is True
    # source says no WBS but the text names a level → ambiguous
    c = parse_wbs("mit WBS 140 zu vermieten", structured="nicht erforderlich")
    assert c.wbs_required is None and c.matched[0].startswith("conflict")
    assert parse_wbs("Helle Wohnung am Park").wbs_required is None
