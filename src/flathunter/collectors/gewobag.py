"""gewobag.de Mietangebote: WordPress list pages (sort-by=recent → newest first), one detail page
per unseen offer for the cost breakdown."""

from __future__ import annotations

import html
import re
from collections.abc import Collection

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from flathunter.collectors.base import Collector
from flathunter.core.normalize import (
    is_now,
    parse_date,
    parse_de_number,
    parse_floor,
    parse_rooms,
    split_street,
)
from flathunter.core.schema import FetchError, LayoutChangedError, RawListing

LIST_URL = "https://www.gewobag.de/fuer-mietinteressentinnen/mietangebote/"
LIST_PARAMS = {"nutzungsarten_all": "wohnung", "sort-by": "recent"}
DETAIL_CAP = 25


def _txt(n: Node | None) -> str:
    return re.sub(r"\s+", " ", n.text(separator=" ")).strip() if n is not None else ""


def parse_list(page_html: str) -> list[RawListing]:
    tree = HTMLParser(page_html)
    out: list[RawListing] = []
    for art in tree.css("article.angebot-big-box"):
        link = art.css_first("a.read-more-link")
        href = (link.attributes.get("href") if link else "") or ""
        if not href:
            continue
        ext_id = href.rstrip("/").rsplit("/", 1)[-1]
        addr = _txt(art.css_first("tr.angebot-address address"))
        street_part, _, rest = addr.partition(",")
        street, no = split_street(street_part.replace("/ ", "/").strip())
        plz = re.search(r"\b(\d{5})\b", rest)
        area = _txt(art.css_first("tr.angebot-area td"))
        m = re.match(r"([\d,.]+)\s*Zimmer\s*\|\s*([\d.,]+)\s*m", area)
        if m is None:
            continue  # parking spaces, commercial units etc. have no room count
        avail = _txt(art.css_first("tr.availability td"))
        total = parse_de_number(_txt(art.css_first("tr.angebot-kosten td")))
        pictos = " ".join(_txt(t) for t in art.css(".gw-pictogram title"))
        out.append(
            RawListing(
                source_id="gewobag",
                external_id=ext_id,
                url=href,
                title=_txt(art.css_first("h3.angebot-title")),
                street=street,
                house_no=no,
                postcode=plz.group(1) if plz else None,
                district=_txt(art.css_first("tr.angebot-region td")) or None,
                landlord="gewobag",
                rooms=parse_rooms(m.group(1)) if m else None,
                size_m2=parse_de_number(m.group(2)) if m else None,
                rent_warm=total,
                available_from=parse_date(avail),
                available_now=is_now(avail),
                wbs_text="erforderlich" if "wbs" in pictos.lower() else None,
                features=[_txt(li) for li in art.css(".angebot-characteristics li")],
                description=_txt(art.css_first("h3.angebot-title")),
                raw_text=_txt(art),
                partial=True,
            )
        )
    return out


def _pairs(main: Node) -> dict[str, str]:
    lines = [ln.strip() for ln in main.text(separator="\n").splitlines() if ln.strip()]
    labels = {
        "Grundmiete", "VZ Betriebskosten kalt", "VZ Betriebskosten warm", "Gesamtmiete", "Etage",
        "Anzahl Zimmer", "Fläche in m²", "Frei ab", "Energieträger", "Baujahr", "Anschrift", "Bezirk/Ortsteil",
    }  # fmt: skip
    return {ln: lines[i + 1] for i, ln in enumerate(lines[:-1]) if ln in labels}


def parse_detail(page_html: str, base: RawListing) -> RawListing:
    tree = HTMLParser(page_html)
    main = tree.css_first("main") or tree.body
    if main is None:
        raise LayoutChangedError(f"gewobag detail {base.external_id}: no main")
    for bad in main.css("script, style, svg, noscript"):
        bad.decompose()
    d = _pairs(main)
    rent_cold = parse_de_number(d.get("Grundmiete"))
    if rent_cold is None:
        raise LayoutChangedError(f"gewobag detail {base.external_id}: Grundmiete missing")
    floor, total_floors = parse_floor(d.get("Etage"))
    year = parse_de_number(d.get("Baujahr"))
    text = _txt(main)
    desc = ""
    m = re.search(r"Objektbeschreibung\s+(.*?)\s+Lage\s", text)
    if m:
        desc = m.group(1)
    ortsteil = (d.get("Bezirk/Ortsteil") or "").partition("/")[2].strip() or None
    avail = d.get("Frei ab", "")
    return base.model_copy(
        update={
            "rent_cold": rent_cold,
            "operating_costs": parse_de_number(d.get("VZ Betriebskosten kalt")),
            "heating_costs": parse_de_number(d.get("VZ Betriebskosten warm")),
            "rent_warm": parse_de_number(d.get("Gesamtmiete")) or base.rent_warm,
            "rooms": parse_rooms(d.get("Anzahl Zimmer")) or base.rooms,
            "size_m2": parse_de_number(d.get("Fläche in m²")) or base.size_m2,
            "floor": floor,
            "floors_total": total_floors,
            "construction_year": int(year) if year else None,
            "energy_carrier": d.get("Energieträger"),
            "ortsteil": ortsteil,
            "available_from": parse_date(avail) or base.available_from,
            "available_now": is_now(avail) or base.available_now,
            "description": f"{base.title} {desc}".strip(),
            "raw_text": text,
            "partial": False,
        }
    )


class GewobagCollector(Collector):
    source_id = "gewobag"
    name = "gewobag Mietangebote"
    tier = 1
    complete_crawl = False  # newest pages only

    async def fetch(self, known_ids: Collection[str] = ()) -> list[RawListing]:
        known = set(known_ids)
        results: list[RawListing] = []
        for page in range(1, (self.max_pages or 2) + 1):
            url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
            items = parse_list(await self.get(url, params=LIST_PARAMS))
            if not items:
                if page == 1:
                    raise LayoutChangedError("gewobag: no offers on first list page")
                break
            results.extend(items)
            if known and all(i.external_id in known for i in items):
                break
        out: list[RawListing] = []
        fetched = 0
        for base in results:
            if base.external_id in known or fetched >= DETAIL_CAP:
                out.append(base)
                continue
            try:
                out.append(parse_detail(html.unescape(await self.get(base.url)), base))
                fetched += 1
            except (FetchError, LayoutChangedError):
                out.append(base)
        return out
