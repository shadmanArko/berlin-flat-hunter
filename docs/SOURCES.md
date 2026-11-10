# Sources (verified 2026-11-10)

| id | method | robots.txt | notes |
|---|---|---|---|
| `inberlinwohnen` | Livewire `wire:snapshot` JSON embedded in server-rendered HTML of `/wohnungsfinder/?page=N` | `Disallow:` empty → allowed | Newest first, 10 per page. Carries degewo, Gewobag, HOWOGE, Stadt und Land, WBM, GESOBAU, berlinovo. Has address + lat/lon, Kalt/Nebenkosten/Gesamtmiete, energy carrier, floor, structured WBS field (`erforderlich` / `nicht erforderlich`). Heating cost = Gesamtmiete − Kalt − Nebenkosten. Each poll reads page 1 and continues only while the page holds unseen listings (max 3 pages). |
| `degewo` | TYPO3 form POST with `wbsSozialwohnung=1`, then detail page per unseen listing | `/immosuche` allowed | The unfiltered list is unreliable (default sort by rooms has ties, so listings repeat across pages and others vanish). The WBS-only subset (~18 flats, 2 pages) is stable. Free-market degewo flats are covered via inberlinwohnen. Detail page gives Nettokalt, Betriebskosten kalt/warm, floor, energy carrier, WBS tags, free text ("Wichtige Hinweise" names the WBS level/bW requirement). |

Politeness: custom honest User-Agent, ≥ 2 s between requests (±20 % jitter), no parallel requests per source, stop-early pagination.
Terms of service were not reviewed in depth; only public listing pages are read, no login, no CAPTCHA.
| `gewobag` | WordPress list `/mietangebote/?nutzungsarten_all=wohnung&sort-by=recent` (newest first; pages `/page/N/`), detail page per unseen offer | robots.txt only restricts Googlebot-Image | List gives address, rooms, m², Gesamtmiete and a WBS pictogram; detail gives Grundmiete, VZ Betriebskosten kalt/warm, floor, energy carrier. Parking/commercial offers (no room count) are skipped. Gewobag writes house-number ranges ("61/63"); the fuzzy matcher treats overlapping numbers as the same building. |

## Not built yet: howoge, wbm, stadtundland, berlinovo, gesobau
All are already carried by `inberlinwohnen` (company filter lists berlinovo, degewo, GESOBAU, Gewobag, HOWOGE, Stadt und Land, WBM), so coverage is complete. Own-site collectors only reduce latency. Probed 2026-11-10: wbm.de is server-rendered (simple); howoge.de's robots.txt forbids URLs containing `cHash`, so pagination must avoid those links; stadtundland.de needs XHR discovery. They are queued after M3 (deployment) so latency can be measured on real data first.

## Where else to look (researched 2026-11-10)
Reachability and robots.txt were checked for every host below. Whether each carries Berlin WBS flats is **not yet verified** unless stated.

| Tier | Source | How | Status |
|---|---|---|---|
| 1 | inberlinwohnen.de | collector | live; carries all city-owned companies |
| 1 | degewo (WBS subset), gewobag | collectors | live |
| 1 | howoge, wbm, stadtundland, gesobau, berlinovo own sites | collectors | queued; only reduce latency |
| 2 | Vonovia, Deutsche Wohnen, Covivio, Heimstaden | scrape if they list WBS flats | queued, need a check of WBS stock |
| 3 | ImmoScout24 (has a "WBS erforderlich" filter), Immowelt, Kleinanzeigen | **email alerts** (no scraping, heavy bot detection) | needs a mailbox from the owner |
| 4 | Genossenschaften (80+ in Berlin; some have WBS flats, often membership shares required) | page-change watcher per cooperative; directory: wohnungsbaugenossenschaften.de (region Berlin), BBU member list | queued |
| – | berlin.de WBS information, Berliner Mieterverein | reference only | – |

Search engines returned mostly blog articles; they were used only to confirm that cooperatives rarely list on the big portals and that ImmoScout24/Immowelt are the main private channels.
