from flathunter.core.dedup import fingerprint, is_fuzzy_match
from flathunter.core.schema import RawListing


def mk(**kw: object) -> RawListing:
    base: dict[str, object] = dict(
        source_id="a",
        external_id="1",
        url="u",
        street="Beispielstraße",
        house_no="12",
        rooms=3.0,
        size_m2=68.13,
        rent_cold=441.42,
        floor=1,
    )
    base.update(kw)
    return RawListing(**base)  # type: ignore[arg-type]


def test_same_flat_different_spelling_same_fingerprint() -> None:
    a, b = mk(), mk(source_id="b", street="Beispielstr.", size_m2=68.4)
    assert fingerprint(a) == fingerprint(b)


def test_different_floor_or_rooms_differ() -> None:
    assert fingerprint(mk()) != fingerprint(mk(floor=2))
    assert fingerprint(mk()) != fingerprint(mk(rooms=2.0))


def test_missing_address_gives_no_fingerprint() -> None:
    assert fingerprint(mk(street=None)) is None


def test_fuzzy_match_tolerances() -> None:
    assert is_fuzzy_match(mk(), mk(size_m2=69.5, rent_cold=450.0, floor=None))
    assert not is_fuzzy_match(mk(), mk(size_m2=72.0))
    assert not is_fuzzy_match(mk(), mk(rent_cold=500.0))
    assert not is_fuzzy_match(mk(), mk(house_no="14"))
