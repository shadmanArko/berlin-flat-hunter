"""Morning digest and short summaries (Telegram, HTML)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from flathunter.core.models import KeyValue, Listing, Source, UserAction
from flathunter.core.profile import Profile
from flathunter.notify.dispatch import too_small

SECTIONS = [
    ("P0_special_need", "🔴 P0 · besonderer Wohnbedarf"),
    ("P1_wbs", "🟠 P1 · WBS"),
    ("needs_review", "🟡 Prüfen"),
    ("P2_free_market", "🟢 P2 · ohne WBS"),
]
REASON_DE = {
    "rent_over_av_wohnen": "Miete über AV-Wohnen-Limit",
    "too_many_rooms_for_wbs": "zu viele Zimmer für den WBS",
    "students_or_trainees_only": "nur Studierende/Azubis",
    "senior_only": "nur Senioren",
    "not_an_apartment": "keine Wohnung (Stellplatz o. ä.)",
    "only_for_wohnungstausch": "nur Wohnungstausch",
}


def _eur(x: float | None) -> str:
    return "?" if x is None else f"{x:,.0f}".replace(",", ".") + " €"


def line(li: Listing) -> str:
    url = li.sources[0].url if li.sources else ""
    rooms = f"{li.rooms:g} Zi" if li.rooms else "? Zi"
    size = f"{li.size_m2:g} m²".replace(".", ",") if li.size_m2 else "? m²"
    room = (li.rent_gross_cold, li.rent_limit_used)
    head = "" if None in room else f" ({room[1] - room[0]:+.0f})"  # type: ignore[operator]
    addr = escape(f"{li.street or ''} {li.house_no or ''}".strip())
    where = escape(li.district or li.ortsteil or "")
    when = "sofort" if li.available_now else (li.available_from.strftime("%d.%m.%y") if li.available_from else "")
    label = f'<a href="{escape(url)}">{addr}</a>' if url else addr
    return f"• {rooms} · {size} · {_eur(li.rent_gross_cold)} BK{head} · {where} · {when} · {label}"


def _get(s: Session, key: str) -> str | None:
    row = s.get(KeyValue, key)
    return row.value if row else None


def _set(s: Session, key: str, value: str) -> None:
    row = s.get(KeyValue, key)
    if row:
        row.value = value
    else:
        s.add(KeyValue(key=key, value=value))


def build_digest(
    s: Session, profile: Profile, kind: str, now: datetime | None = None, max_per_section: int = 8
) -> str | None:
    """Returns the text, or None when a short summary has nothing new to say."""
    now = now or datetime.now(UTC)
    last_raw = _get(s, "last_digest_at")
    since = datetime.fromisoformat(last_raw) if last_raw else now - timedelta(hours=24)
    acted = set(s.scalars(select(UserAction.listing_id)))
    active = [li for li in s.scalars(select(Listing).where(Listing.status == "active")) if li.id not in acted]
    new = [li for li in active if li.first_seen_at > since]
    new_ids = {li.id for li in new}

    def section(items: list[Listing], title: str) -> list[str]:
        items = sorted(items, key=lambda x: -(x.score or 0))
        out = [f"<b>{title}</b> ({len(items)})"] + [line(li) for li in items[:max_per_section]]
        if len(items) > max_per_section:
            out.append(f"… +{len(items) - max_per_section} weitere")
        return out

    def relevant(li: Listing, cls: str) -> bool:
        if li.eligibility_class != cls:
            return False
        if cls == "needs_review" and li.wbs_required is False and profile.include_free_market != "instant":
            return False
        return not (cls != "P2_free_market" and too_small(li, profile))

    title = "☀️ Guten Morgen – Wohnungs-Überblick" if kind == "morning" else "🕐 Neu seit dem letzten Update"
    parts: list[str] = [f"<b>{title}</b>"]
    any_new = False
    for cls, name in SECTIONS:
        n = [li for li in new if relevant(li, cls)]
        if n:
            any_new = True
            parts += ["", *section(n, f"Neu · {name}")]
    small = [li for li in new if li.eligibility_class in ("P0_special_need", "P1_wbs") and too_small(li, profile)]
    if small:
        any_new = True
        parts += ["", *section(small, "⚪ Neu · zu klein für Sofort-Alarm")]
    if kind == "morning":
        for cls, name in SECTIONS[:3]:
            old = [li for li in active if li.id not in new_ids and relevant(li, cls)]
            if old:
                parts += ["", *section(old, f"Noch offen · {name}")]
        week = s.execute(
            select(Listing, UserAction)
            .join(UserAction, UserAction.listing_id == Listing.id)
            .where(UserAction.action == "applied", UserAction.at > now - timedelta(days=7))
        ).all()
        parts += ["", f"📨 Bewerbungen diese Woche: {len(week)}"]
        parts += [f"• {escape((li.street or '') + ' ' + (li.house_no or ''))}" for li, _ in week[:8]]
    elif not any_new:
        return None
    inel = Counter(
        li.eligibility_reason.split(" [")[0]
        for li in new
        if li.eligibility_class == "ineligible" and li.eligibility_reason
    )
    if inel:
        parts += ["", "ausgeschlossen: " + ", ".join(f"{n}× {REASON_DE.get(r, r)}" for r, n in inel.most_common(4))]
    if kind == "morning":
        parts += ["", "<b>System</b>"]
        for src in s.scalars(select(Source).order_by(Source.id)):
            ok = src.last_success_at.astimezone().strftime("%d.%m. %H:%M") if src.last_success_at else "nie"
            flag = "⚠️" if src.consecutive_failures else "✅"
            parts.append(
                f"{flag} {escape(src.id)} · letzter Erfolg {ok}"
                + (f" · {src.consecutive_failures} Fehler in Folge" if src.consecutive_failures else "")
            )
    return "\n".join(parts)[:4000]


async def send_digest(s: Session, sender, profile: Profile, kind: str, max_per_section: int = 8) -> bool:  # type: ignore[no-untyped-def]
    text = build_digest(s, profile, kind, max_per_section=max_per_section)
    if text is not None:
        await sender.send(text, [], loud=False, silent=kind != "morning")
    _set(s, "last_digest_at", datetime.now(UTC).isoformat())
    s.commit()
    return text is not None
