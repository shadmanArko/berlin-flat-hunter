# Decisions

## 2026-11-10 — Postgres via Docker Compose on port 5433
Local Postgres 16 in docker-compose (host port 5433 to avoid clashing with a local Postgres). Same image in CI.

## 2026-11-10 — Local personal-data guard instead of gitleaks only
gitleaks is not installed locally and doesn't know the household's names. `scripts/check_no_personal_data.py` (git pre-commit hook) blocks any staged file containing a value from `config/profile.yaml` or a token-shaped string. gitleaks still runs in CI.

## 2026-11-10 — Repo remote not created automatically
Creating a GitHub repo publishes code; asked in INPUTS_NEEDED.md #1. Development continues locally, CI workflow is committed.

## 2026-11-10 — Python pinned to 3.12 (`.python-version`); ruff line length 110
uv had picked 3.13; spec says 3.12.

## 2026-11-10 — selectolax lexbor backend
`selectolax.parser` (Modest) is deprecated and raises ImportError in 1.0; using `selectolax.lexbor`.

## 2026-11-10 — inberlinwohnen: parse Livewire snapshots, not HTML
The page embeds complete structured listing data (address, lat/lon, costs, WBS field, company) as JSON in `wire:snapshot` attributes. This is the XHR-equivalent JSON the spec prefers over HTML parsing, with no Playwright needed.
Heating cost is derived as Gesamtmiete − Kaltmiete − Nebenkosten (verified on 30 listings; Nebenkosten there excludes heating).

## 2026-11-10 — degewo: crawl only the WBS-filtered subset
Unfiltered pagination is unstable (ties in the sort order duplicate and drop listings; measured 71 unique of 105 rows). Posting the site's own filter form with `wbsSozialwohnung=1` gives a stable ~18-listing, 2-page set, which is the part that matters for a WBS household. Free-market degewo flats arrive via inberlinwohnen. Alternative rejected: union of several sorted crawls (33 requests per poll, still lossy).

## 2026-11-10 — Dedup fingerprint excludes postcode, includes floor
Sources differ on postcode availability. Social-housing blocks contain many identical stacked flats, so floor is part of the key; when one source lacks floor, the fuzzy matcher (same building, rooms, size ±2 m², rent ±3 %) merges instead. Verified live: a flat on degewo + inberlinwohnen became one listing with two sources.

## 2026-11-10 — `partial` listings
When a collector only has list-page data (known listing, no detail fetch) it sets `partial=True`; the store then never overwrites WBS/eligibility fields from that thinner data.

## 2026-11-10 — Gone-detection only for complete crawls
`mark_missing` runs only for collectors with `complete_crawl = True` (degewo's WBS subset). inberlinwohnen reads only the newest pages, so absence there means nothing.

## 2026-11-10 — Test isolation
DB tests create a throwaway Postgres schema per test against `DATABASE_URL` (skipped if Postgres is unreachable); CI provides a Postgres 16 service.

## 2026-11-10 — gitleaks run as binary in CI
gitleaks-action failed on a repo whose first commit has no parent (`<first>^..` range). Running the pinned binary over the full history instead.

## 2026-11-10 — Eligibility ordering and noise control
- Hard exclusions (swap-only, students/trainees, senior, wheelchair, excluded district) run first, then WBS/rooms/Berechtigungsgruppe, then rent. A rent-over flat is `ineligible` even if it also has a Wohnküche.
- Wohnküche only forces `needs_review` when the flat already has the full entitlement (3 rooms), because only then can an extra counted room push it over; otherwise it is a note in the alert.
- A flat that needs no WBS and has borderline rent is not alerted instantly unless `include_free_market: instant`. Reaching the Jobcenter for a free-market flat is rarely worth an instant ping.
- Alerts are sent for all currently open, never-notified listings (not only brand-new ones), ordered by class then score, so the first live run delivers the existing P0/P1 backlog.

## 2026-11-10 — Heating limits not modelled yet
`config/rent_limits.yaml` has an empty `heating` table; heating is shown but never fails a listing. I do not have the AV-Wohnen Heizkosten-Grenzwerte table verified, so I did not invent numbers. Added to INPUTS_NEEDED.

## 2026-11-10 — Telegram design
Plain httpx client, long-polling `getUpdates` for button callbacks (no webhook/public URL needed). Callbacks from any chat other than the configured ones are ignored. Without credentials the same code runs through a console sender (dry run).

## 2026-11-10 — Remaining Tier 1 collectors deferred
inberlinwohnen already lists every city-owned company, so eligibility coverage is complete. Built gewobag (cheap, newest-first). howoge/wbm/stadtundland/berlinovo/gesobau are queued after M3 and should be justified by measured latency vs. inberlinwohnen. Deviation from M2's "remaining Tier 1 collectors".

## 2026-11-10 — Zero-cost local operation (replaces VPS for now)
Owner does not want to pay for hosting. The watcher runs on the owner's Mac via a launchd LaunchAgent (`scripts/launchd/`), with `caffeinate -i` to prevent idle sleep. Polling uses no LLM, so no Claude tokens are spent; tokens are reserved for optional maintenance (repairing broken collectors). Trade-off: no polling while the Mac is off, asleep or offline. Catch-up on wake is automatic (alerts cover all open, never-alerted flats).
- Scheduler is a plain asyncio loop per source (no APScheduler): per-source interval from `config/sources.yaml`, 5 min 06–23 Berlin and 15 min at night, ±20 % jitter, 20 s stagger, 180 s run timeout, loops never die.
- No HTTP `/health` endpoint: nothing external polls it in local mode. `logs/health.json` plus Telegram warnings (3 consecutive failures, and recovery) replace it.
- VPS, GitHub-issue-on-failure and backups from M3 are postponed.

## 2026-11-10 — Digests via Telegram only
Morning (07:00, full: new, still-open, applications this week, excluded counts, source health) plus short summaries at 12:30 and 19:00 (sent only when something is new). Email digest from the spec is skipped: it needs an SMTP account and adds nothing a Telegram message does not. If the Mac is asleep at a slot, the digest is sent on wake when within 3 hours (otherwise skipped, the next one covers it).
