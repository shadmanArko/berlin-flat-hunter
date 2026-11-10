from pathlib import Path

import httpx
import pytest
import respx

from flathunter.collectors.degewo import (
    BASE,
    LIST_URL,
    DegewoCollector,
    parse_detail,
    parse_list,
    parse_page_links,
)
from flathunter.collectors.inberlinwohnen import BASE as IBW_URL
from flathunter.collectors.inberlinwohnen import InBerlinWohnenCollector, parse_page
from flathunter.core.schema import LayoutChangedError

FX = Path(__file__).parent / "fixtures"


def read(p: str) -> str:
    return (FX / p).read_text()


# --- inberlinwohnen -------------------------------------------------------------------------


def test_ibw_parse_page_fields() -> None:
    items = parse_page(read("inberlinwohnen/page1.html"))
    assert len(items) == 10
    f = next(i for i in items if i.external_id == "24217")
    assert f.street == "Anna-Ebermann-Straße" and f.house_no == "10" and f.postcode == "13053"
    assert (f.rooms, f.size_m2, f.rent_cold, f.operating_costs) == (3.0, 68.13, 441.42, 158.29)
    assert f.heating_costs == pytest.approx(167.26)  # Gesamtmiete − Kalt − Nebenkosten
    assert f.rent_warm == 766.97
    assert f.energy_carrier == "Fernwärme"
    assert f.floor == 1 and f.floors_total == 6 and f.construction_year == 1973
    assert f.landlord == "howoge" and f.wbs_text == "nicht erforderlich"
    assert f.published_at is not None and f.url.startswith("https://www.howoge.de/")


def test_ibw_all_pages_have_complete_core_fields() -> None:
    for n in (1, 2, 3):
        for i in parse_page(read(f"inberlinwohnen/page{n}.html")):
            assert i.rooms and i.size_m2 and i.rent_cold and i.street and i.house_no, i.external_id


@respx.mock
async def test_ibw_collector_paginates_and_stops_on_known_page() -> None:
    route = respx.get(IBW_URL).mock(
        side_effect=[httpx.Response(200, text=read(f"inberlinwohnen/page{n}.html")) for n in (1, 2, 3)]
    )
    c = InBerlinWohnenCollector(max_pages=3)
    c.min_delay_s = 0
    items = await c.fetch()
    await c.aclose()
    assert len(items) == 30 and route.call_count == 3

    respx.reset()
    page1_ids = {i.external_id for i in parse_page(read("inberlinwohnen/page1.html"))}
    route = respx.get(IBW_URL).mock(return_value=httpx.Response(200, text=read("inberlinwohnen/page1.html")))
    c = InBerlinWohnenCollector(max_pages=3)
    c.min_delay_s = 0
    await c.fetch(known_ids=page1_ids)
    await c.aclose()
    assert route.call_count == 1  # newest page fully known → no further requests


@respx.mock
async def test_ibw_layout_change_raises_not_empty() -> None:
    respx.get(IBW_URL).mock(return_value=httpx.Response(200, text="<html><body>redesign</body></html>"))
    c = InBerlinWohnenCollector()
    with pytest.raises(LayoutChangedError):
        await c.fetch()
    await c.aclose()


# --- degewo ---------------------------------------------------------------------------------


def test_degewo_list_parse() -> None:
    items = parse_list(read("degewo/list1.html"))
    assert len(items) == 10
    assert all(i.partial and i.street and i.rooms and i.size_m2 and i.rent_warm for i in items)
    assert set(parse_page_links(read("degewo/list1.html"))) >= {2}


def test_degewo_detail_special_need_listing() -> None:
    slug = "3-zimmer-wohnung-in-schoener-lage-nur-mit-wbs-mit-besonderem-wohnbedarf-140"
    base = next(
        i
        for i in parse_list(read("degewo/list1.html")) + parse_list(read("degewo/list2.html"))
        if i.external_id == slug
    )
    d = parse_detail(read("degewo/detail_3-zimmer-wohnung-in-schoener-l.html"), base)
    assert not d.partial
    assert (d.street, d.house_no, d.postcode) == ("Friedrichrodaer Straße", "125", "12249")
    assert (d.rooms, d.size_m2) == (3.0, 77.85)
    assert (d.rent_cold, d.operating_costs, d.heating_costs, d.rent_warm) == (612.26, 140.14, 122.22, 874.62)
    assert d.floor == 4 and d.floors_total == 4 and d.construction_year == 1963
    assert d.energy_carrier == "Fernwärme" and d.available_now
    assert "besonderem Wohnbedarf" in d.description


def test_degewo_detail_layout_change() -> None:
    base = parse_list(read("degewo/list1.html"))[0]
    with pytest.raises(LayoutChangedError):
        parse_detail("<html><main>new design</main></html>", base)


@respx.mock
async def test_degewo_collector_end_to_end() -> None:
    l1, l2 = parse_list(read("degewo/list1.html")), parse_list(read("degewo/list2.html"))
    page2_url = parse_page_links(read("degewo/list1.html"))[2]
    respx.get(page2_url).mock(return_value=httpx.Response(200, text=read("degewo/list2.html")))
    respx.get(LIST_URL, params={}).mock(return_value=httpx.Response(200, text=read("degewo/landing.html")))
    post = respx.post(url__startswith=f"{BASE}/immosuche").mock(
        return_value=httpx.Response(200, text=read("degewo/list1.html"))
    )
    detail_by_slug = {
        "3-zimmer-wohnung-in-schoener-lage-nur-mit-wbs-mit-besonderem-wohnbedarf-140": (
            "degewo/detail_3-zimmer-wohnung-in-schoener-l.html"
        ),
    }
    for i in l1 + l2:
        fx = detail_by_slug.get(i.external_id)
        respx.get(i.url).mock(return_value=httpx.Response(200, text=read(fx) if fx else "<html/>"))
    c = DegewoCollector()
    c.min_delay_s = 0
    known = {i.external_id for i in l1 + l2} - set(detail_by_slug)
    items = await c.fetch(known_ids=known)
    await c.aclose()
    assert post.called
    assert len({i.external_id for i in items}) == len(items) == len({i.external_id for i in l1 + l2})
    full = [i for i in items if not i.partial]
    assert [i.external_id for i in full] == list(detail_by_slug)


# --- gewobag --------------------------------------------------------------------------------


def test_gewobag_list_and_detail() -> None:
    from flathunter.collectors.gewobag import parse_detail as gw_detail
    from flathunter.collectors.gewobag import parse_list as gw_list

    items = gw_list(read("gewobag/list1.html"))
    assert len(items) >= 5 and all(i.partial and i.street and i.rooms and i.size_m2 for i in items)
    base = next(i for i in items if i.external_id == "0100-01723-0104-0033")
    assert base.wbs_text == "erforderlich" and base.postcode == "12043" and base.house_no == "61/63"
    d = gw_detail(read("gewobag/detail_0100-01723-0104-0033.html"), base)
    assert (d.rent_cold, d.operating_costs, d.heating_costs, d.rent_warm) == (803.79, 236.0, 300.0, 1339.79)
    assert (d.rooms, d.size_m2, d.floor, d.construction_year) == (3.0, 101.63, 3, 1900)
    assert d.energy_carrier == "Fernwärme" and "min. 3 Räume" in d.description


def test_gewobag_layout_change() -> None:
    from flathunter.collectors.gewobag import parse_detail as gw_detail
    from flathunter.collectors.gewobag import parse_list as gw_list

    base = gw_list(read("gewobag/list1.html"))[0]
    with pytest.raises(LayoutChangedError):
        gw_detail("<html><main>redesign</main></html>", base)
    assert gw_list("<html><body>redesign</body></html>") == []
