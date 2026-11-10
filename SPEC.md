# Berlin WBS Flat Hunter: Build & Operate Spec

> **For Claude Code.** You own this project end to end: design decisions, code, tests, deployment and ongoing maintenance. This spec is the brief, not a cage. Where you find a better approach than what is written here, use it and record why in `docs/DECISIONS.md`. The owner (Arko, a senior software engineer) has given you full control. Interrupt him only for the inputs listed in §15, and only through the mechanism in §3.

---

## 0. How Arko starts this (human steps)

1. Create an empty **private** GitHub repo, e.g. `berlin-flat-hunter`, clone it, put this file in the root as `SPEC.md`.
2. Open Claude Code in that folder and say:
   *"Read SPEC.md and build the whole project milestone by milestone. Start with milestone M0."*
3. Answer the onboarding questions Claude Code sends you (§15). Everything else is automatic.

---

## 1. Mission

Find the **best and largest flat the household is entitled to, at a rent the household's cost rules allow**, as fast as possible.

**The household's WBS (verified from the original Bescheid). Code must read these from the git-ignored `config/profile.yaml`, never hard-code them. Names, address and case numbers never appear in the repo.**

| Field | Value |
|---|---|
| WBS type | WBS 100 (Ü-Kennzahl 100), issued by Bezirksamt Mitte, Bescheid of 03.11.2026 |
| Besonderer Wohnbedarf | **Granted** ("Ein besonderer Wohnbedarf konnte Ihnen zuerkannt werden") |
| Berechtigungsgruppe | J |
| Household | 3 persons |
| Size entitlement | **3 Räume** plus kitchen and side rooms (bath/shower, WC). Fewer rooms are explicitly allowed. |
| Valid until | End of 11/2027 (Berlin only) |
| Rent policy | Housing costs must fit the Berlin AV-Wohnen limits (`rent_policy: av_wohnen` in profile, see §2.6) |

**Goal ranking:** the biggest eligible flat (3 rooms first, then largest m²) with good facilities, whose rent stays inside the AV-Wohnen limits.

The system must:

- Detect every new matching listing from all relevant Berlin sources **within minutes** of publication.
- Push each match to Arko instantly (Telegram), with the apply link and a pre-written application text.
- Send a **morning digest at 07:00 Europe/Berlin** plus short midday and evening summaries.
- Run unattended 24/7, notice when it breaks, and repair itself via Claude Code maintenance runs.

**Success criteria**

| Metric | Target |
|---|---|
| Time from listing publication to Telegram alert (Tier 1 sources) | ≤ 10 min (p90) |
| Missed eligible listings from Tier 1 sources | 0 (verified weekly against manual check) |
| False "eligible" alerts | < 10 % |
| A broken collector is detected | within 3 consecutive failed runs |
| A broken collector is repaired (PR opened) | within 24 h |

---

## 2. Domain rules: eligibility (get this right, it is the core value)

### 2.1 WBS levels
Berlin WBS levels are **income ceilings**: WBS 100, 140, 160, 180, 220. A WBS 100 holder has the lowest income and therefore qualifies for **every** WBS level. Listings that say "WBS 140", "WBS 180", "WBS bis 220", "WBS erforderlich" etc. are all eligible on income grounds.

### 2.2 Besonderer Wohnbedarf (the household's advantage)
Some social flats are reserved for WBS holders **with besonderer Wohnbedarf**. These have far less competition and must get **top priority (P0)**. Real example wording from a degewo listing:
> "Für die Anmietung dieser Wohnung ist ein Wohnberechtigungsschein 100 oder 140 mit besonderem Wohnbedarf erforderlich."

Detect at least these patterns (case-insensitive, also in title, description, PDF exposé and structured fields):
`besonderem Wohnbedarf`, `besonderer Wohnbedarf`, `bes. Wohnbedarf`, `Dringlichkeit`, `Dringlichkeitsvermerk`, `WBS mit Dringlichkeit`, `WBS-D`, `Sonderwohnbedarf`. Expand this list as you see real listings and keep it in `config/wbs_patterns.yaml`.

### 2.3 Size entitlement (from the WBS: 3 Räume + Küche + Nebenräume)
- The entitlement counts **living rooms** (Wohnräume). Kitchen, bath, WC, hallway and storage don't count. In listings, "3 Zimmer" / "3-Zimmer-Wohnung" = 3 rooms → **fits, and is the target size**.
- 1, 1.5, 2, 2.5 rooms → fits (the WBS explicitly allows fewer rooms), but ranks below 3 rooms.
- 3.5 rooms → `needs_review` (half rooms are treated differently by landlords; flag "ask the landlord whether a WBS for 3 Räume is enough").
- 4+ rooms → `ineligible` for WBS-bound flats. For free-market (no-WBS) flats, room count is limited only by the rent rule below.
- The WBS sets no m² cap; within the room limit, **larger m² is better**.
- "Wohnküche" or "Küche als Zimmer gezählt": `needs_review`.
- Some listings state the WBS room count they require ("WBS für 3 Räume", "WBS mit mind. 2 Räumen", "Raumanzahl laut WBS"). Parse it: required ≤ 3 → fits; required > 3 → `ineligible`.

### 2.6 Rent ceiling (profile `rent_policy: av_wohnen`)
The household's housing costs must stay within Berlin's AV-Wohnen limits, otherwise the move will not be approved. Implement the check exactly like this, with all numbers in `config/rent_limits.yaml` (with the source URL and valid-from date) so they can be updated each year without code changes:

- Compute **Bruttokaltmiete = Kaltmiete (Nettokalt) + Betriebskosten/Nebenkosten excluding heating and hot water**. Parse heating costs separately.
- Limits valid since 01.01.2026 for a 3-person household (Jobcenter Mitte overview):
  - general Richtwert Bruttokalt: **668.80 €/month**
  - Richtwert for **social housing (Sozialwohnung / WBS-bound flat): 736.00 €/month**
  - Heating is checked separately against the AV-Wohnen Heizkosten-Grenzwerte, which depend on the energy carrier and the building's total floor area. Store that table too, and if the listing doesn't state the energy carrier or building size, mark heating "unknown" rather than failing the listing.
- Apply the social-housing limit when the listing is WBS-bound, otherwise the general limit.
- Classification:
  - Bruttokalt ≤ limit → `rent_ok`
  - ≤ limit + 10 % → `rent_borderline` → class `needs_review` with the note "ask Jobcenter before applying" (still alert, because borderline cases are sometimes approved)
  - above that → `ineligible` (reason: `rent_over_av_wohnen`), but count these in the digest
  - rent components missing → compute what is possible, mark `rent_unknown`, still alert P0/P1 listings
- Show in every alert: Kaltmiete, Nebenkosten, Heizkosten, computed Bruttokalt, the limit used, and the headroom in €.
- Any Härtefall supplements that may apply are decided by the Jobcenter case by case. Don't model them; Arko can raise the limit in `profile.yaml` (`rent_limit_override`) if the Jobcenter confirms a higher one in writing.

### 2.7 Berechtigungsgruppe
The household's group is **J**. If a listing names specific Berechtigungsgruppen (e.g. "nur für Berechtigungsgruppe …"), match against the profile's group: listed → eligible, not listed → `ineligible`, unclear → `needs_review`.

### 2.4 Other restrictions to detect (flag as ineligible or needs_review)
Senior-only (`Seniorenwohnung`, `ab 60/65 Jahren`), wheelchair-only (`rollstuhlgerecht ... nur für`), student-only, Tauschwohnung-only (`nur für Wohnungstausch`, `Mieter der ... Gesellschaft`), Wohnberechtigung for specific groups not matching the household, "Genossenschaftsmitgliedschaft erforderlich" (flag, don't exclude).

### 2.5 Eligibility classes
Each listing gets exactly one:
- `P0_special_need` — WBS with besonderer Wohnbedarf required, size fits (§2.3), rent ok (§2.6).
- `P1_wbs` — WBS required (any level), size fits, rent ok.
- `P2_free_market` — no WBS needed, rent ok under the general limit.
- `needs_review` — ambiguous; send to Arko with the reason.
- `ineligible` — stored, never alerted (but counted in digests).

Use deterministic rules first. For listings the rules mark `needs_review`, call an LLM classifier (Claude API, small/cheap model such as `claude-haiku-5-5`, JSON output, temperature 0) with the full text and the household profile. Log the LLM's reason. Rules always win over the LLM when both are confident.

---

## 3. Operating principles for Claude Code

1. **Autonomy.** Make decisions yourself. Record non-trivial ones in `docs/DECISIONS.md` (date, decision, alternatives, reason).
2. **Asking for input.** When you truly need something from Arko (credentials, a personal choice, a legal or ToS judgment call), add an entry to `INPUTS_NEEDED.md` (what, why, exact format, where to put it) and, once Telegram works, send it to him there too. Then **continue with everything that is not blocked**. Never stop the whole project waiting on one answer.
3. **Secrets.** Never commit secrets or personal data. Use `.env` (git-ignored) plus `.env.example`. Personal profile data lives in `config/profile.yaml` (git-ignored) with a committed `profile.example.yaml`. Add a pre-commit secret scanner (e.g. gitleaks).
4. **Polite, legal scraping.** Check each site's robots.txt and terms before writing a collector and record the result in the source registry. Use honest rate limits, jitter, conditional requests (ETag / If-Modified-Since) where supported, and prefer official feeds or the site's own JSON/XHR endpoints over HTML parsing. Never hammer a site.
5. **No bot-detection evasion.** Do not solve, bypass or outsource CAPTCHAs, and do not use residential proxy rotation or fingerprint spoofing. If a site blocks automated access, switch that source to the email-alert route (§5.3) and note it.
6. **Never apply on Arko's behalf without his explicit per-source opt-in** (§9).
7. **Tests before deploy.** Every collector has fixture tests from saved real responses. CI must be green before deploy.
8. **Small, verifiable milestones** (§14). Finish each milestone's acceptance criteria before starting the next.

---

## 4. Architecture

### 4.1 Key decision: split "watching" from "thinking"
Polling every few minutes must be cheap, fast and deterministic, so the **Watcher** is a normal Python service that runs 24/7 on a server. It does not start an LLM session per poll (too slow, too costly, and subject to usage limits). **Claude Code scheduled routines** are used for what needs intelligence: repairing broken collectors, discovering new sources, and weekly quality review.

```
            ┌──────────────────────── VPS (Docker Compose) ───────────────────────┐
            │                                                                      │
 Sources ──►│  Scheduler ─► Collectors ─► Normalizer ─► Dedup ─► Eligibility ─►  │──► Telegram (instant)
 (web,      │      │             │                                   │            │──► Email digest (07:00)
  email     │      │             └─► raw snapshots (failures)        ▼            │
  alerts)   │      └──────────► Health monitor ──────────► Postgres                │
            │                         │                                            │
            └─────────────────────────┼────────────────────────────────────────────┘
                                      ▼
                         GitHub Issue "collector-broken"
                                      ▼
              Claude Code routine (daily) ─► fix + fixture test ─► PR ─► CI ─► auto-deploy
```

### 4.2 Stack (adjust if you have good reason)
- Python 3.12, `uv` for dependencies, `ruff` + `mypy` + `pytest`.
- HTTP: `httpx` (async, HTTP/2). Parsing: `selectolax` (HTML), `pypdf` or `pdfplumber` (exposé PDFs).
- Browser only where unavoidable: Playwright (Chromium), one shared browser, strict timeouts.
- Scheduling: APScheduler inside the Watcher (per-source cron/interval + jitter), timezone Europe/Berlin.
- DB: PostgreSQL 16, SQLAlchemy 2 + Alembic migrations.
- Notifications: Telegram Bot API (`python-telegram-bot` or plain httpx), SMTP for email digest.
- Email alert ingestion: IMAP on a dedicated mailbox.
- Deploy: Docker Compose on a small Linux VPS (e.g. Hetzner, Ubuntu LTS), GitHub Actions: test → build → deploy over SSH on merge to `main`.
- Observability: structured JSON logs, a `/health` endpoint, a `runs` table, Telegram alerts for failures, Uptime check (healthchecks.io or similar) pinged every cycle.

### 4.3 Repo layout
```
berlin-flat-hunter/
  SPEC.md  CLAUDE.md  INPUTS_NEEDED.md  README.md
  docs/ DECISIONS.md  RUNBOOK.md  SOURCES.md
  config/ sources.yaml  wbs_patterns.yaml  rent_limits.yaml  scoring.yaml
          schedule.yaml  profile.example.yaml  (profile.yaml is git-ignored)
  src/flathunter/
    collectors/   base.py  inberlinwohnen.py  degewo.py  gewobag.py  howoge.py
                  wbm.py  stadtundland.py  berlinovo.py  email_alerts.py  genossenschaften/...
    core/         models.py  normalize.py  dedup.py  eligibility.py  scoring.py
    notify/       telegram.py  digest.py  templates/
    apply/        letter.py  checklist.py  (submit/ later, opt-in only)
    ops/          scheduler.py  health.py  github_issues.py  main.py
  tests/  fixtures/<source>/*.html|json|pdf  test_collectors.py  test_eligibility.py ...
  migrations/
  docker-compose.yml  Dockerfile  .env.example  .github/workflows/
```

Create a concise `CLAUDE.md` early with: project purpose, commands (test, lint, run locally, deploy), conventions, and the guardrails from §3, so every future Claude Code session (including routines) starts with the right context.

---

## 5. Sources

Maintain all sources in `config/sources.yaml` (id, name, tier, method, url, interval, robots/ToS status, enabled, owner notes). **Verify every URL yourself**; the list below is the starting point, not ground truth.

### 5.1 Tier 1: city-owned housing companies (most WBS flats). Poll every 5 min, 06:00–23:00; every 15 min at night.
| id | Source | Notes |
|---|---|---|
| `inberlinwohnen` | inberlinwohnen.de (Wohnungsfinder) | Aggregates the city-owned companies. Primary source. |
| `degewo` | degewo.de Immosuche | Listing pages have WBS fields and PDF exposés. |
| `gewobag` | gewobag.de | |
| `howoge` | howoge.de | |
| `wbm` | wbm.de | Applications close after the first N applicants: speed matters most here. |
| `stadtundland` | stadtundland.de | |
| `berlinovo` | berlinovo.de | Smaller stock, also furnished/apartment offers. |

Scrape the aggregator **and** each company's own site: some listings appear on the company site first. For each, open the site in Playwright once, inspect network traffic, and prefer a JSON endpoint if one exists.

### 5.2 Tier 2: large private landlords with some WBS stock. Poll every 15–30 min.
Vonovia / Deutsche Wohnen, Covivio, Heimstaden, Adler, Gesobau-like entities you discover. Research which actually list WBS flats in Berlin; enable only those that do.

### 5.3 Tier 3: big portals via email alerts (not scraped)
ImmoScout24, Immowelt, Kleinanzeigen: these use heavy bot detection. Instead:
1. Arko creates saved searches with instant email alerts (search term "WBS", Berlin, his size/rent limits) pointed at a dedicated mailbox (§15).
2. `email_alerts.py` polls that mailbox via IMAP every 2 min, parses each alert into listing records (one parser per portal's email template, with fixture tests), and feeds them into the normal pipeline.
3. If a listing page from an alert is needed for details, fetch it once at human pace; if blocked, keep the email data and mark details as missing.

### 5.4 Tier 4: housing cooperatives (Genossenschaften). Check 2×/day.
Build a discovery task: compile Berlin cooperatives that publish vacancies or open their waiting lists (e.g. via the Berlin cooperative associations' listings). For each, a generic "page changed" collector (normalized text hash of the vacancy section) is enough; alert on change with a diff summary. Flag those requiring membership.

### 5.5 Source discovery
Monthly, a Claude Code routine searches for new Berlin WBS listing sources and opens a PR adding any good ones as disabled entries for review.

---

## 6. Data model (PostgreSQL)

- `sources` — mirror of `sources.yaml` plus runtime state (last_success_at, consecutive_failures, enabled).
- `runs` — one row per collector run: source_id, started_at, duration_ms, http_status, items_seen, items_new, error.
- `listings` — canonical flat: id, fingerprint (unique), first_seen_at, last_seen_at, status (`active`/`gone`), address (street, house_no, postcode, district, ortsteil), lat/lon (optional geocode), rooms, size_m2, rent_cold, operating_costs (excl. heating), heating_costs, rent_gross_cold (computed), rent_warm, energy_carrier, building_floor_area, rent_check (`rent_ok`/`rent_borderline`/`rent_over`/`rent_unknown`), rent_limit_used, deposit, kitchen_included (Einbauküche), bathroom_window, heating_type, construction_year, available_from, floor, elevator, balcony, wbs_required (bool/null), wbs_levels (int[]), special_need_required (bool/null), eligibility_class, eligibility_reason, score, raw_text.
- `listing_sources` — listing_id, source_id, external_id, url, first_seen_at (a flat can come from several sources).
- `listing_events` — price changes, re-listings, removal.
- `notifications` — listing_id, channel, sent_at, message_id, kind (`instant`/`digest`/`needs_review`).
- `user_actions` — listing_id, action (`applied`, `not_interested`, `viewing_booked`, `rejected`, `offer`, `signed`, `withdrawn`), at, note (fed by Telegram buttons).
- `inputs_needed` — key, question, status, answered_at.

## 7. Pipeline details

**Collector contract** (`collectors/base.py`): `async def fetch() -> list[RawListing]`. Must be idempotent, time-bounded (≤ 60 s), and must raise a typed error on layout change (e.g. zero items where items are expected, missing required fields), never silently return empty.

**Normalization:** German number formats (`1.234,56 €`), `Zimmer` vs `Zi.`, warm vs cold rent (compute warm if components are given), dates (`ab sofort`, `01.12.2026`), districts mapped to the 12 Bezirke + Ortsteile.

**Dedup fingerprint:** normalized street + house number + postcode + rooms + round(size_m2) (+ floor if present). Fuzzy-match fallback (address similarity + size within ±2 m² + rent within ±3 %) to merge the same flat from different sources. Never alert twice for one flat; append the extra source link to the existing alert instead.

**Change detection:** a listing that disappears for 3 consecutive runs becomes `gone`. A reappearing listing is a re-listing event (alert again only if it was not already acted on).

**Scoring** (orders listings within a class; class always comes first, so a P0 2-room flat still beats a P1 3-room flat in alert loudness, but the digest shows both clearly). Weighted, documented in `docs/SCORING.md`, weights in `config/scoring.yaml`:
1. **Rooms** (heaviest): 3 > 2.5 > 2 > lower.
2. **Size m²** within that room count: larger is better.
3. **Rent headroom**: more € below the AV-Wohnen limit is better (safer approval, lower risk if Nebenkosten rise).
4. **Facilities**: elevator, balcony/loggia, fitted kitchen, bath with window, modern heating (district heating/gas over night-storage), good energy class, newer or renovated building.
5. **Location**: preferred districts from profile; optional commute time if Arko provides a routing API key and target locations (school/Kita, work).
6. **Availability**: move-in date inside the household's window.
Each alert shows the top 3 reasons for its score.

## 8. Notifications

**Instant Telegram alert** for `P0`, `P1`, `P2` (P2 only if enabled in profile) and `needs_review`:
```
🔴 P0 · WBS mit besonderem Wohnbedarf
2 Zi · 54 m² · 612 € warm · Lichtenberg (Fennpfuhl)
Frei ab: sofort · 3. OG · Aufzug · Balkon
Quelle: degewo (+ inberlinwohnen)
➡ Bewerben: <link>
⏱ gefunden 4 min nach Veröffentlichung
[✅ Beworben] [👎 Nicht interessant] [📝 Anschreiben]
```
P0 alerts should use a distinct, loud notification (separate Telegram chat or bot with sound) so Arko never misses one.

**Morning digest (07:00)** via Telegram and email (HTML): new matches since last digest grouped by class, open listings not yet acted on, applications this week, and system health (each source's last success). **Short summaries at 12:30 and 19:00.** All times configurable.

**Health alerts:** a source failing 3 times in a row, the IMAP mailbox silent for > 48 h, the Watcher down (external uptime check).

## 9. Application assist

- **Phase A (build by default):** For each alert, the `📝 Anschreiben` button returns a short, polite German application text generated from `profile.yaml`, tailored to the listing. It states: household of 3, WBS 100 **mit besonderem Wohnbedarf** (Berechtigungsgruppe J), valid until 11/2027, entitled to 3 Räume, desired move-in date, contact details. It does **not** mention income figures.
- Document checklist per listing (with paths to Arko's document folder if configured):
  1. WBS (the "Wohnberechtigungsschein" page) — always
  2. Überlassungsmitteilung (the form the landlord fills in and sends to the Wohnungsamt) — always hand over with the WBS
  3. Bescheinigung über die Prüfung der Wohnberechtigung / income certificate — only if the landlord asks
  4. IDs, Mietschuldenfreiheitsbescheinigung, Schufa, and any landlord-specific forms
- **Approval step before signing:** when Arko marks a listing `offer` in Telegram, the system sends a reminder: request a written rental offer (Mietangebot) from the landlord and get the Jobcenter's written approval of the new rent **before signing**. Generate the rent breakdown (Kaltmiete, Nebenkosten, Heizkosten, Bruttokalt vs. limit) as a one-page PDF to hand in. If a deposit is needed, the reminder also says to ask the Jobcenter about it in the same request.
- **After a flat is secured:** when Arko marks `signed`, pause all alerts and send him the list of every other open application (from `user_actions`), so he can withdraw them, as the WBS letter asks. Also schedule a reminder 60 days before the WBS expires (end of 11/2027) in case the search is still running.
- **Phase B (opt-in per source, off by default):** "One-tap apply": Arko taps `Jetzt bewerben` in Telegram and the system fills and submits that source's application form with his profile. Build only for sources where (a) the terms do not forbid it, (b) there is no CAPTCHA, and (c) Arko has explicitly enabled it in `profile.yaml`. Before enabling any source, ask Arko via §3.2 with your ToS assessment. Portal account passwords, if needed, come from `.env` that Arko fills himself; never ask him to paste passwords into chat.
- Never auto-submit without the tap. Log every submission with a screenshot/HTML receipt.

## 10. Scheduling summary (`config/schedule.yaml`)

| Job | When |
|---|---|
| Tier 1 collectors | every 5 min 06:00–23:00, every 15 min otherwise, ±20 % jitter, sources staggered |
| Tier 2 collectors | every 20 min |
| Email alerts (IMAP) | every 2 min |
| Tier 4 cooperatives | 08:00 and 16:00 |
| Digests | 07:00, 12:30, 19:00 |
| Gone-check / housekeeping | hourly |
| DB backup | daily 03:30, keep 14 days |

## 11. Claude Code routines (maintenance agent)

Create these as Claude Code **cloud routines** (so they run with Arko's laptop closed), attached to this repo. Create them with `/schedule` or ask Arko to create them at claude.ai/code/routines if you can't; put the exact prompts in `docs/ROUTINES.md`.

1. **Daily repair (06:00):** "Read CLAUDE.md. Check open GitHub issues labeled `collector-broken`. For each: reproduce, fix the collector, add or update a fixture test from the current page, run the full test suite, open a PR, and enable auto-merge if CI passes. Comment on the issue with what changed. If a fix needs Arko's input, add it to INPUTS_NEEDED.md and say so in the issue."
2. **Weekly quality review (Sunday 10:00):** "Sample last week's `ineligible` and `needs_review` listings, check the eligibility rules against them, tighten `wbs_patterns.yaml` and the rules, open a PR with the evidence."
3. **Monthly source discovery (1st of month):** §5.5.

The Watcher creates or updates the `collector-broken` issue automatically (GitHub API, token in `.env`) with the error, the run history and a saved copy of the failing response.

## 12. Deployment & ops

- `docker compose up -d` brings up `watcher`, `postgres`, (optional) `playwright` sidecar. Restart policy `unless-stopped`. Resource limits set.
- GitHub Actions: on PR → lint, type-check, tests. On merge to `main` → build image, SSH to VPS, pull, run migrations, restart, smoke test (`/health`, one dry-run of each Tier 1 collector), roll back on failure.
- `docs/RUNBOOK.md`: how to restart, read logs, pause a source, rotate secrets, restore a backup.
- Server hardening basics: non-root user, SSH keys only, firewall (only SSH open; no public DB port), automatic security updates.

## 13. Testing

- Unit tests for normalization, WBS pattern detection (include real phrases, negatives and tricky cases like "kein WBS erforderlich"), size entitlement, dedup.
- Collector tests run against saved fixtures; a separate, manually triggered "live smoke" job hits the real sites once.
- End-to-end test: fixture listing → pipeline → Telegram message rendered (mock sender) → digest rendered.
- Eligibility golden set: `tests/golden/eligibility.yaml` with ≥ 50 labeled real listings by M4.

## 14. Milestones (finish acceptance criteria before moving on)

| # | Scope | Acceptance |
|---|---|---|
| **M0** | Repo scaffold, CLAUDE.md, tooling, CI, `.env.example`, `profile.example.yaml`, `INPUTS_NEEDED.md` filled with §15 items, onboarding message to Arko | CI green; Arko has a clear list of what to provide |
| **M1** | Postgres schema, collectors for `inberlinwohnen` + `degewo`, normalization, dedup, WBS parser, local run | Real listings stored correctly; tests green |
| **M2** | Telegram instant alerts + buttons, eligibility rules, remaining Tier 1 collectors | Arko receives a correct alert for a real live listing |
| **M3** | VPS deployment, scheduler, health monitor, GitHub issue on failure, backups | Runs 48 h unattended; a forced failure creates an issue and a Telegram alert |
| **M4** | Digests, email-alert ingestion (Tier 3), LLM needs_review classifier, golden set | 07:00 digest arrives; portal alert emails become listings |
| **M5** | Claude Code routines (§11), Tier 2 + Tier 4 sources | A deliberately broken parser is fixed by the routine via PR |
| **M6** | Application assist Phase A; Phase B only per explicit opt-in | Cover letter generated per listing; any opt-in source submits on tap with receipt |

Ship M2 as fast as possible: a working Tier 1 alert pipeline is most of the value. Polish later.

## 15. Inputs needed from Arko

Collect these during M0 via `INPUTS_NEEDED.md` (and Telegram once it exists). Ask in small batches, in the order they block work.

**Already provided (from the WBS papers) — do not ask again:** household size 3; entitlement 3 Räume; WBS 100 with besonderer Wohnbedarf; Berechtigungsgruppe J; valid until end of 11/2027; rent policy AV-Wohnen. Arko supplies `config/profile.yaml` with these plus names and contact details.

**Needed for M1–M2**
1. *(answered, see above)*
2. *(answered, see above)*
3. Whether the Jobcenter has confirmed any limit higher than the standard AV-Wohnen values (`rent_limit_override`), otherwise use the defaults in §2.6.
4. Preferred and excluded districts; any must-haves (elevator, ground floor, balcony, max floor), and whether a preference should override "bigger is better".
5. Earliest and latest move-in date.
6. Telegram: bot token from @BotFather and his chat ID (Claude Code explains how to get both). Optional second chat for loud P0 alerts.
7. Whether to include P2 (free-market, no-WBS) listings in instant alerts or digest only.

**Needed for M3**
8. A small Linux VPS with SSH access (or an always-on home machine), and SSH key/host details placed in GitHub Actions secrets by Arko.
9. GitHub token (fine-grained, this repo only: issues + contents + pull requests) for the Watcher.

**Needed for M4**
10. A dedicated mailbox for portal alerts (e.g. a new Gmail) with IMAP enabled and an app password in `.env`; Arko creates the saved searches on ImmoScout24, Immowelt and Kleinanzeigen pointing to it.
11. Email address for the digest.
12. Anthropic API key for the needs_review classifier and cover letters (optional; rules-only mode works without it).

**Needed for M6**
13. Profile for applications: name, phone, email, current address, occupation, short household description, preferred tone. Where his documents are stored (folder path), if he wants the checklist to point to them.
14. Per-source opt-in for one-tap apply, after reading Claude Code's ToS notes.

## 16. Guardrails (summary)

Private repo. No secrets or personal data in git or logs. Respect robots.txt and terms; no CAPTCHA solving or anti-bot evasion. Never submit an application without Arko's tap and per-source opt-in. Rate-limit every source. Fail loudly, never silently.
