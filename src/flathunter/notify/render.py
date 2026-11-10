"""Instant alert rendering (SPEC §8). Telegram HTML parse mode."""

from __future__ import annotations

from html import escape

from flathunter.core.models import Listing
from flathunter.core.profile import Profile
from flathunter.core.scoring import score

BADGE = {
    "P0_special_need": "🔴 P0 · WBS mit besonderem Wohnbedarf",
    "P1_wbs": "🟠 P1 · WBS",
    "P2_free_market": "🟢 P2 · ohne WBS",
    "needs_review": "🟡 Prüfen",
}
SOURCE_LABEL = {"inberlinwohnen": "inberlinwohnen", "degewo": "degewo"}


def _eur(x: float | None) -> str:
    return "?" if x is None else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def render_alert(
    li: Listing, profile: Profile, listing_id_for_buttons: int | None = None
) -> tuple[str, list[list[dict[str, str]]]]:
    rooms = f"{li.rooms:g} Zi" if li.rooms else "? Zi"
    size = f"{li.size_m2:g} m²" if li.size_m2 else "? m²"
    place = li.district or li.ortsteil or ""
    if li.ortsteil and li.district:
        place = f"{li.district} ({li.ortsteil})"
    avail = "sofort" if li.available_now else (li.available_from.strftime("%d.%m.%Y") if li.available_from else "k. A.")
    bits = [f"{li.floor}. OG" if li.floor else ("EG" if li.floor == 0 else None)]
    feats = " ".join(li.features or []).lower()
    if "aufzug" in feats:
        bits.append("Aufzug")
    if "balkon" in feats or "loggia" in feats or "terrasse" in feats:
        bits.append("Balkon/Terrasse")
    if "einbauküche" in feats:
        bits.append("EBK")
    limit = li.rent_limit_used
    headroom = None if limit is None or li.rent_gross_cold is None else limit - li.rent_gross_cold
    lines = [
        f"<b>{BADGE.get(li.eligibility_class or '', li.eligibility_class)}</b>",
        f"{rooms} · {size} · {_eur(li.rent_warm)} warm · {escape(place)}",
        f"{escape(li.street or '')} {escape(li.house_no or '')}".strip(),
        f"Frei ab: {avail}" + "".join(f" · {b}" for b in bits if b),
        f"Kalt {_eur(li.rent_cold)} + NK {_eur(li.operating_costs)} = <b>Bruttokalt {_eur(li.rent_gross_cold)}</b>"
        f" · Heizung {_eur(li.heating_costs)}",
    ]
    if limit is not None:
        h = "" if headroom is None else f" · Spielraum {headroom:+.0f} €"
        lines.append(f"Limit {_eur(limit)}{h} ({li.rent_check})")
    if li.wbs_required:
        lv = "/".join(map(str, li.wbs_levels)) if li.wbs_levels else "?"
        lines.append(f"WBS {lv}" + (" · bes. Wohnbedarf" if li.special_need_required else ""))
    if li.eligibility_reason and li.eligibility_class == "needs_review":
        lines.append("⚠️ " + escape(li.eligibility_reason))
    elif li.eligibility_reason and "[" in li.eligibility_reason:
        lines.append("⚠️ " + escape(li.eligibility_reason.split("[", 1)[1].rstrip("]")))
    src = " + ".join(escape(SOURCE_LABEL.get(s.source_id, s.source_id)) for s in li.sources)
    if li.landlord:
        src = f"{escape(li.landlord)} via {src}" if li.landlord not in src else src
    lines.append(f"Quelle: {src}")
    links = " · ".join(f'<a href="{escape(s.url)}">{escape(s.source_id)}</a>' for s in li.sources)
    lines.append(f"➡ Bewerben: {links}")
    if li.published_at and li.first_seen_at:
        mins = int((li.first_seen_at - li.published_at).total_seconds() // 60)
        if 0 <= mins < 24 * 60:
            lines.append(f"⏱ gefunden {mins} min nach Veröffentlichung")
    _, why = score(
        {"rooms": li.rooms, "size_m2": li.size_m2, "features": li.features, "text": "", "district": li.district},
        headroom,
        profile,
    )
    if why:
        names = {
            "elevator": "Aufzug",
            "balcony": "Balkon/Terrasse",
            "fitted_kitchen": "EBK",
            "bath_window": "Bad mit Fenster",
            "modern_heating": "moderne Heizung",
        }
        why = [", ".join(names.get(x.strip(), x.strip()) for x in w.split(",")) for w in why]
        lines.append("★ " + " · ".join(escape(w) for w in why))
    lid = li.id
    buttons = [
        [
            {"text": "✅ Beworben", "callback_data": f"act:{lid}:applied"},
            {"text": "👎 Nicht interessant", "callback_data": f"act:{lid}:not_interested"},
            {"text": "📝 Anschreiben", "callback_data": f"act:{lid}:letter"},
        ]
    ]
    return "\n".join(x for x in lines if x), buttons
