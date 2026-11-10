"""inberlinwohnen.de Wohnungsfinder. The page is a Livewire app that server-renders the full
listing JSON into `wire:snapshot` attributes, so we parse that instead of HTML."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Collection
from datetime import datetime
from typing import Any

from flathunter.collectors.base import Collector
from flathunter.core.normalize import (
    parse_date,
    parse_de_number,
    parse_floor,
    parse_rooms,
)
from flathunter.core.schema import LayoutChangedError, RawListing

BASE = "https://www.inberlinwohnen.de/wohnungsfinder/"
_SNAP_RE = re.compile(r'wire:snapshot="([^"]*)"')


def _walk(o: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(o, dict):
        if "rentGross" in o and "address" in o and "deeplink" in o:
            out.append(o)
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


def _labels(o: Any, out: dict[str, Any]) -> None:
    if isinstance(o, dict):
        if "label" in o and "value" in o:
            out[str(o["label"])] = o["value"]
        for v in o.values():
            _labels(v, out)
    elif isinstance(o, list):
        for v in o:
            _labels(v, out)


def _first(x: Any) -> dict[str, Any]:
    """Livewire wraps arrays as [data, {"s": "arr"}]; unwrap lists of dicts."""
    if isinstance(x, list) and x and isinstance(x[0], dict):
        return x[0]
    return x if isinstance(x, dict) else {}


def parse_page(page_html: str) -> list[RawListing]:
    flats: list[dict[str, Any]] = []
    for snap in _SNAP_RE.findall(page_html):
        try:
            _walk(json.loads(html.unescape(snap)), flats)
        except json.JSONDecodeError:
            continue
    out: list[RawListing] = []
    for f in flats:
        lab: dict[str, Any] = {}
        _labels(f.get("details"), lab)
        addr = _first(f.get("address"))
        company = _first(f.get("company"))
        rent_net = parse_de_number(f.get("rentNet"))
        extra = parse_de_number(f.get("extraCosts"))
        total = parse_de_number(lab.get("Gesamtmiete"))
        heating = (
            round(total - rent_net - extra, 2)
            if total is not None and rent_net is not None and extra is not None
            else None
        )
        if heating is not None and heating < 0:
            heating = None
        floor, floors_total = parse_floor(lab.get("Etage"))
        if floors_total is None:
            floors_total = f.get("levelsTotal") if isinstance(f.get("levelsTotal"), int) else None
        title = str(f.get("title") or "").strip()
        wbs_field = lab.get("WBS")
        carrier = lab.get("Hauptenergieträger")
        created = f.get("createdAt")
        try:
            published = datetime.fromisoformat(str(created).replace("Z", "+00:00")) if created else None
        except ValueError:
            published = None
        year = parse_de_number(f.get("constructionYear"))
        rooms_raw = f.get("rooms")
        feats = [str(x) for x in ([lab["Heizung"]] if lab.get("Heizung") else [])]
        out.append(
            RawListing(
                source_id="inberlinwohnen",
                external_id=str(f["id"]),
                url=str(f["deeplink"]),
                title=title,
                street=addr.get("street"),
                house_no=str(addr.get("number") or "") or None,
                postcode=addr.get("zipCode"),
                district=addr.get("district"),
                lat=parse_de_number(addr.get("lat")),
                lon=parse_de_number(addr.get("lon")),
                rooms=parse_rooms(rooms_raw),
                size_m2=parse_de_number(f.get("area")),
                rent_cold=rent_net,
                operating_costs=extra,
                heating_costs=heating,
                rent_warm=total,
                energy_carrier=None if str(carrier).lower() in ("unbekannt", "none", "") else carrier,
                floor=floor,
                floors_total=floors_total,
                construction_year=int(year) if year else None,
                available_from=parse_date(f.get("occupationDate") or lab.get("Bezugsfertig ab")),
                published_at=published,
                landlord=(company.get("intern") or company.get("name") or "").strip() or None,
                wbs_text=str(wbs_field) if wbs_field is not None else None,
                features=[re.sub(r"<[^>]+>", "", x).strip() for x in feats],
                description=title,
                raw_text=title + "\n" + "\n".join(f"{k}: {v}" for k, v in lab.items()),
            )
        )
    return out


class InBerlinWohnenCollector(Collector):
    source_id = "inberlinwohnen"
    name = "inberlinwohnen.de Wohnungsfinder"
    tier = 1
    complete_crawl = False  # only the newest max_pages pages are read

    async def fetch(self, known_ids: Collection[str] = ()) -> list[RawListing]:
        pages = self.max_pages or 3
        results: list[RawListing] = []
        for page in range(1, pages + 1):
            text = await self.get(BASE, params={"page": str(page)} if page > 1 else None)
            items = parse_page(text)
            if not items:
                if page == 1:
                    raise LayoutChangedError("inberlinwohnen: no listings in page 1 snapshots")
                break
            results.extend(items)
            # Newest-first: stop early once an entire page is already known.
            if known_ids and all(i.external_id in known_ids for i in items):
                break
        return results
