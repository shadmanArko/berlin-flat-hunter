# Inputs needed from Arko

Only items not already in `config/profile.yaml` or `SPEC.md`. Ordered by what blocks work first.
Nothing here blocks M0/M1 locally; I continue with everything unblocked.

## 1. GitHub remote (blocks: "CI green" in M0)
- **What:** OK to run `gh repo create berlin-flat-hunter --private --source . --push` under your account (`gh` is already logged in)? Or create an empty private repo yourself and give me the URL.
- **Why:** CI (GitHub Actions) can only run on a remote. Creating a repo publishes code, so I will not do it unasked.
- **Format:** reply "yes, create it" or paste the repo URL.

## 2. Telegram bot (blocks: M2 acceptance)
- **What:** bot token and your chat ID. Optional: a second chat/bot for loud P0 alerts.
- **How:** in Telegram, message @BotFather, send `/newbot`, copy the token. Then message your new bot once and open `https://api.telegram.org/bot<TOKEN>/getUpdates`; the number at `message.chat.id` is the chat ID.
- **Where:** `.env` as `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=` (optional `TELEGRAM_P0_CHAT_ID=`). Do not paste the token into chat.

## 3. Search preferences (blocks: scoring in M2; defaults used until answered)
Fill the TODO fields in `config/profile.yaml`:
- `districts_preferred` / `districts_excluded`
- `must_have` (elevator, balcony, max floor, ...), and whether a preference should override "bigger is better"
- `move_in_earliest` / `move_in_latest` (YYYY-MM-DD)
- `include_free_market`: `instant`, `digest_only` or `off` (I currently assume `digest_only`)

Until then: no district filter, no must-haves, any move-in date.

## 3b. AV-Wohnen heating limits and source URL (optional; blocks only the heating check)
Either send the Jobcenter's current Heizkosten-Grenzwerte table (energy carrier x building floor area) or the URL of the Jobcenter Mitte overview you got the 668.80 / 736.00 values from. Until then heating is displayed but not checked.

## 4. Contact details for landlords (blocks: M6 cover letters only)
`household.contact.email` and `household.contact.phone` in `config/profile.yaml`; also confirm who the main contact is.

## 5. VPS + GitHub token (blocks: M3)
- A small Linux VPS (e.g. Hetzner, Ubuntu LTS) with SSH, or an always-on home machine. SSH key/host go into GitHub Actions secrets (you set them; I will give the exact secret names).
- A fine-grained GitHub token for this repo only (issues, contents, pull requests) as `GITHUB_TOKEN` in the server `.env`.

## 6. Mailbox for portal alerts, digest address, Anthropic key (blocks: M4)
- Dedicated mailbox with IMAP enabled and an app password in `.env`; then create the ImmoScout24 / Immowelt / Kleinanzeigen saved searches pointing at it.
- Email address for the digest.
- `ANTHROPIC_API_KEY` in `.env` (optional; rules-only mode works without it).

## 7. Application assist (blocks: M6)
Occupation, short household description, preferred tone, documents folder path. Per-source opt-in for one-tap apply comes later, with my ToS notes.
