"""Save trimmed real responses as test fixtures (manual; hits live sites politely).
Usage: uv run python scripts/capture_fixtures.py <degewo-detail-slug> ..."""

import asyncio
import re
import sys
from pathlib import Path

from flathunter.collectors.degewo import (
    LIST_URL,
    DegewoCollector,
    build_wbs_filter,
    parse_list,
    parse_page_links,
)

FX = Path("tests/fixtures")
IBW = "https://www.inberlinwohnen.de/wohnungsfinder/"


def trim_degewo(html: str, keep_svg: bool = False) -> str:
    tags = "script|style|noscript" if keep_svg else "script|style|svg|noscript"
    html = re.sub(rf"<({tags})\b.*?</\1>", "", html, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def trim_ibw(html: str) -> str:
    keep = [s for s in re.findall(r'wire:snapshot="[^"]*"', html) if "rentGross" in s]
    return "<html><body>\n" + "\n".join(f"<div {s}></div>" for s in keep) + "\n</body></html>"


async def capture_gewobag() -> None:
    from flathunter.collectors.gewobag import LIST_PARAMS, LIST_URL, GewobagCollector, parse_list

    c = GewobagCollector()
    try:
        page = await c.get(LIST_URL, params=LIST_PARAMS)
        (FX / "gewobag").mkdir(exist_ok=True)
        (FX / "gewobag" / "list1.html").write_text(trim_degewo(page, keep_svg=True))
        for i in parse_list(page)[:2]:
            (FX / "gewobag" / f"detail_{i.external_id}.html").write_text(trim_degewo(await c.get(i.url)))
    finally:
        await c.aclose()


async def main() -> None:
    if sys.argv[1:] == ["gewobag"]:
        return await capture_gewobag()
    c = DegewoCollector()
    try:
        for p in (1, 2, 3):
            h = await c.get(IBW, params={"page": str(p)} if p > 1 else None)
            (FX / "inberlinwohnen" / f"page{p}.html").write_text(trim_ibw(h))
        landing = await c.get(LIST_URL)
        (FX / "degewo" / "landing.html").write_text(trim_degewo(landing))
        action, data = build_wbs_filter(landing)
        first = await c._post(action, data)
        (FX / "degewo" / "list1.html").write_text(trim_degewo(first))
        links = parse_page_links(first)
        cards = parse_list(first)
        if 2 in links:
            p2 = await c.get(links[2])
            (FX / "degewo" / "list2.html").write_text(trim_degewo(p2))
            cards += parse_list(p2)
        for slug in sys.argv[1:]:
            card = next(x for x in cards if x.external_id.startswith(slug))
            (FX / "degewo" / f"detail_{slug[:30]}.html").write_text(trim_degewo(await c.get(card.url)))
            print("saved", card.external_id)
    finally:
        await c.aclose()


asyncio.run(main())
