from typing import Any

from flathunter.core.eligibility import classify
from flathunter.core.profile import Profile

P = Profile(household_size=3, special_need=True, berechtigungsgruppe="J", max_rooms=3)


def f(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        rooms=3.0,
        rent_cold=500.0,
        operating_costs=150.0,
        wbs_required=True,
        special_need_required=True,
        text="",
        district="Lichtenberg",
    )
    base.update(kw)
    return base


def test_p0_special_need() -> None:
    v = classify(f(), P)
    assert v.eligibility_class == "P0_special_need" and v.rent.status == "rent_ok"
    assert v.rent.limit == 736.0 and v.rent.headroom == 86.0


def test_p1_when_no_special_need_required() -> None:
    assert classify(f(special_need_required=False), P).eligibility_class == "P1_wbs"


def test_special_need_not_granted_is_ineligible() -> None:
    v = classify(f(), Profile(special_need=False))
    assert v.eligibility_class == "ineligible" and "special_need" in v.reason


def test_p2_free_market_uses_general_limit() -> None:
    v = classify(f(wbs_required=False, special_need_required=None, rent_cold=500, operating_costs=150), P)
    assert v.eligibility_class == "P2_free_market" and v.rent.limit == 668.8
    v = classify(f(wbs_required=False, rent_cold=520, operating_costs=150), P)  # 670 > 668.8 but ≤ +10 %
    assert v.eligibility_class == "needs_review" and v.reason == "rent_borderline"


def test_rent_thresholds_wbs() -> None:
    assert classify(f(rent_cold=600, operating_costs=136), P).rent.status == "rent_ok"  # 736 exactly
    b = classify(f(rent_cold=650, operating_costs=150), P)  # 800 ≤ 809.6
    assert b.eligibility_class == "needs_review" and "ask Jobcenter before applying" in b.notes
    o = classify(f(rent_cold=700, operating_costs=150), P)
    assert o.eligibility_class == "ineligible" and o.reason == "rent_over_av_wohnen"


def test_rent_unknown_still_alerts() -> None:
    v = classify(f(operating_costs=None), P)
    assert v.eligibility_class == "P0_special_need" and v.rent.status == "rent_unknown"


def test_rent_override() -> None:
    p = Profile(rent_limit_override=900.0)
    assert classify(f(rent_cold=700, operating_costs=150), p).eligibility_class == "P0_special_need"


def test_room_rules() -> None:
    assert classify(f(rooms=2.0), P).eligibility_class == "P0_special_need"
    v = classify(f(rooms=3.5), P)
    assert v.eligibility_class == "needs_review" and any("3 Räume" in n for n in v.notes)
    assert classify(f(rooms=4.0), P).eligibility_class == "ineligible"
    assert classify(f(wbs_required_rooms=4), P).eligibility_class == "ineligible"
    assert classify(f(wbs_required_rooms=2), P).eligibility_class == "P0_special_need"
    # free market: no room cap
    assert classify(f(wbs_required=False, rooms=4.0, rent_cold=400), P).eligibility_class == "P2_free_market"


def test_restrictions() -> None:
    assert classify(f(text="Seniorengerechtes Wohnen 55 plus"), P).reason == "senior_only"
    assert classify(f(text="Wohnung ab 60 Jahren"), P).reason == "senior_only"
    assert (
        classify(f(text="Modern wohnen für Studierende und Auszubildende mit WBS"), P).reason
        == "students_or_trainees_only"
    )
    assert classify(f(text="nur für Wohnungstausch"), P).reason == "only_for_wohnungstausch"
    c = classify(f(text="Genossenschaftsmitgliedschaft erforderlich"), P)
    assert c.eligibility_class == "P0_special_need" and c.notes


def test_berechtigungsgruppe() -> None:
    assert classify(f(text="nur für Berechtigungsgruppe A, B"), P).reason == "berechtigungsgruppe_not_listed"
    assert classify(f(text="nur für Berechtigungsgruppe I und J"), P).eligibility_class == "P0_special_need"


def test_unclear_wbs_is_review() -> None:
    assert classify(f(wbs_required=None), P).eligibility_class == "needs_review"


def test_wohnkueche_review_and_excluded_district() -> None:
    assert classify(f(text="große Wohnküche"), P).eligibility_class == "needs_review"
    assert classify(f(text="große Wohnküche", rooms=2.0), P).eligibility_class == "P0_special_need"
    assert classify(f(), Profile(districts_excluded=["lichtenberg"])).reason == "excluded_district"


def test_parking_and_commercial_are_not_apartments() -> None:
    for title in ["Stellplatz zu vermieten", "Offener Stellplatz in der Tiefgarage", "PKW-Stellplatz im Hof"]:
        v = classify(f(rooms=None, size_m2=None, rent_cold=70.0, operating_costs=None, title=title), P)
        assert v.eligibility_class == "ineligible" and v.reason == "not_an_apartment"
    v = classify(f(rooms=None, size_m2=None, rent_cold=57.5, operating_costs=None, title="x"), P)
    assert v.reason == "not_an_apartment"
