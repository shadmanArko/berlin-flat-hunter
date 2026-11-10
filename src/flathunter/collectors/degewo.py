"""degewo.de Immosuche: server-rendered list pages (10 per page, no newest-first sort, so all
pages are crawled) plus one detail page per listing that we have not seen before."""
from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Collection
from urllib.parse import urljoin

import httpx
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

BASE = "https://www.degewo.de"
LIST_URL = f"{BASE}/immosuche"
_VALUE_LABELS = {"Warmmiete", "Zimmer", "m²", "frei ab"}
DETAIL_CAP = 40  # per run; the rest is picked up next run (keeps a run well-behaved)


def _txt(n: Node | None) -> str:
    return re.sub(r"\s+", " ", n.text(separator=" ")).strip() if n is not None else ""


def _defs(root: HTMLParser | Node) -> dict[str, str]:
    """Definition-list items as {label: value}. List teasers put the value in <dt>, detail
    sections put the label there, so both orders are normalised."""
    out: dict[str, str] = {}
    for item in root.css(".c-definition-list__item"):
        t, d = _txt(item.css_first("dt")), _txt(item.css_first("dd"))
        if not t and not d:
            continue
        if (t[:1].isdigit() and d and not d[:1].isdigit()) or (d in _VALUE_LABELS and t not in _VALUE_LABELS):
            t, d = d, t
        out.setdefault(t, d)
    return out


def parse_list(page_html: str) -> list[RawListing]:
    tree = HTMLParser(page_html)
    out: list[RawListing] = []
    for card in tree.css(".c-teaser--apartment"):
        a = card.css_first("h3 a[href*='/immosuche/details/']")
        if a is None:
            continue
        href = a.attributes.get("href") or ""
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        addr_p = card.css_first(".c-copy p")
        addr, _, ortsteil = _txt(addr_p).partition("|")
        street, no = split_street(addr.strip())
        d = _defs(card)
        avail = d.get("frei ab", "")
        out.append(
            RawListing(
                source_id="degewo", external_id=slug, url=urljoin(BASE, href), title=_txt(a),
                street=street, house_no=no, ortsteil=ortsteil.strip() or None, landlord="degewo",
                rooms=parse_rooms(d.get("Zimmer")), size_m2=parse_de_number(d.get("m²")),
                rent_warm=parse_de_number(d.get("Warmmiete")),
                available_from=parse_date(avail), available_now=is_now(avail),
                features=[_txt(t) for t in card.css(".c-tag__label")],
                description=_txt(a), raw_text=_txt(card), partial=True,
            )
        )
    return out


def parse_page_links(page_html: str) -> dict[int, str]:
    """Pagination links carry a cHash, so they must be followed, not constructed."""
    pages: dict[int, str] = {}
    for m in re.finditer(r'href="([^"]*?tx_openimmo_immobilie%5Bpage%5D&#x3D;(\d+)[^"]*)"', page_html):
        pages[int(m.group(2))] = urljoin(BASE, html.unescape(m.group(1)))
    return pages


def parse_total(page_html: str) -> int | None:
    m = re.search(r"(\d+)\s+Ergebnisse", page_html)
    return int(m.group(1)) if m else None


def parse_detail(page_html: str, base: RawListing) -> RawListing:
    tree = HTMLParser(page_html)
    main = tree.css_first("main") or tree.body
    if main is None or tree.css_first("#section-def-list-rent-details") is None:
        raise LayoutChangedError(f"degewo detail {base.external_id}: cost section missing")
    for bad in main.css("script, style, noscript"):
        bad.decompose()
    d = _defs(main)
    text = _txt(main)

    rent_cold = parse_de_number(d.get("Nettokaltmiete"))
    bk_cold = parse_de_number(d.get("Betriebskosten (kalt)"))
    bk_warm = parse_de_number(d.get("Betriebskosten (warm)"))
    if rent_cold is None:
        raise LayoutChangedError(f"degewo detail {base.external_id}: Nettokaltmiete missing")

    m = re.search(r"Adresse:\s*([^,]+?),\s*(\d{5})\s+Berlin", text)
    street, no, plz = base.street, base.house_no, base.postcode
    if m:
        street, no = split_street(m.group(1).strip())
        plz = m.group(2)
    floor, total = parse_floor(d.get("Etage"))
    year = parse_de_number(d.get("Baujahr"))

    desc_node = None
    for h in main.css("h2, h3"):
        if _txt(h) == "Beschreibung":
            desc_node = h.parent
            break
    description = _txt(desc_node)
    hints = ""
    for h in main.css("h2, h3"):
        if _txt(h) == "Wichtige Hinweise":
            hints = _txt(h.parent)
    feats = [_txt(t) for t in main.css(".c-tag__label")]
    ausstattung = re.search(r"Ausstattung\s+([^.]{5,300}?)\s+Wichtige Hinweise", text)
    if ausstattung:
        feats += [f.strip() for f in ausstattung.group(1).split(",")]
    # degewo marks WBS flats with a "Mit WBS" feature tag and a "WBS-Pflicht" entry (empty value).
    wbs_required = "WBS-Pflicht" in d or any(f.lower().startswith("mit wbs") for f in feats)
    wbs_signals = "WBS erforderlich" if wbs_required else None
    avail = d.get("frei ab", "")

    return base.model_copy(update={
        "street": street, "house_no": no, "postcode": plz, "partial": False,
        "rent_cold": rent_cold, "operating_costs": bk_cold, "heating_costs": bk_warm,
        "rent_warm": parse_de_number(d.get("Warmmiete")) or base.rent_warm,
        "rooms": parse_rooms(d.get("Zimmer")) or base.rooms,
        "size_m2": parse_de_number(d.get("Wohnfläche")) or base.size_m2,
        "floor": floor, "floors_total": total,
        "construction_year": int(year) if year else None,
        "energy_carrier": d.get("Primärer Energieträger"),
        "available_from": parse_date(avail) or base.available_from,
        "available_now": is_now(avail) or base.available_now,
        "wbs_text": wbs_signals,
        "features": sorted({f for f in feats if f}),
        "description": " ".join(x for x in (base.title, description, hints) if x),
        "raw_text": text,
    })


def build_wbs_filter(page_html: str) -> tuple[str, dict[str, str]]:
    """The search is a TYPO3 form POST. Its list pages are unstable when unfiltered (sorting
    ties make listings repeat across pages and others vanish), whereas the WBS-only subset is
    small (~2 pages) and stable. Returns (action_url, form_data) with wbsSozialwohnung=1."""
    form = HTMLParser(page_html).css_first("form#form-filter-immo-objects")
    if form is None:
        raise LayoutChangedError("degewo: search filter form not found")
    data: dict[str, str] = {}
    for inp in form.css("input"):
        name = inp.attributes.get("name")
        if name and inp.attributes.get("type") != "checkbox":
            data[name] = inp.attributes.get("value") or ""
    data["tx_openimmo_immobilie[wbsSozialwohnung]"] = "1"
    action = html.unescape(form.attributes.get("action") or "/immosuche")
    return urljoin(BASE, action), data


class DegewoCollector(Collector):
    """WBS-bound flats on degewo.de. Free-market flats are covered via inberlinwohnen."""

    source_id = "degewo"
    name = "degewo Immosuche (WBS subset)"
    tier = 1
    complete_crawl = True

    async def _post(self, url: str, data: dict[str, str]) -> str:
        await asyncio.sleep(self.min_delay_s)
        try:
            resp = await self.client.post(url, data=data)
        except httpx.HTTPError as e:
            raise FetchError(f"degewo: {type(e).__name__} posting filter: {e}") from e
        self.http_status = resp.status_code
        if resp.status_code != 200:
            raise FetchError(f"degewo: HTTP {resp.status_code} on filter POST")
        return resp.text

    async def fetch(self, known_ids: Collection[str] = ()) -> list[RawListing]:
        known = set(known_ids)
        landing = await self.get(LIST_URL)
        action, data = build_wbs_filter(landing)
        first = await self._post(action, data)
        items = parse_list(first)
        total = parse_total(first)
        if not items:
            if total == 0:
                return []  # legitimately no WBS flats right now
            raise LayoutChangedError("degewo: no listing cards in filtered list page 1")
        links = parse_page_links(first)
        listings = {i.external_id: i for i in items}
        seen_pages, queue = {1}, sorted(links)
        while queue:
            n = queue.pop(0)
            if n in seen_pages or (self.max_pages and n > self.max_pages):
                continue
            seen_pages.add(n)
            more = parse_list(await self.get(links[n]))
            if not more:
                raise LayoutChangedError(f"degewo: filtered list page {n} has no cards")
            for i in more:
                listings.setdefault(i.external_id, i)
        if total is not None and not self.max_pages and len(listings) < total * 0.8:
            raise LayoutChangedError(f"degewo: parsed {len(listings)} of {total} announced listings")

        result: list[RawListing] = []
        fetched = failed = 0
        for ext_id, base in listings.items():
            if ext_id in known or fetched >= DETAIL_CAP:
                result.append(base)  # partial: counts as "seen", details come later
                continue
            try:
                result.append(parse_detail(await self.get(base.url), base))
                fetched += 1
            except (FetchError, LayoutChangedError):
                failed += 1
                result.append(base)
                if failed >= 3 and fetched == 0:
                    raise
        return result
